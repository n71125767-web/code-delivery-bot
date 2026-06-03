from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, SupplierRequest, ProcessedMessage, OrderAction
from app.utils import normalize_username, make_hash


WAITING_BUYER_STATUS = "waiting_buyer_message"
WAITING_SUPPLIER_STATUS = "waiting_supplier"
SUPPLIER_ANSWERED_STATUS = "supplier_answered"
DELIVERED_STATUS = "delivered"
COMPLETED_STATUS = "completed"
ERROR_STATUS = "error"

ACTIVE_PAID_STATUSES = [
    WAITING_BUYER_STATUS,
    WAITING_SUPPLIER_STATUS,
    SUPPLIER_ANSWERED_STATUS,
    DELIVERED_STATUS,
    "waiting_service",
    "waiting_supplier_number",
    "number_sent_to_customer",
    "waiting_supplier_code",
    "code_sent_to_customer",
]


async def log_order_action(
    session: AsyncSession,
    order_id: int | None,
    action: str,
    details: str | None = None,
) -> None:
    session.add(
        OrderAction(
            order_id=order_id,
            action=action,
            details=details,
        )
    )
    await session.commit()


async def is_message_processed(session: AsyncSession, message_key: str) -> bool:
    result = await session.execute(
        select(ProcessedMessage).where(ProcessedMessage.message_key == message_key)
    )
    return result.scalars().first() is not None


async def mark_message_processed(
    session: AsyncSession,
    message_key: str,
    source: str,
    raw_text: str | None,
) -> None:
    if await is_message_processed(session, message_key):
        return

    session.add(
        ProcessedMessage(
            message_key=message_key,
            source=source,
            raw_text=raw_text,
        )
    )
    await session.commit()


async def get_order_by_id(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.id == order_id)
    )
    return result.scalars().first()


async def get_order_by_operation_id(session: AsyncSession, operation_id: int) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.operation_id == operation_id)
    )
    return result.scalars().first()


