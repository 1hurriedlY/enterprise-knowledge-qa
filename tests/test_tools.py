import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.domain import Intent, ToolCallStatus
from app.models import Order, ToolCall
from app.schemas import (
    QueryLogisticsArgs,
    QueryOrderArgs,
    ToolDecision,
    ToolErrorResult,
    TransferHumanResult,
    TransferToHumanResult,
)
from app.services import chat as chat_service
from app.services.chat import _explicit_order_id, _history_order_id, _resolve_explicit_tool_intent
from app.services.tools import query_logistics, query_order


class FakeToolSession:
    def __init__(
        self, scalar_values: list[object | None], event_rows: list[str] | None = None
    ) -> None:
        self.scalar_values = scalar_values
        self.event_rows = event_rows or []
        self.added: list[object] = []

    async def scalar(self, _: object) -> object | None:
        return self.scalar_values.pop(0)

    async def scalars(self, _: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.event_rows)

    def add(self, value: object) -> None:
        if isinstance(value, ToolCall) and value.id is None:
            value.id = uuid.uuid4()
        self.added.append(value)

    async def flush(self) -> None:
        return None


def _order(user_id: uuid.UUID) -> Order:
    return Order(
        order_id="12345",
        user_id=user_id,
        status="已发货",
        amount=Decimal("99.00"),
        created_at=datetime(2026, 9, 16, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_order_and_logistics_tools_return_only_owned_data() -> None:
    user_id = uuid.uuid4()
    order_result = await query_order(
        FakeToolSession([_order(user_id)]), user_id, QueryOrderArgs(order_id="12345")
    )
    logistics_result = await query_logistics(
        FakeToolSession([_order(user_id)], ["已发货", "正在派送中"]),
        user_id,
        QueryLogisticsArgs(order_id="12345"),
    )
    missing_result = await query_order(
        FakeToolSession([None]), user_id, QueryOrderArgs(order_id="12345")
    )

    assert order_result.order_id == "12345"  # type: ignore[union-attr]
    assert logistics_result.logistics == ["已发货", "正在派送中"]  # type: ignore[union-attr]
    assert isinstance(missing_result, ToolErrorResult)
    assert missing_result.error_code == "ORDER_NOT_FOUND"


def test_order_id_schema_rejects_malformed_values_and_unknown_tools() -> None:
    with pytest.raises(ValidationError):
        QueryOrderArgs(order_id="bad id!")
    with pytest.raises(ValidationError):
        ToolDecision(
            need_tool=True,
            tool_name="erase_everything",
            arguments={},
            ask_user="",
            reason="bad model output",
        )


@pytest.mark.parametrize(
    ("model_intent", "query", "expected"),
    [
        (Intent.LOGISTICS_QUERY, "订单 12345 发货了吗？", Intent.ORDER_QUERY),
        (Intent.ORDER_QUERY, "订单 12345 到哪了？", Intent.LOGISTICS_QUERY),
        (Intent.TRANSFER_HUMAN, "我要人工客服", Intent.TRANSFER_HUMAN),
    ],
)
def test_clear_tool_words_correct_model_misclassification(
    model_intent: Intent, query: str, expected: Intent
) -> None:
    assert _resolve_explicit_tool_intent(model_intent, query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("我的订单 12345 发货了吗？", "12345"),
        ("查询订单号：ORD-123", "ORD-123"),
        ("order ABC-789", "ABC-789"),
        ("我的订单发货了吗？", None),
    ],
)
def test_explicit_order_id_uses_only_values_present_in_the_query(
    query: str, expected: str | None
) -> None:
    assert _explicit_order_id(query) == expected


def test_history_order_id_uses_a_prior_user_message_but_not_assistant_text() -> None:
    history = [
        ("user", "我的订单 12345 已发货了吗？"),
        ("assistant", "订单 99999 正在运输中。"),
    ]

    assert _history_order_id(history) == "12345"


class FakeDecisionLlm:
    async def structured(self, _: str, result_type: object) -> ToolDecision | TransferHumanResult:
        if result_type is TransferHumanResult:
            return TransferHumanResult(answer="已创建人工工单。", ticket_reason="用户需要人工客服")
        return ToolDecision(
            need_tool=True,
            tool_name="query_order",
            arguments={"order_id": "12345"},
            ask_user="",
            reason="test",
        )


@pytest.mark.asyncio
async def test_tool_timeout_is_logged_without_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_query(*_: object) -> object:
        await asyncio.sleep(0.05)
        raise AssertionError("should time out first")

    monkeypatch.setattr(chat_service, "query_order", slow_query)
    monkeypatch.setattr(
        chat_service, "get_settings", lambda: SimpleNamespace(tool_timeout_seconds=0.001)
    )
    session = FakeToolSession([])
    answer, need_human, calls = await chat_service._tool_answer(
        session=session,
        user=SimpleNamespace(id=uuid.uuid4()),
        conversation_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        query="订单 12345 发货了吗？",
        history=[],
        intent=Intent.ORDER_QUERY,
        llm=FakeDecisionLlm(),
    )

    assert "超时" in answer
    assert need_human is False
    assert calls[0].status == ToolCallStatus.TIMEOUT
    assert isinstance(session.added[0], ToolCall)
    assert session.added[0].error_message == "工具响应超时"


@pytest.mark.asyncio
async def test_missing_order_number_never_uses_an_llm_invented_value() -> None:
    session = FakeToolSession([])
    answer, need_human, calls = await chat_service._tool_answer(
        session=session,
        user=SimpleNamespace(id=uuid.uuid4()),
        conversation_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        query="我的订单发货了吗？",
        history=[],
        intent=Intent.ORDER_QUERY,
        llm=FakeDecisionLlm(),
    )

    assert "订单号" in answer
    assert need_human is False
    assert calls == []
    assert session.added == []


@pytest.mark.asyncio
async def test_transfer_audit_serializes_conversation_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def successful_transfer(*_: object) -> TransferToHumanResult:
        return TransferToHumanResult(ticket_id=uuid.uuid4(), status="created")

    monkeypatch.setattr(chat_service, "transfer_to_human", successful_transfer)
    session = FakeToolSession([])
    conversation_id = uuid.uuid4()
    _, need_human, calls = await chat_service._tool_answer(
        session=session,
        user=SimpleNamespace(id=uuid.uuid4()),
        conversation_id=conversation_id,
        message_id=uuid.uuid4(),
        query="我要投诉，请转人工客服。",
        history=[],
        intent=Intent.TRANSFER_HUMAN,
        llm=FakeDecisionLlm(),
    )

    assert need_human is True
    assert calls[0].status == ToolCallStatus.SUCCESS
    assert isinstance(session.added[0], ToolCall)
    assert session.added[0].tool_input["conversation_id"] == str(conversation_id)
