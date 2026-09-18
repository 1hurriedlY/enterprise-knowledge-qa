import uuid

from arq.connections import RedisSettings

from app.config import get_settings
from app.database import SessionLocal
from app.services.ingestion import ingest_document


async def ingest_document_job(_: dict[object, object], document_id: str) -> None:
    async with SessionLocal() as session:
        await ingest_document(session, uuid.UUID(document_id))


class WorkerSettings:
    functions = [ingest_document_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 600
