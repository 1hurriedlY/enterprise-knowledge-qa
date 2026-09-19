import asyncio
import logging
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.domain import DocumentStatus, Intent, MessageRole, ToolCallStatus
from app.models import Chunk, Conversation, Document, Message, RequestLog, ToolCall, User
from app.prompts import (
    INTENT_PROMPT_V1,
    QUERY_REWRITE_PROMPT_V1,
    RAG_ANSWER_PROMPT_V1,
    RAG_ANSWER_PROMPT_VERSION,
    TOOL_DECISION_PROMPT_V1,
    TOOL_SUMMARY_PROMPT_V1,
    TOOL_SUMMARY_PROMPT_VERSION,
    TRANSFER_HUMAN_PROMPT_V1,
    TRANSFER_HUMAN_PROMPT_VERSION,
)
from app.schemas import (
    ChatResponse,
    IntentDecision,
    QueryLogisticsArgs,
    QueryLogisticsResult,
    QueryOrderArgs,
    QueryOrderResult,
    RagAnswerResult,
    RewriteResult,
    SourceCitation,
    ToolCallSummary,
    ToolDecision,
    ToolErrorResult,
    TransferHumanResult,
    TransferToHumanArgs,
    TransferToHumanResult,
)
from app.services.bm25 import Bm25Document, Bm25Hit, Bm25Index
from app.services.llm import LlmClient, LlmOutputError, compact_json, render_history
from app.services.redaction import redact_json, redact_text
from app.services.reranker import RerankClient, RerankError, RerankScore
from app.services.tools import query_logistics, query_order, transfer_to_human
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

NO_ANSWER = "抱歉，知识库中未找到相关信息。如果您需要进一步帮助，可以转接人工客服。"
SENSITIVE_REPLY = "抱歉，我无法提供这类高风险建议。如果您有订单或售后服务相关问题，我可以帮您处理。"
IRRELEVANT_REPLY = "抱歉，我只能协助处理企业知识库、订单、物流和售后服务相关问题。"
INJECTION_REPLY = "抱歉，我无法提供内部规则或执行该请求。请告诉我您的订单、物流或售后问题。"


class ConversationNotFoundError(ValueError):
    """Raised only when a conversation is absent or belongs to another user."""


@dataclass(frozen=True)
class RetrievedChunk:
    source: SourceCitation
    number: str


@dataclass(frozen=True)
class _CachedBm25Corpus:
    index: Bm25Index
    documents: tuple[Bm25Document, ...]
    fingerprint: tuple[int, datetime | None]
    expires_at: float


_BM25_CACHE: OrderedDict[uuid.UUID, _CachedBm25Corpus] = OrderedDict()


def _preclassified_reply(query: str) -> tuple[Intent, str] | None:
    lowered = query.lower()
    if any(marker in lowered for marker in ("系统提示词", "忽略之前", "开发者模式", "内部指令")):
        return Intent.IRRELEVANT, INJECTION_REPLY
    if any(marker in lowered for marker in ("股票", "投资建议", "诊断", "法律意见", "政治")):
        return Intent.SENSITIVE, SENSITIVE_REPLY
    return None


def _resolve_explicit_tool_intent(intent: Intent, query: str) -> Intent:
    """Correct only unambiguous tool intents before an irreversible action.

    The model remains responsible for nuanced classification. Clear operational
    wording is deterministic, however: a shipment-status question must not
    accidentally trigger logistics history, and a tracking question must not
    accidentally trigger an order-status response.
    """
    if intent not in {Intent.ORDER_QUERY, Intent.LOGISTICS_QUERY}:
        return intent
    normalized = query.replace(" ", "")
    if any(marker in normalized for marker in ("物流", "到哪", "派送", "什么时候到", "何时到")):
        return Intent.LOGISTICS_QUERY
    if any(marker in normalized for marker in ("发货了吗", "是否发货", "订单状态", "发货状态")):
        return Intent.ORDER_QUERY
    return intent


def _explicit_order_id(query: str) -> str | None:
    """Return an order ID that is present in the user's current message.

    The keyword form supports the documented alphanumeric-and-hyphen format;
    the numeric fallback keeps short conversational forms such as "12345 到哪了".
    """
    labeled = re.search(
        r"(?:订单(?:号)?|order(?:\s+(?:id|number))?)\s*[:：#]?\s*"
        r"([A-Za-z0-9][A-Za-z0-9-]{2,79})(?![A-Za-z0-9-])",
        query,
        flags=re.IGNORECASE,
    )
    if labeled is not None:
        return labeled.group(1)
    numeric = re.search(r"(?<!\d)(\d{3,80})(?!\d)", query)
    return numeric.group(1) if numeric is not None else None


