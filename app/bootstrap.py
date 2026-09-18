from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain import UserRole
from app.models import ApiKey, LogisticsEvent, Order, User
from app.services.auth import hash_api_key


async def seed_demo_identity(session: AsyncSession) -> None:
    """Create an idempotent local identity for first-run development only."""
    settings = get_settings()
    user = await session.scalar(select(User).where(User.email == settings.demo_user_email))
    if user is None:
        user = User(name="Demo Admin", email=settings.demo_user_email, role=UserRole.ADMIN)
        session.add(user)
        await session.flush()
    key_hash = hash_api_key(settings.demo_api_key.get_secret_value())
    key = await session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
    if key is None:
        session.add(ApiKey(user_id=user.id, key_hash=key_hash, label="development bootstrap key"))

    order = await session.scalar(
        select(Order).where(Order.order_id == "12345", Order.user_id == user.id)
    )
    if order is None:
        order = Order(order_id="12345", user_id=user.id, status="已发货", amount=99.0)
        session.add(order)
        await session.flush()
    logistics_exists = await session.scalar(
        select(LogisticsEvent.id).where(LogisticsEvent.order_id == order.order_id).limit(1)
    )
    if logistics_exists is None:
        session.add_all(
            [
                LogisticsEvent(
                    order_id=order.order_id,
                    event_text="已发货",
                    event_time=datetime(2026, 9, 16, 9, 0, tzinfo=UTC),
                    sequence=1,
                ),
                LogisticsEvent(
                    order_id=order.order_id,
                    event_text="到达北京转运中心",
                    event_time=datetime(2026, 9, 17, 10, 0, tzinfo=UTC),
                    sequence=2,
                ),
                LogisticsEvent(
                    order_id=order.order_id,
                    event_text="正在派送中",
                    event_time=datetime(2026, 9, 18, 8, 0, tzinfo=UTC),
                    sequence=3,
                ),
            ]
        )
    await session.commit()
