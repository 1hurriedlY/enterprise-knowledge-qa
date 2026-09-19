"""Authenticated conversation and knowledge-base answer endpoints."""

import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.database import get_session
from app.domain import MessageRole
from app.models import Conversation, Message, User
from app.schemas import (
    ChatRequest,
    ChatResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    MessageListResponse,
    MessageResponse,
    SourceCitation,
)
from app.services.audit import persist_request_audit
from app.services.auth import current_user, require_same_user
from app.services.chat import ConversationNotFoundError, answer_chat
from app.services.llm import LlmOutputError

router = APIRouter(tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
SSE_CHUNK_SIZE = 24


def _sse_event(event: str, payload: dict[str, object]) -> bytes:
    """Encode one Server-Sent Event without allowing multiline data injection."""
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n".encode()


def _answer_chunks(answer: str) -> list[str]:
    """Split an already validated answer into readable, ordered SSE deltas."""
    chunks: list[str] = []
    remaining = answer
    preferred_breaks = "。！？；，\n"
    while len(remaining) > SSE_CHUNK_SIZE:
        boundary = max(remaining.rfind(mark, 0, SSE_CHUNK_SIZE) for mark in preferred_breaks)
        boundary = boundary + 1 if boundary >= 0 else SSE_CHUNK_SIZE
        chunks.append(remaining[:boundary])
        remaining = remaining[boundary:]
    if remaining:
        chunks.append(remaining)
    return chunks


async def _stream_chat_response(
    *,
    session: AsyncSession,
    user: User,
    payload: ChatRequest,
    request_id: str,
    started: float,
) -> AsyncIterator[bytes]:
    """Run the normal safe chat pipeline once, then progressively deliver it."""
    try:
        response = await answer_chat(
            session=session,
            user=user,
            conversation_id=payload.conversation_id,
            query=payload.query,
            request_id=request_id,
        )
        for chunk in _answer_chunks(response.answer):
            yield _sse_event("delta", {"content": chunk})
        complete = response.model_dump(mode="json")
        complete.pop("answer")
        yield _sse_event("complete", complete)
    except ConversationNotFoundError:
        await persist_request_audit(
            request_id=request_id,
            user_id=user.id,
            path="/api/v1/chat/stream",
            method="POST",
            query=payload.query,
            started=started,
            status_code=status.HTTP_404_NOT_FOUND,
            error_message="会话不存在",
        )
        yield _sse_event("error", {"message": "会话不存在，请开始新的会话。"})
    except (LlmOutputError, TimeoutError):
        await session.rollback()
        await persist_request_audit(
            request_id=request_id,
            user_id=user.id,
            path="/api/v1/chat/stream",
            method="POST",
            query=payload.query,
            started=started,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_message="智能客服暂时无法处理",
        )
        yield _sse_event("error", {"message": "智能客服暂时无法处理，请稍后重试或转接人工客服。"})
    except Exception:
        await session.rollback()
        await persist_request_audit(
            request_id=request_id,
            user_id=user.id,
            path="/api/v1/chat/stream",
            method="POST",
            query=payload.query,
            started=started,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_message="流式问答处理失败",
        )
        yield _sse_event("error", {"message": "智能客服暂时无法处理，请稍后重试或转接人工客服。"})


@router.post(
    "/api/v1/conversations",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: CreateConversationRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CreateConversationResponse:
    require_same_user(user, payload.user_id)
    conversation = Conversation(user_id=user.id, title=payload.title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return CreateConversationResponse(
        conversation_id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
    )


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    require_same_user(user, payload.user_id)
    try:
        response = await answer_chat(
            session=session,
            user=user,
            conversation_id=payload.conversation_id,
            query=payload.query,
            request_id=getattr(request.state, "request_id", str(uuid.uuid4())),
        )
        request.state.audit_logged = True
        return response
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在") from exc
    except (LlmOutputError, TimeoutError) as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能客服暂时无法处理，请稍后重试或转接人工客服",
        ) from exc


@router.post(
    "/api/v1/chat/stream",
    responses={
        200: {"content": {"text/event-stream": {}}},
        401: {"description": "API Key 无效或缺失"},
        403: {"description": "请求 user_id 与 API Key 身份不一致"},
    },
)
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Return a validated chat response progressively over Server-Sent Events.

    This endpoint deliberately streams only *after* the usual RAG/tool pipeline
    has completed validation. It therefore preserves citation and prompt-safety
    guarantees while giving the browser progressive rendering.
    """
    require_same_user(user, payload.user_id)
    request.state.audit_logged = True
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    started = time.perf_counter()
    return StreamingResponse(
        _stream_chat_response(
            session=session,
            user=user,
            payload=payload,
            request_id=request_id,
            started=started,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/api/v1/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageListResponse:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    messages = (
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    ).all()
    return MessageListResponse(
        messages=[
            MessageResponse(
                role=message.role,
                content=message.content,
                sources=[SourceCitation.model_validate(source) for source in message.sources],
                created_at=message.created_at,
            )
            for message in messages
            if message.role in {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL}
        ]
    )