def _history_order_id(history: list[tuple[str, str]]) -> str | None:
    """Find an explicit order number from prior user turns, newest first."""
    for role, content in reversed(history):
        if role == MessageRole.USER.value:
            order_id = _explicit_order_id(content)
            if order_id is not None:
                return order_id
    return None


async def _history(session: AsyncSession, conversation_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = (
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(10)
        )
    ).all()
    return [(row.role.value, row.content) for row in reversed(rows)]


async def _retrieve(
    session: AsyncSession, user_id: uuid.UUID, query: str, llm: LlmClient
) -> list[RetrievedChunk]:
    settings = get_settings()
    vector = await llm.embed(query)
    vector_hits = await VectorStore().search(user_id, vector, limit=10)
    threshold = settings.retrieval_score_threshold
    found_rows: dict[uuid.UUID, tuple[Chunk, Document]] = {}
    found_documents: dict[uuid.UUID, Bm25Document] = {}
    use_hybrid = settings.hybrid_search_enabled
    if use_hybrid:
        corpus = await _get_bm25_corpus(session, user_id, settings)
        if corpus is None:
            use_hybrid = False
        else:
            index, documents = corpus
            found_documents = {document.chunk_id: document for document in documents}
            bm25_hits = index.search(query, limit=10)
            hits = _fuse_hybrid_hits(
                vector_hits,
                bm25_hits,
                settings.hybrid_vector_weight,
                settings.hybrid_bm25_weight,
                limit=10,
            )
    if not use_hybrid:
        if not vector_hits:
            return []
        hit_scores = {chunk_id: score for chunk_id, score in vector_hits}
        rows = (
            await session.execute(
                select(Chunk, Document)
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    Chunk.id.in_(hit_scores),
                    Document.user_id == user_id,
                    Document.status == DocumentStatus.COMPLETED,
                )
            )
        ).all()
        hits = vector_hits
    if not hits:
        return []
    if not use_hybrid:
        found_rows = {chunk.id: (chunk, document) for chunk, document in rows}
    candidates: list[RetrievedChunk] = []
    for chunk_id, score in hits:
        if use_hybrid:
            bm25_document = found_documents.get(chunk_id)
            if bm25_document is None:
                continue
            document_id = bm25_document.document_id
            filename = bm25_document.filename
            heading_path = bm25_document.heading_path
            content = bm25_document.content
        else:
            pair = found_rows.get(chunk_id)
            if pair is None:
                continue
            chunk, row_document = pair
            document_id = row_document.id
            filename = row_document.filename
            heading_path = chunk.heading_path
            content = chunk.content
        candidates.append(
            RetrievedChunk(
                number="",
                source=SourceCitation(
                    document_id=document_id,
                    filename=filename,
                    chunk_id=chunk_id,
                    heading_path=heading_path,
                    content=content,
                    score=score,
                ),
            )
        )

    if not settings.rerank_enabled:
        eligible = [item for item in candidates if item.source.score >= threshold]
        return _renumber_chunks(eligible[:5])

    return await _rerank_candidates(query, candidates, settings)


async def _get_bm25_corpus(
    session: AsyncSession, user_id: uuid.UUID, settings: Settings
) -> tuple[Bm25Index, tuple[Bm25Document, ...]] | None:
    now = time.monotonic()
    fingerprint = await _bm25_fingerprint(session, user_id)
    if fingerprint[0] > settings.bm25_cache_max_chunks:
        logger.warning(
            "BM25 corpus exceeds configured limit; using vector-only retrieval for user %s",
            user_id,
        )
        _BM25_CACHE.pop(user_id, None)
        return None
    cached = _BM25_CACHE.get(user_id)
    if (
        cached is not None
        and cached.expires_at > now
        and cached.fingerprint == fingerprint
    ):
        _BM25_CACHE.move_to_end(user_id)
        return cached.index, cached.documents

    rows = (
        await session.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Document.user_id == user_id,
                Document.status == DocumentStatus.COMPLETED,
            )
        )
    ).all()
    documents = tuple(
        Bm25Document(
            chunk_id=chunk.id,
            document_id=document.id,
            filename=document.filename,
            heading_path=chunk.heading_path,
            content=chunk.content,
        )
        for chunk, document in rows
    )
    index = Bm25Index(documents)
    if len(documents) <= settings.bm25_cache_max_chunks:
        _BM25_CACHE[user_id] = _CachedBm25Corpus(
            index=index,
            documents=documents,
            fingerprint=fingerprint,
            expires_at=now + settings.bm25_cache_ttl_seconds,
        )
        _BM25_CACHE.move_to_end(user_id)
        while len(_BM25_CACHE) > settings.bm25_cache_max_users:
            _BM25_CACHE.popitem(last=False)
    else:
        _BM25_CACHE.pop(user_id, None)
    return index, documents


