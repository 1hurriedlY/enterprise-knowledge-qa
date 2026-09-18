"""Read-only audit endpoints restricted to administrators."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.domain import MessageRole
from app.models import Conversation, Message, RequestLog, ToolCall, User
from app.schemas import (
    AdminConversationListResponse,
    AdminConversationResponse,
    MessageListResponse,
    MessageResponse,
    RequestLogListResponse,
    RequestLogResponse,
    SourceCitation,
    ToolCallListResponse,
    ToolCallResponse,
)
from app.services.auth import admin_user
from app.services.redaction import redact_json, redact_text

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
PageSize = Annotated[int, Query(ge=1, le=200, description="Maximum records to return")]


@router.get(
    "/conversations",
    response_model=AdminConversationListResponse,
    summary="查询所有会话记录",
    description="仅管理员可访问，按最后更新时间倒序返回。",
)
async def list_conversations(
    limit: PageSize = 50,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
) -> AdminConversationListResponse:
    records = (
        await session.scalars(
            select(Conversation).order_by(desc(Conversation.updated_at)).limit(limit)
        )
    ).all()
    return AdminConversationListResponse(
        conversations=[
            AdminConversationResponse(
                conversation_id=record.id,
                user_id=record.user_id,
                title=record.title,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in records
        ]
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="查询指定会话的消息记录",
    description="仅管理员可访问；返回用户、助手、工具和系统消息，内容会脱敏。",
)
async def list_conversation_messages(
    conversation_id: uuid.UUID,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
) -> MessageListResponse:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    records = (
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    ).all()
    return MessageListResponse(
        messages=[
            MessageResponse(
                role=record.role,
                content=redact_text(record.content) or "",
                sources=[
                    SourceCitation.model_validate(redact_json(source)) for source in record.sources
                ],
                created_at=record.created_at,
            )
            for record in records
            if record.role
            in {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL, MessageRole.SYSTEM}
        ]
    )


@router.get(
    "/logs",
    response_model=RequestLogListResponse,
    summary="查询请求审计日志",
    description="仅管理员可访问，按创建时间倒序返回；敏感文本会被脱敏。",
)
async def list_request_logs(
    limit: PageSize = 50,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
) -> RequestLogListResponse:
    records = (
        await session.scalars(select(RequestLog).order_by(desc(RequestLog.created_at)).limit(limit))
    ).all()
    return RequestLogListResponse(
        logs=[
            RequestLogResponse(
                request_id=record.request_id,
                user_id=record.user_id,
                conversation_id=record.conversation_id,
                query=redact_text(record.query),
                intent=record.intent,
                latency_ms=record.latency_ms,
                status_code=record.status_code,
                created_at=record.created_at,
            )
            for record in records
        ]
    )


@router.get(
    "/tool-calls",
    response_model=ToolCallListResponse,
    summary="查询工具调用审计记录",
    description="仅管理员可访问，按创建时间倒序返回；工具输入与输出会脱敏。",
)
async def list_tool_calls(
    limit: PageSize = 50,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
) -> ToolCallListResponse:
    records = (
        await session.scalars(select(ToolCall).order_by(desc(ToolCall.created_at)).limit(limit))
    ).all()
    return ToolCallListResponse(
        tool_calls=[
            ToolCallResponse(
                tool_call_id=record.id,
                conversation_id=record.conversation_id,
                tool_name=record.tool_name,
                tool_input=redact_json(record.tool_input),
                tool_output=redact_json(record.tool_output),
                status=record.status,
                error_message=redact_text(record.error_message),
                latency_ms=record.latency_ms,
                created_at=record.created_at,
            )
            for record in records
        ]
    )
