import uuid

import pytest

from app.domain import UserRole
from app.models import User
from app.routers.users import get_current_user


@pytest.mark.asyncio
async def test_current_user_endpoint_returns_only_authenticated_identity() -> None:
    user = User(
        id=uuid.uuid4(),
        name="Demo User",
        email="demo@example.com",
        role=UserRole.USER,
    )

    response = await get_current_user(user)

    assert response.user_id == user.id
    assert response.email == "demo@example.com"
    assert response.role == UserRole.USER
