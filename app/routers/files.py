"""Authenticated document upload and lifecycle endpoints."""

import hashlib
import uuid
from pathlib import Path

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.domain import DocumentStatus, JobStatus
from app.models import Chunk, Document, IngestionJob, User
from app.schemas import (
    DeleteDocumentResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadResponse,
)
from app.services.auth import current_user, require_same_user
from app.services.vector_store import VectorStore

router = APIRouter(prefix="/api/v1/files", tags=["files"])

_ALLOWED_FILE_TYPES = {".md", ".pdf", ".txt"}
_UPLOAD_CHUNK_BYTES = 64 * 1024


def _safe_upload_path(settings: Settings, document_id: uuid.UUID, suffix: str) -> Path:
    root = settings.upload_dir.resolve()
    target = (root / f"{document_id}{suffix}").resolve()
    if root not in target.parents:
        raise RuntimeError("invalid upload path")
    return target


async def _save_upload(file: UploadFile, target: Path, max_bytes: int) -> tuple[int, str]:
    """Stream a file to storage while enforcing its byte limit."""
    total = 0
    digest = hashlib.sha256()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as destination:
            while data := await file.read(_UPLOAD_CHUNK_BYTES):
                total += len(data)
                if total > max_bytes:
                    raise ValueError("文件大小不能超过 10 MB")
                digest.update(data)
                destination.write(data)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return total, digest.hexdigest()


async def _enqueue_ingestion(document_id: uuid.UUID, settings: Settings) -> None:
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("ingest_document_job", str(document_id))
    finally:
        await pool.aclose()


def _delete_uploaded_file(path_value: str, settings: Settings) -> None:
    root = settings.upload_dir.resolve()
    path = Path(path_value).resolve()
    if root not in path.parents:
        raise RuntimeError("stored file path is outside upload directory")
    path.unlink(missing_ok=True)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Form(...),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    """Accept a supported source file and submit parsing to the ARQ worker."""
    require_same_user(user, user_id)
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or len(filename) > 255 or suffix not in _ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 PDF、Markdown 或 TXT 文件",
        )
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件大小不能超过 10 MB",
        )

    document_id = uuid.uuid4()
    target = _safe_upload_path(settings, document_id, suffix)
    try:
        file_size, content_hash = await _save_upload(file, target, settings.max_upload_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="文件暂时无法保存，请稍后重试",
        ) from exc

    document = Document(
        id=document_id,
        user_id=user.id,
        filename=filename,
        file_type=suffix,
        file_path=str(target),
        file_size=file_size,
        content_hash=content_hash,
        status=DocumentStatus.PROCESSING,
    )
    session.add(document)
    session.add(IngestionJob(document_id=document.id, status=JobStatus.PENDING))
    try:
        await session.commit()
        await _enqueue_ingestion(document.id, settings)
    except Exception as exc:
        await session.rollback()
        persisted = await session.get(Document, document.id)
        if persisted is not None:
            persisted.status = DocumentStatus.FAILED
            persisted.error_message = "文档暂时无法安排处理，请稍后重试"
            job = await session.scalar(
                select(IngestionJob).where(IngestionJob.document_id == persisted.id)
            )
            if job is not None:
                job.status = JobStatus.FAILED
                job.error_message = "入库任务未提交"
            await session.commit()
        else:
            _delete_uploaded_file(str(target), settings)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="文档暂时无法处理，请稍后重试",
        ) from exc

    return DocumentUploadResponse(
        document_id=document.id,
        filename=document.filename,
        status=DocumentStatus.PROCESSING,
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentListResponse:
    documents = (
        await session.scalars(
            select(Document)
            .where(Document.user_id == user.id, Document.status != DocumentStatus.DELETED)
            .order_by(Document.created_at.desc())
        )
    ).all()
    return DocumentListResponse(
        documents=[
            DocumentListItem(
                document_id=document.id,
                filename=document.filename,
                status=document.status,
                chunk_count=document.chunk_count,
                created_at=document.created_at,
                error_message=document.error_message,
            )
            for document in documents
        ]
    )


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DeleteDocumentResponse:
    document = await session.scalar(
        select(Document)
        .where(Document.id == document_id, Document.user_id == user.id)
        .with_for_update()
    )
    if document is None or document.status == DocumentStatus.DELETED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    point_ids = (
        await session.scalars(select(Chunk.vector_point_id).where(Chunk.document_id == document.id))
    ).all()
    try:
        await VectorStore().delete_points(point_ids)
        _delete_uploaded_file(document.file_path, settings)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="文档暂时无法删除，请稍后重试",
        ) from exc

    # Foreign-key cascades remove chunks and the ingestion job along with the
    # document. Step 4 will first remove that document's Qdrant points.
    await session.delete(document)
    await session.commit()
    return DeleteDocumentResponse(document_id=document.id, status="deleted")
