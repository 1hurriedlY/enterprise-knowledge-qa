import uuid

import pytest
from pydantic import ValidationError

from app.domain import DocumentStatus, Intent, ToolCallStatus
from app.schemas import ChatRequest, SourceCitation, ToolDecision


def test_chat_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            query="如何申请退款？",
            unknown=True,
        )


def test_tool_decision_requires_a_tool_when_needed() -> None:
    with pytest.raises(ValidationError, match="tool_name is required"):
        ToolDecision(
            need_tool=True,
            tool_name=None,
            arguments={},
            ask_user="",
            reason="需要查询订单",
        )


def test_source_citation_enforces_score_bounds() -> None:
    with pytest.raises(ValidationError):
        SourceCitation(
            document_id=uuid.uuid4(),
            filename="退款政策.md",
            chunk_id=uuid.uuid4(),
            heading_path="退款政策 > 流程",
            content="退款内容",
            score=1.01,
        )


def test_domain_enums_use_api_values() -> None:
    assert DocumentStatus.PROCESSING.value == "processing"
    assert Intent.LOGISTICS_QUERY.value == "logistics_query"
    assert ToolCallStatus.TIMEOUT.value == "timeout"