async def _bm25_fingerprint(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[int, datetime | None]:
    result = await session.execute(
        select(func.count(Chunk.id), func.max(Document.updated_at))
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.user_id == user_id,
            Document.status == DocumentStatus.COMPLETED,
        )
    )
    count, latest_updated_at = result.one()
    return int(count), latest_updated_at


def _fuse_hybrid_hits(
    vector_hits: Sequence[tuple[uuid.UUID, float]],
    bm25_hits: Sequence[Bm25Hit],
    vector_weight: float,
    bm25_weight: float,
    limit: int,
) -> list[tuple[uuid.UUID, float]]:
    """Fuse absolute vector scores with max-normalized BM25 scores."""
    total_weight = vector_weight + bm25_weight
    if total_weight <= 0 or limit <= 0:
        return []
    vector_scores = {chunk_id: max(0.0, min(1.0, score)) for chunk_id, score in vector_hits}
    bm25_scores = {hit.chunk_id: hit.score for hit in bm25_hits}
    max_bm25 = max(bm25_scores.values(), default=0.0)
    ordered_ids = list(dict.fromkeys([*vector_scores, *bm25_scores]))
    bm25_scale = max_bm25 if max_bm25 > 0 else 1.0
    fused = [
        (
            chunk_id,
            (
                vector_weight * vector_scores.get(chunk_id, 0.0)
                + bm25_weight * (bm25_scores.get(chunk_id, 0.0) / bm25_scale)
            )
            / total_weight,
        )
        for chunk_id in ordered_ids
    ]
    return sorted(fused, key=lambda item: item[1], reverse=True)[:limit]


async def _rerank_candidates(
    query: str, candidates: Sequence[RetrievedChunk], settings: Settings
) -> list[RetrievedChunk]:
    try:
        rerank_scores = await RerankClient(settings).rerank(
            query,
            [item.source.content for item in candidates],
            top_n=settings.rerank_top_n,
        )
    except RerankError:
        logger.warning("rerank failed; falling back to vector ranking", exc_info=True)
        eligible = [
            item for item in candidates if item.source.score >= settings.retrieval_score_threshold
        ]
        return _renumber_chunks(eligible[:5])

    return _apply_rerank(candidates, rerank_scores, settings.rerank_score_threshold)


def _renumber_chunks(chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(number=str(index), source=item.source)
        for index, item in enumerate(chunks, start=1)
    ]


def _apply_rerank(
    candidates: Sequence[RetrievedChunk],
    scores: Sequence[RerankScore],
    score_threshold: float,
) -> list[RetrievedChunk]:
    reranked: list[RetrievedChunk] = []
    for result in sorted(scores, key=lambda item: item.score, reverse=True):
        if result.score < score_threshold:
            continue
        if result.index >= len(candidates):
            logger.warning("ignoring rerank result with invalid index: %s", result.index)
            continue
        source = candidates[result.index].source.model_copy(update={"score": result.score})
        reranked.append(RetrievedChunk(number="", source=source))
        if len(reranked) == 5:
            break
    return _renumber_chunks(reranked)


def _context(chunks: Sequence[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{item.number}]\n文档：{item.source.filename}\n标题路径：{item.source.heading_path}\n内容：{item.source.content}"
        for item in chunks
    )


def _validated_rag_answer(
    result: RagAnswerResult, retrieved: Sequence[RetrievedChunk]
) -> tuple[str, list[SourceCitation], bool]:
    chosen = {item.number: item.source for item in retrieved}
    valid_citations = [number for number in result.citations if number in chosen]
    sources = [chosen[number] for number in valid_citations]
    if not sources:
        return NO_ANSWER, [], True

    valid_set = set(valid_citations)
    answer = re.sub(
        r"\[([1-5])\]",
        lambda match: match.group(0) if match.group(1) in valid_set else "",
        result.answer,
    )
    for number in valid_citations:
        if f"[{number}]" not in answer:
            answer = f"{answer} [{number}]"
    return answer, sources, result.need_human


