"""Read-only audit endpoints restricted to administrators."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import RequestLog, ToolCall, User
from app.schemas import (
    RequestLogListResponse,
    RequestLogResponse,
    ToolCallListResponse,
    ToolCallResponse,
)
from app.services.auth import admin_user
from app.services.redaction import redact_json, redact_text

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
PageSize = Annotated[int, Query(ge=1, le=200, description="Maximum records to return")]


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
