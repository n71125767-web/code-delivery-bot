from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Order, SupplierRequest


async def create_order_from_purchase(session: AsyncSession, data: dict) -> Order:
    existing = await session.scalar(
        select(Order).where(Order.operation_id == data["operation_id"])
    )

    if existing:
        return existing

    order = Order(
        operation_id=data["operation_id"],
        external_id=data.get("external_id"),
        customer_telegram_id=data["customer_telegram_id"],
        customer_username=data.get("customer_username"),
        product_id=data["product_id"],
        product_name=data["product_name"],
        amount=data.get("amount"),
        currency=data.get("currency"),
        status="waiting_service",
        raw_message=data.get("raw_message"),
    )

    session.add(order)
    await session.commit()
    await session.refresh(order)

    return order


async def find_waiting_service_order(
    session: AsyncSession,
    customer_telegram_id: int,
) -> Order | None:
    return await session.scalar(
        select(Order)
        .where(Order.customer_telegram_id == customer_telegram_id)
        .where(Order.status == "waiting_service")
        .order_by(Order.id.desc())
    )


async def find_order_waiting_supplier_number(
    session: AsyncSession,
    supplier_telegram_id: int,
) -> Order | None:
    request = await session.scalar(
        select(SupplierRequest)
        .where(SupplierRequest.supplier_telegram_id == supplier_telegram_id)
        .where(SupplierRequest.request_type == "number")
        .where(SupplierRequest.status == "sent")
        .order_by(SupplierRequest.id.desc())
    )

    if not request:
        return None

    return await session.get(Order, request.order_id)


async def find_order_waiting_supplier_code(
    session: AsyncSession,
    supplier_telegram_id: int,
) -> Order | None:
    request = await session.scalar(
        select(SupplierRequest)
        .where(SupplierRequest.supplier_telegram_id == supplier_telegram_id)
        .where(SupplierRequest.request_type == "code")
        .where(SupplierRequest.status == "sent")
        .order_by(SupplierRequest.id.desc())
    )

    if not request:
        return None

    return await session.get(Order, request.order_id)


async def create_supplier_request(
    session: AsyncSession,
    order: Order,
    supplier_telegram_id: int,
    request_type: str,
) -> SupplierRequest:
    request = SupplierRequest(
        order_id=order.id,
        supplier_telegram_id=supplier_telegram_id,
        request_type=request_type,
        status="sent",
    )

    session.add(request)
    await session.commit()
    await session.refresh(request)

    return request


async def close_supplier_request(
    session: AsyncSession,
    order: Order,
    supplier_telegram_id: int,
    request_type: str,
) -> None:
    request = await session.scalar(
        select(SupplierRequest)
        .where(SupplierRequest.order_id == order.id)
        .where(SupplierRequest.supplier_telegram_id == supplier_telegram_id)
        .where(SupplierRequest.request_type == request_type)
        .where(SupplierRequest.status == "sent")
        .order_by(SupplierRequest.id.desc())
    )

    if request:
        request.status = "answered"
        request.answered_at = datetime.utcnow()

    await session.commit()