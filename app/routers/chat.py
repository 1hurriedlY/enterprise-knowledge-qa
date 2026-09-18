"""Authenticated conversation and knowledge-base answer endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.auth import current_user, require_same_user
from app.services.chat import ConversationNotFoundError, answer_chat
from app.services.llm import LlmOutputError

router = APIRouter(tags=["chat"])


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