async def create_or_update_order_from_admaker_message(session: AsyncSession, data: dict) -> Order:
    existing = await get_order_by_operation_id(session, data["operation_id"])

    if existing:
        existing.external_id = data.get("external_id")
        existing.customer_telegram_id = data.get("customer_telegram_id")
        existing.customer_username = normalize_username(data.get("customer_username"))
        existing.product_id = data.get("product_id")
        existing.product_name = data.get("product_name")
        existing.amount = data.get("amount")
        existing.currency = data.get("currency")
        existing.raw_message = data.get("raw_message")
        existing.is_paid = True
        existing.updated_at = datetime.utcnow()

        if existing.status in ["waiting_service", None]:
            existing.status = WAITING_BUYER_STATUS

        await session.commit()
        await session.refresh(existing)
        await log_order_action(session, existing.id, "order_updated_from_admaker", data.get("raw_message"))
        return existing

    order = Order(
        operation_id=data["operation_id"],
        external_id=data.get("external_id"),
        customer_telegram_id=data.get("customer_telegram_id"),
        customer_username=normalize_username(data.get("customer_username")),
        product_id=data.get("product_id"),
        product_name=data.get("product_name"),
        amount=data.get("amount"),
        currency=data.get("currency"),
        status=WAITING_BUYER_STATUS,
        raw_message=data.get("raw_message"),
        is_paid=True,
        paid_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(order)
    await session.commit()
    await session.refresh(order)

    await log_order_action(session, order.id, "order_created_from_admaker", data.get("raw_message"))
    return order


async def create_or_update_order_from_purchase(session: AsyncSession, data: dict) -> Order:
    return await create_or_update_order_from_admaker_message(session, data)


async def find_waiting_service_order_by_id_or_username_today(
    session: AsyncSession,
    telegram_id: int | None,
    username: str | None,
    user_message: str | None = None,
) -> Order | None:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    clean_username = normalize_username(username)
    text = (user_message or "").lower()

    if telegram_id:
        result = await session.execute(
            select(Order)
            .where(Order.customer_telegram_id == telegram_id)
            .where(Order.status.in_([WAITING_BUYER_STATUS, "waiting_service"]))
            .where(Order.created_at >= today_start)
            .order_by(Order.created_at.desc())
        )
        order = result.scalars().first()
        if order:
            return order

    if clean_username:
        result = await session.execute(
            select(Order)
            .where(Order.customer_username == clean_username)
            .where(Order.status.in_([WAITING_BUYER_STATUS, "waiting_service"]))
            .where(Order.created_at >= today_start)
            .order_by(Order.created_at.desc())
        )
        order = result.scalars().first()
        if order:
            return order

    result = await session.execute(
        select(Order)
        .where(Order.status.in_([WAITING_BUYER_STATUS, "waiting_service"]))
        .where(Order.created_at >= today_start)
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    for order in orders:
        if order.product_name and order.product_name.lower() in text:
            return order

    return orders[0] if len(orders) == 1 else None


async def find_active_paid_order_for_buyer(
    session: AsyncSession,
    telegram_id: int | None,
    username: str | None,
    user_message: str | None = None,
) -> Order | None:
    clean_username = normalize_username(username)
    text = (user_message or "").lower()

    if telegram_id:
        result = await session.execute(
            select(Order)
            .where(Order.customer_telegram_id == telegram_id)
            .where(Order.is_paid == True)
            .where(Order.status.in_(ACTIVE_PAID_STATUSES))
            .order_by(Order.created_at.desc())
        )
        order = result.scalars().first()
        if order:
            return order

    if clean_username:
        result = await session.execute(
            select(Order)
            .where(Order.customer_username == clean_username)
            .where(Order.is_paid == True)
            .where(Order.status.in_(ACTIVE_PAID_STATUSES))
            .order_by(Order.created_at.desc())
        )
        order = result.scalars().first()
        if order:
            return order

    result = await session.execute(
        select(Order)
        .where(Order.is_paid == True)
        .where(Order.status.in_(ACTIVE_PAID_STATUSES))
        .order_by(Order.created_at.desc())
        .limit(20)
    )
    orders = result.scalars().all()

    for order in orders:
        if order.product_name and order.product_name.lower() in text:
            return order

    return None


async def find_waiting_service_order_for_customer(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> Order | None:
    return await find_waiting_service_order_by_id_or_username_today(
        session=session,
        telegram_id=telegram_id,
        username=username,
    )


async def find_active_order_for_customer(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> Order | None:
    return await find_active_paid_order_for_buyer(
        session=session,
        telegram_id=telegram_id,
        username=username,
    )


async def create_supplier_request(
    session: AsyncSession,
    order_id: int,
    supplier_telegram_id: int,
    request_type: str = "product",
    buyer_message: str | None = None,
    supplier_username: str | None = None,
) -> SupplierRequest:
    request = SupplierRequest(
        order_id=order_id,
        supplier_telegram_id=supplier_telegram_id,
        supplier_username=normalize_username(supplier_username),
        request_type=request_type,
        status="sent",
        buyer_message=buyer_message,
    )

    session.add(request)
    await session.commit()
    await session.refresh(request)

    await log_order_action(
        session,
        order_id,
        "supplier_request_created",
        f"supplier={supplier_telegram_id}, type={request_type}, buyer_message={buyer_message}",
    )

    return request


async def find_waiting_supplier_request(
    session: AsyncSession,
    supplier_telegram_id: int,
    request_type: str | None = None,
) -> SupplierRequest | None:
    query = (
        select(SupplierRequest)
        .where(SupplierRequest.supplier_telegram_id == supplier_telegram_id)
        .where(SupplierRequest.status == "sent")
        .order_by(SupplierRequest.created_at.asc())
    )

    if request_type:
        query = query.where(SupplierRequest.request_type == request_type)

    result = await session.execute(query)
    return result.scalars().first()


async def is_delivered_text_used(session: AsyncSession, text: str) -> bool:
    delivered_hash = make_hash(text)

    result = await session.execute(
        select(Order)
        .where(Order.delivered_hash == delivered_hash)
        .where(Order.status.in_([DELIVERED_STATUS, COMPLETED_STATUS]))
    )

    return result.scalars().first() is not None


async def mark_order_error(session: AsyncSession, order: Order, error_text: str) -> None:
    order.status = ERROR_STATUS
    order.last_error = error_text
    order.updated_at = datetime.utcnow()
    await session.commit()
    await log_order_action(session, order.id, "error", error_text)


async def mark_order_waiting_supplier(
    session: AsyncSession,
    order: Order,
    supplier_id: int,
    buyer_message: str,
    business_connection_id: str | None = None,
) -> None:
    order.status = WAITING_SUPPLIER_STATUS
    order.supplier_telegram_id = supplier_id
    order.buyer_message = buyer_message
    order.customer_business_connection_id = business_connection_id
    order.updated_at = datetime.utcnow()

    await session.commit()
    await log_order_action(session, order.id, "waiting_supplier", buyer_message)


async def mark_supplier_answered(
    session: AsyncSession,
    order: Order,
    request: SupplierRequest,
    answer: str,
) -> None:
    request.status = "answered"
    request.supplier_answer = answer
    request.answered_at = datetime.utcnow()

    order.status = SUPPLIER_ANSWERED_STATUS
    order.updated_at = datetime.utcnow()

    await session.commit()
    await log_order_action(session, order.id, "supplier_answered", answer)


async def mark_order_delivered(session: AsyncSession, order: Order, delivered_text: str) -> None:
    order.delivered_text = delivered_text
    order.delivered_hash = make_hash(delivered_text)
    order.status = DELIVERED_STATUS
    order.updated_at = datetime.utcnow()

    await session.commit()
    await log_order_action(session, order.id, "delivered", delivered_text)


async def mark_order_completed(session: AsyncSession, order: Order) -> None:
    order.status = COMPLETED_STATUS
    order.updated_at = datetime.utcnow()

    await session.commit()
    await log_order_action(session, order.id, "completed", None)