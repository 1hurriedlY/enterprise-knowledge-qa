import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain import DocumentStatus, JobStatus
from app.models import Chunk, Document, Embedding, IngestionJob
from app.services.llm import LlmClient
from app.services.parsing import DocumentParseError, chunk_text, clean_text, parse_document
from app.services.vector_store import VectorPoint, VectorStore


class IngestionError(RuntimeError):
    pass


async def _existing_embeddings(
    session: AsyncSession, content_hashes: list[str], model_name: str
) -> dict[str, Embedding]:
    rows = (
        await session.scalars(
            select(Embedding).where(
                Embedding.content_hash.in_(content_hashes), Embedding.model_name == model_name
            )
        )
    ).all()
    return {row.content_hash: row for row in rows}


async def get_or_create_embeddings(
    session: AsyncSession, llm: LlmClient, contents: list[str]
) -> dict[str, Embedding]:
    """Return cached embeddings by content hash, creating missing ones in batch."""
    settings = get_settings()
    content_by_hash = {
        hashlib.sha256(content.encode("utf-8")).hexdigest(): content for content in contents
    }
    embeddings = await _existing_embeddings(
        session, list(content_by_hash), settings.embedding_model
    )
    missing_hashes = [
        content_hash for content_hash in content_by_hash if content_hash not in embeddings
    ]
    if not missing_hashes:
        return embeddings

    vectors = await llm.embed_many(
        [content_by_hash[content_hash] for content_hash in missing_hashes]
    )
    if any(len(vector) != settings.embedding_dimension for vector in vectors):
        raise IngestionError("Embedding 向量维度与配置不一致")

    new_embeddings = [
        Embedding(
            content_hash=content_hash,
            model_name=settings.embedding_model,
            dimension=len(vector),
            qdrant_point_id=str(uuid.uuid4()),
            vector=vector,
        )
        for content_hash, vector in zip(missing_hashes, vectors, strict=True)
    ]
    try:
        async with session.begin_nested():
            session.add_all(new_embeddings)
            await session.flush()
    except IntegrityError:
        # Another worker may have inserted the same global cache record while
        # this document was being parsed. Reuse it instead of embedding again.
        embeddings = await _existing_embeddings(
            session, list(content_by_hash), settings.embedding_model
        )
        unresolved = set(content_by_hash).difference(embeddings)
        if unresolved:
            raise IngestionError("Embedding 缓存暂时冲突，请重试") from None
        return embeddings

    embeddings.update({embedding.content_hash: embedding for embedding in new_embeddings})
    return embeddings


async def ingest_document(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Parse a document, cache its embeddings, and atomically index its chunks."""
    document = await session.get(Document, document_id)
    job = await session.scalar(select(IngestionJob).where(IngestionJob.document_id == document_id))
    if document is None or job is None or document.status == DocumentStatus.DELETED:
        return

    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    job.status = JobStatus.PROCESSING
    job.attempts += 1
    job.error_message = None
    job.started_at = datetime.now(UTC)
    await session.commit()

    try:
        text = clean_text(parse_document(Path(document.file_path), document.file_type))
        pieces = chunk_text(text)
        if not pieces:
            raise IngestionError("文档中没有可入库的有效文本")

        # A deletion can complete while a worker is parsing a large file. Never
        # allow this worker to resurrect that document or recreate its chunks.
        await session.refresh(document)
        if document.status == DocumentStatus.DELETED:
            return

        vector_store = VectorStore()
        old_point_ids = (
            await session.scalars(
                select(Chunk.vector_point_id).where(Chunk.document_id == document.id)
            )
        ).all()
        if old_point_ids:
            await vector_store.delete_points(old_point_ids)

        # A retry must not leave stale chunks behind. The database changes
        # share one transaction; any remote points are explicitly cleaned up.
        await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        embeddings = await get_or_create_embeddings(
            session, LlmClient(), [piece.content for piece in pieces]
        )
        points: list[VectorPoint] = []
        for piece in pieces:
            content_hash = hashlib.sha256(piece.content.encode("utf-8")).hexdigest()
            embedding = embeddings[content_hash]
            chunk = Chunk(
                document_id=document.id,
                embedding_id=embedding.id,
                content=piece.content,
                heading_path=piece.heading_path,
                chunk_index=piece.chunk_index,
                metadata_={"heading_path": piece.heading_path},
                vector_point_id=str(uuid.uuid4()),
            )
            session.add(chunk)
            await session.flush()
            points.append(
                VectorPoint(
                    point_id=chunk.vector_point_id,
                    vector=embedding.vector,
                    user_id=document.user_id,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    heading_path=chunk.heading_path,
                )
            )

        await vector_store.upsert_chunks(points)

        document.chunk_count = len(pieces)
        document.status = DocumentStatus.COMPLETED
        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(UTC)
        await session.commit()
    except (DocumentParseError, IngestionError) as exc:
        await session.rollback()
        document = await session.get(Document, document_id)
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_id == document_id)
        )
        if document and job:
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.now(UTC)
            await session.commit()
    except Exception:
        # Qdrant does not participate in the PostgreSQL transaction. Clean
        # only points created by this attempt before exposing a safe failure.
        await session.rollback()
        try:
            if "points" in locals():
                await VectorStore().delete_points([point.point_id for point in points])
        except Exception:
            pass
        document = await session.get(Document, document_id)
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.document_id == document_id)
        )
        if document and job:
            document.status = DocumentStatus.FAILED
            document.error_message = "文档处理失败，请稍后重试"
            job.status = JobStatus.FAILED
            job.error_message = "内部处理失败"
            job.finished_at = datetime.now(UTC)
            await session.commit()
        raise
