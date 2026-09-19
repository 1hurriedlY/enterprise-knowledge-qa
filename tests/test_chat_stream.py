import json
import uuid
from types import SimpleNamespace

import pytest

from app.domain import Intent
from app.routers import chat as chat_router
from app.schemas import ChatRequest, ChatResponse
from app.services.llm import LlmOutputError


def _payload() -> ChatRequest:
    return ChatRequest(user_id=uuid.uuid4(), conversation_id=uuid.uuid4(), query="退款如何办理？")


def _events(chunks: list[bytes]) -> list[tuple[str, dict[str, object]]]:
    result: list[tuple[str, dict[str, object]]] = []
    for chunk in chunks:
        event_line, data_line, _ = chunk.decode("utf-8").split("\n", maxsplit=2)
        result.append((event_line.removeprefix("event: "), json.loads(data_line[6:])))
    return result


@pytest.mark.asyncio
async def test_stream_delivers_validated_answer_before_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    response = ChatResponse(
        conversation_id=payload.conversation_id,
        answer="请在订单详情页提交退款申请，选择退款原因后确认提交；审核通过后退款会原路退回到账户。",
        sources=[],
        intent=Intent.KNOWLEDGE_QA,
        rewritten_query=payload.query,
        need_human=False,
        tool_calls=[],
        latency_ms=12,
    )

    async def fake_answer_chat(**_: object) -> ChatResponse:
        return response

    monkeypatch.setattr(chat_router, "answer_chat", fake_answer_chat)
    chunks = [
        chunk
        async for chunk in chat_router._stream_chat_response(
            session=SimpleNamespace(),
            user=SimpleNamespace(id=payload.user_id),
            payload=payload,
            request_id="request-1",
            started=1.0,
        )
    ]

    events = _events(chunks)
    assert all(event == "delta" for event, _ in events[:-1])
    assert events[-1][0] == "complete"
    assert "".join(str(data["content"]) for _, data in events[:-1]) == response.answer
    assert "answer" not in events[-1][1]
    assert events[-1][1]["conversation_id"] == str(payload.conversation_id)


@pytest.mark.asyncio
async def test_stream_hides_internal_model_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload()
    recorded: dict[str, object] = {}

    async def failing_answer_chat(**_: object) -> ChatResponse:
        raise LlmOutputError("provider private diagnostic")

    async def fake_persist_request_audit(**kwargs: object) -> None:
        recorded.update(kwargs)

    async def fake_rollback() -> None:
        recorded["rolled_back"] = True

    monkeypatch.setattr(chat_router, "answer_chat", failing_answer_chat)
    monkeypatch.setattr(chat_router, "persist_request_audit", fake_persist_request_audit)
    chunks = [
        chunk
        async for chunk in chat_router._stream_chat_response(
            session=SimpleNamespace(rollback=fake_rollback),
            user=SimpleNamespace(id=payload.user_id),
            payload=payload,
            request_id="request-2",
            started=1.0,
        )
    ]

    events = _events(chunks)
    assert events == [("error", {"message": "智能客服暂时无法处理，请稍后重试或转接人工客服。"})]
    assert recorded["status_code"] == 503
    assert recorded["rolled_back"] is True
    assert "private" not in json.dumps(events, ensure_ascii=False)


@pytest.mark.asyncio
async def test_stream_hides_unexpected_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload()
    recorded: dict[str, object] = {}

    async def failing_answer_chat(**_: object) -> ChatResponse:
        raise RuntimeError("database connection diagnostic")

    async def fake_persist_request_audit(**kwargs: object) -> None:
        recorded.update(kwargs)

    async def fake_rollback() -> None:
        return None

    monkeypatch.setattr(chat_router, "answer_chat", failing_answer_chat)
    monkeypatch.setattr(chat_router, "persist_request_audit", fake_persist_request_audit)
    chunks = [
        chunk
        async for chunk in chat_router._stream_chat_response(
            session=SimpleNamespace(rollback=fake_rollback),
            user=SimpleNamespace(id=payload.user_id),
            payload=payload,
            request_id="request-3",
            started=1.0,
        )
    ]

    events = _events(chunks)
    assert events[0][0] == "error"
    assert events[0][1]["message"] == "智能客服暂时无法处理，请稍后重试或转接人工客服。"
    assert recorded["status_code"] == 500
    assert "diagnostic" not in json.dumps(events, ensure_ascii=False)
