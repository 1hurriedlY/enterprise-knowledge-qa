"""Public registration/login and authenticated API key management."""

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.domain import UserRole
from app.models import ApiKey, User
from app.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
)
from app.services.auth import current_user, hash_api_key
from app.services.passwords import hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def generate_api_key() -> str:
    return f"kb_{secrets.token_urlsafe(32)}"


def _api_key_response(key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        key_id=key.id,
        label=key.label,
        created_at=key.created_at,
        revoked_at=key.revoked_at,
        active=key.revoked_at is None,
    )


def _api_key_create_response(key: ApiKey, raw_key: str) -> ApiKeyCreateResponse:
    return ApiKeyCreateResponse(
        key_id=key.id,
        label=key.label,
        created_at=key.created_at,
        revoked_at=key.revoked_at,
        active=key.revoked_at is None,
        api_key=raw_key,
    )


async def _issue_api_key(
    session: AsyncSession, user_id: uuid.UUID, label: str
) -> tuple[ApiKey, str]:
    raw_key = generate_api_key()
    key = ApiKey(
        user_id=user_id,
        key_hash=hash_api_key(raw_key),
        label=label,
        created_at=datetime.now(UTC),
    )
    session.add(key)
    await session.flush()
    return key, raw_key


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    email = payload.email.lower()
    if await session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")
    user = User(name=payload.name, email=email, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        await session.flush()
        key, raw_key = await _issue_api_key(session, user.id, "registration key")
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册") from exc
    return AuthResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role or UserRole.USER,
        api_key=raw_key,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    key, raw_key = await _issue_api_key(session, user.id, "login key")
    await session.commit()
    return AuthResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        api_key=raw_key,
    )


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreateResponse:
    key, raw_key = await _issue_api_key(session, user.id, payload.label)
    await session.commit()
    return _api_key_create_response(key, raw_key)


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> ApiKeyListResponse:
    keys = (
        await session.scalars(
            select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
        )
    ).all()
    return ApiKeyListResponse(api_keys=[_api_key_response(key) for key in keys])


@router.delete("/api-keys/{key_id}", response_model=ApiKeyResponse)
async def revoke_api_key(
    key_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyResponse:
    key = await session.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await session.commit()
    return _api_key_response(key)
