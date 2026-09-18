import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain import Confidence, DocumentStatus, Intent, MessageRole, ToolCallStatus

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OrderId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$",
    ),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentUploadResponse(StrictModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus


class DocumentListItem(StrictModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus
    chunk_count: int
    created_at: datetime
    error_message: str | None = None


class DocumentListResponse(StrictModel):
    documents: list[DocumentListItem]


class DeleteDocumentResponse(StrictModel):
    document_id: uuid.UUID
    status: Literal["deleted"]


class CreateConversationRequest(StrictModel):
    user_id: uuid.UUID
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CreateConversationResponse(StrictModel):
    conversation_id: uuid.UUID
    title: str
    created_at: datetime


class SourceCitation(StrictModel):
    document_id: uuid.UUID
    filename: str
    chunk_id: uuid.UUID
    heading_path: str
    content: str
    score: float = Field(ge=0, le=1)


class ToolCallSummary(StrictModel):
    tool_call_id: uuid.UUID
    tool_name: str
    status: ToolCallStatus


class ChatRequest(StrictModel):
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ChatResponse(StrictModel):
    conversation_id: uuid.UUID
    answer: str
    sources: list[SourceCitation]
    intent: Intent
    rewritten_query: str
    need_human: bool
    tool_calls: list[ToolCallSummary]
    latency_ms: int = Field(ge=0)


class MessageResponse(StrictModel):
    role: MessageRole
    content: str
    sources: list[SourceCitation] = Field(default_factory=list)
    created_at: datetime


class MessageListResponse(StrictModel):
    messages: list[MessageResponse]


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    app: Literal["ok"]
    database: Literal["ok", "error"]
    vector_db: Literal["ok", "error"]
    llm: Literal["ok", "error"]
    redis: Literal["ok", "error"]


class RequestLogResponse(StrictModel):
    request_id: str
    user_id: uuid.UUID | None
    query: str | None
    intent: str | None
    latency_ms: int
    status_code: int
    created_at: datetime


class RequestLogListResponse(StrictModel):
    logs: list[RequestLogResponse]


class ToolCallResponse(StrictModel):
    tool_call_id: uuid.UUID
    conversation_id: uuid.UUID
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any]
    status: ToolCallStatus
    latency_ms: int


class ToolCallListResponse(StrictModel):
    tool_calls: list[ToolCallResponse]


class RewriteResult(StrictModel):
    rewritten_query: NonEmptyText
    reason: str


class IntentDecision(StrictModel):
    intent: Intent
    confidence: Confidence
    reason: str


class ToolDecision(StrictModel):
    need_tool: bool
    tool_name: Literal["query_order", "query_logistics", "transfer_to_human"] | None
    arguments: dict[str, Any]
    ask_user: str
    reason: str

    @field_validator("tool_name")
    @classmethod
    def require_tool_for_request(cls, value: str | None, info: Any) -> str | None:
        if info.data.get("need_tool") and value is None:
            raise ValueError("tool_name is required when need_tool is true")
        return value


class RagAnswerResult(StrictModel):
    answer: NonEmptyText
    citations: list[Annotated[str, StringConstraints(pattern=r"^[1-5]$")]] = Field(
        default_factory=list, max_length=5
    )
    confidence: Confidence
    need_human: bool

    @field_validator("citations")
    @classmethod
    def citations_must_be_unique(cls, citations: list[str]) -> list[str]:
        if len(citations) != len(set(citations)):
            raise ValueError("citations must not contain duplicates")
        return citations


class TransferHumanResult(StrictModel):
    answer: NonEmptyText
    ticket_reason: NonEmptyText


class QueryOrderArgs(StrictModel):
    order_id: OrderId


class QueryOrderResult(StrictModel):
    order_id: str
    status: str
    amount: float
    created_at: datetime


class QueryLogisticsArgs(StrictModel):
    order_id: OrderId


class QueryLogisticsResult(StrictModel):
    order_id: str
    logistics: list[str]


class TransferToHumanArgs(StrictModel):
    reason: NonEmptyText
    conversation_id: uuid.UUID


class TransferToHumanResult(StrictModel):
    ticket_id: uuid.UUID
    status: Literal["created"]


class ToolErrorResult(StrictModel):
    error_code: str
    error_message: str
