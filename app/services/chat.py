import asyncio
import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain import Intent, MessageRole, ToolCallStatus
from app.models import Chunk, Conversation, Document, Message, RequestLog, ToolCall, User
from app.prompts import (
    INTENT_PROMPT_V1,
    QUERY_REWRITE_PROMPT_V1,
    RAG_ANSWER_PROMPT_V1,
    RAG_ANSWER_PROMPT_VERSION,
    TOOL_DECISION_PROMPT_V1,
    TOOL_SUMMARY_PROMPT_V1,
    TOOL_SUMMARY_PROMPT_VERSION,
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
    TransferToHumanArgs,
    TransferToHumanResult,
)
from app.services.llm import LlmClient, LlmOutputError, compact_json, render_history
from app.services.redaction import redact_json, redact_text
from app.services.tools import query_logistics, query_order, transfer_to_human
from app.services.vector_store import VectorStore

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
    vector = await llm.embed(query)
    hits = await VectorStore().search(user_id, vector, limit=10)
    threshold = get_settings().retrieval_score_threshold
    hit_scores = {chunk_id: score for chunk_id, score in hits if score >= threshold}
    if not hit_scores:
        return []
    rows = (
        await session.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(hit_scores), Document.user_id == user_id)
        )
    ).all()
    found = {chunk.id: (chunk, document) for chunk, document in rows}
    results: list[RetrievedChunk] = []
    for index, (chunk_id, score) in enumerate(hits, start=1):
        pair = found.get(chunk_id)
        if pair is None or score < threshold or len(results) == 5:
            continue
        chunk, document = pair
        results.append(
            RetrievedChunk(
                number=str(index),
                source=SourceCitation(
                    document_id=document.id,
                    filename=document.filename,
                    chunk_id=chunk.id,
                    heading_path=chunk.heading_path,
                    content=chunk.content,
                    score=score,
                ),
            )
        )
    return results


def _context(chunks: Sequence[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{item.number}]\n文档：{item.source.filename}\n标题路径：{item.source.heading_path}\n内容：{item.source.content}"
        for item in chunks
    )


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
) -> tuple[str, bool, list[ToolCallSummary]]:
    decision = await llm.structured(
        TOOL_DECISION_PROMPT_V1.format(query=query, history=render_history(history)), ToolDecision
    )
    expected = {
        Intent.ORDER_QUERY: "query_order",
        Intent.LOGISTICS_QUERY: "query_logistics",
        Intent.TRANSFER_HUMAN: "transfer_to_human",
    }[intent]
    arguments = dict(decision.arguments)
    if expected in {"query_order", "query_logistics"}:
        order_id = _explicit_order_id(query)
        if order_id is None:
            return "请提供您的订单号，我会为您查询相关信息。", False, []
        # Do not trust an order number invented by the model. In this first
        # version, an order lookup is permitted only for an ID explicit in the
        # current user message.
        arguments["order_id"] = order_id
    if expected == "transfer_to_human":
        arguments = {"reason": arguments.get("reason") or query, "conversation_id": conversation_id}

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
                    session, user, conversation_id, user_message.id, query, history, intent, llm
                )
                assistant_message = Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                    sources=[],
                    prompt_version=TOOL_SUMMARY_PROMPT_VERSION,
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
                    chosen = {item.number: item.source for item in retrieved}
                    sources = [chosen[number] for number in result.citations if number in chosen]
                    if not sources:
                        answer, need_human = NO_ANSWER, True
                    else:
                        answer, need_human = result.answer, result.need_human
                        for number in result.citations:
                            if f"[{number}]" not in answer:
                                answer = f"{answer} [{number}]"
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
