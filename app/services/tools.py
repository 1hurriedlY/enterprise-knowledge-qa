import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, HumanTicket, LogisticsEvent, Order
from app.schemas import (
    QueryLogisticsArgs,
    QueryLogisticsResult,
    QueryOrderArgs,
    QueryOrderResult,
    ToolErrorResult,
    TransferToHumanArgs,
    TransferToHumanResult,
)


async def query_order(
    session: AsyncSession, user_id: uuid.UUID, args: QueryOrderArgs
) -> QueryOrderResult | ToolErrorResult:
    order = await session.scalar(
        select(Order).where(Order.order_id == args.order_id, Order.user_id == user_id)
    )
    if order is None:
        return ToolErrorResult(error_code="ORDER_NOT_FOUND", error_message="订单不存在")
    return QueryOrderResult(
        order_id=order.order_id,
        status=order.status,
        amount=float(order.amount),
        created_at=order.created_at,
    )


async def query_logistics(
    session: AsyncSession, user_id: uuid.UUID, args: QueryLogisticsArgs
) -> QueryLogisticsResult | ToolErrorResult:
    order = await session.scalar(
        select(Order).where(Order.order_id == args.order_id, Order.user_id == user_id)
    )
    if order is None:
        return ToolErrorResult(error_code="LOGISTICS_NOT_FOUND", error_message="物流信息不存在")
    rows = (
        await session.scalars(
            select(LogisticsEvent.event_text)
            .where(LogisticsEvent.order_id == order.order_id)
            .order_by(LogisticsEvent.sequence)
        )
    ).all()
    if not rows:
        return ToolErrorResult(error_code="LOGISTICS_NOT_FOUND", error_message="物流信息不存在")
    return QueryLogisticsResult(order_id=order.order_id, logistics=list(rows))


async def transfer_to_human(
    session: AsyncSession, user_id: uuid.UUID, args: TransferToHumanArgs
) -> TransferToHumanResult | ToolErrorResult:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == args.conversation_id, Conversation.user_id == user_id
        )
    )
    if conversation is None:
        return ToolErrorResult(error_code="CONVERSATION_NOT_FOUND", error_message="会话不存在")
    ticket = HumanTicket(
        conversation_id=args.conversation_id,
        user_id=user_id,
        reason=args.reason,
        status="created",
    )
    session.add(ticket)
    await session.flush()
    return TransferToHumanResult(ticket_id=ticket.id, status="created")
