from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Order, SupplierRequest


ACTIVE_CUSTOMER_STATUSES = [
    "waiting_service",
    "number_sent_to_customer",
    "code_sent_to_customer",
]


async def get_order_by_operation_id(session: AsyncSession, operation_id: int) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.operation_id == operation_id)
    )
    return result.scalars().first()


async def create_or_update_order_from_purchase(session: AsyncSession, data: dict) -> Order:
    existing = await get_order_by_operation_id(session, data["operation_id"])

    if existing:
        existing.external_id = data.get("external_id")
        existing.customer_telegram_id = data.get("customer_telegram_id")
        existing.customer_username = data.get("customer_username")
        existing.product_id = data.get("product_id")
        existing.product_name = data.get("product_name")
        existing.amount = data.get("amount")
        existing.currency = data.get("currency")
        existing.raw_message = data.get("raw_message")
        existing.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(existing)
        return existing

    order = Order(
        operation_id=data["operation_id"],
        external_id=data.get("external_id"),
        customer_telegram_id=data.get("customer_telegram_id"),
        customer_username=data.get("customer_username"),
        product_id=data.get("product_id"),
        product_name=data.get("product_name"),
        amount=data.get("amount"),
        currency=data.get("currency"),
        status="waiting_service",
        raw_message=data.get("raw_message"),
        paid_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(order)
    await session.commit()
    await session.refresh(order)

    return order


async def find_waiting_service_order_for_customer(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> Order | None:
    result = await session.execute(
        select(Order)
        .where(Order.customer_telegram_id == telegram_id)
        .where(Order.status == "waiting_service")
        .order_by(Order.created_at.desc())
    )
    order = result.scalars().first()

    if order:
        return order

    if username:
        clean_username = username.replace("@", "").lower()

        result = await session.execute(
            select(Order)
            .where(Order.customer_username.is_not(None))
            .where(Order.status == "waiting_service")
            .order_by(Order.created_at.desc())
        )

        orders = result.scalars().all()

        for item in orders:
            if item.customer_username and item.customer_username.replace("@", "").lower() == clean_username:
                return item

    return None


async def find_active_order_for_customer(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> Order | None:
    result = await session.execute(
        select(Order)
        .where(Order.customer_telegram_id == telegram_id)
        .where(Order.status.in_(ACTIVE_CUSTOMER_STATUSES))
        .order_by(Order.created_at.desc())
    )
    order = result.scalars().first()

    if order:
        return order

    if username:
        clean_username = username.replace("@", "").lower()

        result = await session.execute(
            select(Order)
            .where(Order.customer_username.is_not(None))
            .where(Order.status.in_(ACTIVE_CUSTOMER_STATUSES))
            .order_by(Order.created_at.desc())
        )

        orders = result.scalars().all()

        for item in orders:
            if item.customer_username and item.customer_username.replace("@", "").lower() == clean_username:
                return item

    return None


async def create_supplier_request(
    session: AsyncSession,
    order_id: int,
    supplier_telegram_id: int,
    request_type: str,
) -> SupplierRequest:
    request = SupplierRequest(
        order_id=order_id,
        supplier_telegram_id=supplier_telegram_id,
        request_type=request_type,
        status="sent",
    )

    session.add(request)
    await session.commit()
    await session.refresh(request)

    return request


async def find_waiting_supplier_request(
    session: AsyncSession,
    supplier_telegram_id: int,
    request_type: str,
) -> SupplierRequest | None:
    result = await session.execute(
        select(SupplierRequest)
        .where(SupplierRequest.supplier_telegram_id == supplier_telegram_id)
        .where(SupplierRequest.request_type == request_type)
        .where(SupplierRequest.status == "sent")
        .order_by(SupplierRequest.created_at.asc())
    )

    return result.scalars().first()


async def get_order_by_id(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.id == order_id)
    )
    return result.scalars().first()

async def find_waiting_service_order_by_id_or_username_today(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> Order | None:
    return await find_waiting_service_order_for_customer(
        session=session,
        telegram_id=telegram_id,
        username=username,
    )