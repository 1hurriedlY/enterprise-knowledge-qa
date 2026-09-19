"""Best-effort request audit persistence isolated from HTTP middleware."""

import logging
import time
import uuid

from app.database import SessionLocal
from app.models import RequestLog
from app.services.redaction import redact_text

logger = logging.getLogger(__name__)


async def persist_request_audit(
    *,
    request_id: str,
    user_id: uuid.UUID | None,
    path: str,
    method: str,
    query: str,
    started: float,
    status_code: int,
    error_message: str | None,
) -> None:
    """Persist non-chat audit metadata without risking the business response."""
    try:
        async with SessionLocal() as session:
            session.add(
                RequestLog(
                    request_id=request_id,
                    user_id=user_id,
                    path=path,
                    method=method,
                    query=redact_text(query) or None,
                    retrieved_chunks=[],
                    tool_calls=[],
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    status_code=status_code,
                    error_message=redact_text(error_message),
                )
            )
            await session.commit()
    except Exception:
        # Keep audit degradation observable without adding request data to logs.
        logger.warning("request audit persistence failed: request_id=%s", request_id)
