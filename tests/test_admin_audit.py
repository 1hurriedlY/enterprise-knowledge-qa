import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domain import ToolCallStatus, UserRole
from app.models import RequestLog, ToolCall, User
from app.routers.admin import list_request_logs, list_tool_calls
from app.services.auth import admin_user


class FakeAuditSession:
    def __init__(self, records: list[object]) -> None:
        self.records = records

    async def scalars(self, _: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.records)


def _admin() -> User:
    return User(name="Admin", email="admin@example.com", role=UserRole.ADMIN)


@pytest.mark.asyncio
async def test_admin_audit_endpoints_redact_secret_like_values() -> None:
    now = datetime.now(UTC)
    conversation_id = uuid.uuid4()
    request_log = RequestLog(
        request_id=str(uuid.uuid4()),
        user_id=uuid.uuid4(),
        conversation_id=conversation_id,
        path="/api/v1/chat",
        method="POST",
        query="api_key=sk-secret-token-12345678 查询订单",
        rewritten_query="查询订单",
        intent="order_query",
        retrieved_chunks=[],
        tool_calls=[],
        latency_ms=12,
        status_code=200,
        created_at=now,
    )
    tool_call = ToolCall(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        message_id=uuid.uuid4(),
        tool_name="query_order",
        tool_input={"api_key": "unprefixed-secret", "order_id": "12345"},
        tool_output={"status": "已发货"},
        status=ToolCallStatus.SUCCESS,
        latency_ms=3,
        created_at=now,
    )

    logs = await list_request_logs(
        limit=50, _=_admin(), session=FakeAuditSession([request_log])  # type: ignore[arg-type]
    )
    calls = await list_tool_calls(
        limit=50, _=_admin(), session=FakeAuditSession([tool_call])  # type: ignore[arg-type]
    )

    assert "sk-secret" not in (logs.logs[0].query or "")
    assert calls.tool_calls[0].tool_input["api_key"] == "[REDACTED]"
    assert calls.tool_calls[0].tool_input["order_id"] == "12345"


@pytest.mark.asyncio
async def test_non_admin_is_denied_before_audit_query() -> None:
    user = User(name="User", email="user@example.com", role=UserRole.USER)
    with pytest.raises(HTTPException) as exc_info:
        await admin_user(user)
    assert exc_info.value.status_code == 403
