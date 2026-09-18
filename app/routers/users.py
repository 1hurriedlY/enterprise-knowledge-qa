"""Authenticated identity endpoint for browser clients."""

from fastapi import APIRouter, Depends

from app.models import User
from app.schemas import CurrentUserResponse
from app.services.auth import current_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user(user: User = Depends(current_user)) -> CurrentUserResponse:
    """Return only the identity that belongs to the supplied API key."""
    return CurrentUserResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
    )