async def _save_log(
    session: AsyncSession,
    request_id: str,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    query: str,
    rewritten_query: str,
    intent: Intent,
    retrieved: list[RetrievedChunk],
    tool_summaries: list[ToolCallSummary],
    started: float,
    status_code: int = 200,
    error_message: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    session.add(
        RequestLog(
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            path="/api/v1/chat",
            method="POST",
            query=redact_text(query),
            rewritten_query=redact_text(rewritten_query),
            intent=intent.value,
            retrieved_chunks=[item.source.model_dump(mode="json") for item in retrieved],
            tool_calls=[item.model_dump(mode="json") for item in tool_summaries],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status_code=status_code,
            error_message=redact_text(error_message),
        )
    )


async def _tool_answer(
    session: AsyncSession,
    user: User,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    query: str,
    history: list[tuple[str, str]],
    intent: Intent,
    llm: LlmClient,
    rewritten_query: str | None = None,
) -> tuple[str, bool, list[ToolCallSummary]]:
    decision = await llm.structured(
        TOOL_DECISION_PROMPT_V1.format(
            query=rewritten_query or query, history=render_history(history)
        ),
        ToolDecision,
    )
    expected = {
        Intent.ORDER_QUERY: "query_order",
        Intent.LOGISTICS_QUERY: "query_logistics",
        Intent.TRANSFER_HUMAN: "transfer_to_human",
    }[intent]
    arguments = dict(decision.arguments)
    transfer_answer: str | None = None
    if expected in {"query_order", "query_logistics"}:
        order_id = _explicit_order_id(query) or _history_order_id(history)
        if order_id is None:
            return "请提供您的订单号，我会为您查询相关信息。", False, []
        # Model output never authorizes an order lookup: use only current or
        # prior user messages in this same conversation.
        arguments["order_id"] = order_id
    if expected == "transfer_to_human":
        transfer = await llm.structured(
            TRANSFER_HUMAN_PROMPT_V1.format(
                query=rewritten_query or query, history=render_history(history)
            ),
            TransferHumanResult,
        )
        transfer_answer = transfer.answer
        arguments = {"reason": transfer.ticket_reason, "conversation_id": conversation_id}

    started = time.perf_counter()

    async def record_call(
        tool_output: dict[str, object], status: ToolCallStatus, error_message: str | None
    ) -> ToolCallSummary:
        call = ToolCall(
            conversation_id=conversation_id,
            message_id=message_id,
            tool_name=expected,
            tool_input=redact_json(jsonable_encoder(arguments)),
            tool_output=redact_json(tool_output),
            status=status,
            error_message=error_message,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        session.add(call)
        await session.flush()
        return ToolCallSummary(tool_call_id=call.id, tool_name=expected, status=call.status)

    try:
        result: QueryOrderResult | QueryLogisticsResult | TransferToHumanResult | ToolErrorResult
        if expected == "query_order":
            result = await asyncio.wait_for(
                query_order(session, user.id, QueryOrderArgs.model_validate(arguments)),
                timeout=get_settings().tool_timeout_seconds,
            )
        elif expected == "query_logistics":
            result = await asyncio.wait_for(
                query_logistics(session, user.id, QueryLogisticsArgs.model_validate(arguments)),
                timeout=get_settings().tool_timeout_seconds,
            )
        else:
            result = await asyncio.wait_for(
                transfer_to_human(session, user.id, TransferToHumanArgs.model_validate(arguments)),
                timeout=get_settings().tool_timeout_seconds,
            )
        if isinstance(result, ToolErrorResult):
            call_status = ToolCallStatus.FAILED
            error_message = result.error_message
        else:
            call_status = ToolCallStatus.SUCCESS
            error_message = None
        summary = await record_call(
            result.model_dump(mode="json"), call_status, error_message
        )
        if expected == "transfer_to_human" and not isinstance(result, ToolErrorResult):
            if transfer_answer is not None:
                return transfer_answer, True, [summary]
            return "已为您创建人工客服工单，客服人员会尽快与您联系。", True, [summary]
        if isinstance(result, ToolErrorResult):
            return "抱歉，没有查询到相关信息，请核对订单号或联系人工客服。", False, [summary]
        answer = await llm.text(
            TOOL_SUMMARY_PROMPT_V1.format(
                query=query, tool_output=compact_json(result.model_dump(mode="json"))
            )
        )
        return answer, False, [summary]
    except ValidationError:
        summary = await record_call(
            {"error_code": "INVALID_ARGUMENT", "error_message": "参数格式错误"},
            ToolCallStatus.FAILED,
            "参数格式错误",
        )
        return "订单号格式不正确，请提供由字母、数字或连字符组成的订单号。", False, [summary]
    except TimeoutError:
        summary = await record_call(
            {"error_code": "TOOL_TIMEOUT", "error_message": "工具响应超时"},
            ToolCallStatus.TIMEOUT,
            "工具响应超时",
        )
        return "抱歉，查询超时，请稍后重试或联系人工客服。", False, [summary]
    except Exception:
        summary = await record_call(
            {"error_code": "TOOL_UNAVAILABLE", "error_message": "工具暂时不可用"},
            ToolCallStatus.FAILED,
            "工具执行失败",
        )
        return (
            "抱歉，暂时无法查询到相关信息，请稍后重试或联系人工客服。",
            False,
            [summary],
        )


async def answer_chat(
    session: AsyncSession, user: User, conversation_id: uuid.UUID, query: str, request_id: str
) -> ChatResponse:
    started = time.perf_counter()
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    if conversation is None:
        raise ConversationNotFoundError("conversation not found")
    history = await _history(session, conversation_id)
    user_message = Message(conversation_id=conversation_id, role=MessageRole.USER, content=query)
    session.add(user_message)
    await session.flush()

    preclassified = _preclassified_reply(query)
    rewritten = query
    retrieved: list[RetrievedChunk] = []
    tool_summaries: list[ToolCallSummary] = []
    sources: list[SourceCitation] = []
    need_human = False
    try:
        if preclassified:
            intent, answer = preclassified
        else:
            llm = LlmClient()
            rewrite = await llm.structured(
                QUERY_REWRITE_PROMPT_V1.format(history=render_history(history), query=query),
                RewriteResult,
            )
            rewritten = rewrite.rewritten_query
            intent = (
                await llm.structured(
                    INTENT_PROMPT_V1.format(history=render_history(history), query=rewritten),
                    IntentDecision,
                )
            ).intent
            intent = _resolve_explicit_tool_intent(intent, rewritten)
            if intent in {Intent.SENSITIVE, Intent.IRRELEVANT}:
                answer = SENSITIVE_REPLY if intent == Intent.SENSITIVE else IRRELEVANT_REPLY
            elif intent in {Intent.ORDER_QUERY, Intent.LOGISTICS_QUERY, Intent.TRANSFER_HUMAN}:
                answer, need_human, tool_summaries = await _tool_answer(
                    session,
                    user,
                    conversation_id,
                    user_message.id,
                    query,
                    history,
                    intent,
                    llm,
                    rewritten,
                )
                assistant_message = Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                    sources=[],
                    prompt_version=(
                        TRANSFER_HUMAN_PROMPT_VERSION
                        if intent == Intent.TRANSFER_HUMAN
                        else TOOL_SUMMARY_PROMPT_VERSION
                    ),
                )
                session.add(assistant_message)
                await _save_log(
                    session,
                    request_id,
                    user.id,
                    conversation_id,
                    query,
                    rewritten,
                    intent,
                    [],
                    tool_summaries,
                    started,
                    prompt_tokens=llm.prompt_tokens,
                    completion_tokens=llm.completion_tokens,
                )
                await session.commit()
                return ChatResponse(
                    conversation_id=conversation_id,
                    answer=answer,
                    sources=[],
                    intent=intent,
                    rewritten_query=rewritten,
                    need_human=need_human,
                    tool_calls=tool_summaries,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            else:
                retrieved = await _retrieve(session, user.id, rewritten, llm)
                if not retrieved:
                    answer, need_human = NO_ANSWER, True
                else:
                    result = await llm.structured(
                        RAG_ANSWER_PROMPT_V1.format(
                            context=_context(retrieved), question=rewritten
                        ),
                        RagAnswerResult,
                    )
                    answer, sources, need_human = _validated_rag_answer(result, retrieved)
        assistant_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            sources=[source.model_dump(mode="json") for source in sources],
            prompt_version=RAG_ANSWER_PROMPT_VERSION if sources else None,
        )
        session.add(assistant_message)
        await _save_log(
            session,
            request_id,
            user.id,
            conversation_id,
            query,
            rewritten,
            intent,
            retrieved,
            tool_summaries,
            started,
            prompt_tokens=llm.prompt_tokens if not preclassified else None,
            completion_tokens=llm.completion_tokens if not preclassified else None,
        )
        await session.commit()
        return ChatResponse(
            conversation_id=conversation_id,
            answer=answer,
            sources=sources,
            intent=intent,
            rewritten_query=rewritten,
            need_human=need_human,
            tool_calls=tool_summaries,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    except (LlmOutputError, TimeoutError):
        await session.rollback()
        raise
