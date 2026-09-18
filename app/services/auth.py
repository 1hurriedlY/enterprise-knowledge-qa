import hashlib
import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.domain import UserRole
from app.models import ApiKey, User


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def current_user(
    x_api_key: str = Header(alias="X-API-Key", min_length=16),
    session: AsyncSession = Depends(get_session),
) -> User:
    result = await session.execute(
        select(User)
        .join(ApiKey, ApiKey.user_id == User.id)
        .where(ApiKey.key_hash == hash_api_key(x_api_key), ApiKey.revoked_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 API Key")
    return user


def require_same_user(user: User, claimed_user_id: uuid.UUID) -> None:
    if user.id != claimed_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能访问其他用户资源")


async def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
