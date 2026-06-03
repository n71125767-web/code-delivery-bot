from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Order, SupplierRequest


ACTIVE_CUSTOMER_STATUSES = [
    "waiting_service",
    "waiting_supplier_number",
    "number_sent_to_customer",
    "waiting_supplier_code",
    "code_sent_to_customer",
]


async def get_order_by_operation_id(session: AsyncSession, operation_id: int) -> Order | None:
    result = await session.execute(select(Order).where(Order.operation_id == operation_id))
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

        if existing.status in {"problem", "confirmed"}:
            existing.status = "waiting_service"

        await session.commit()
        await session.refresh(existing)
        return existing

    order = Order(
        operation_id=data["operation_id"],
        external_id=data.get("external_id"),
        customer_telegram_id=data.get("customer_telegram_id"),
        buyer_chat_id=data.get("customer_telegram_id"),
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


async def find_order_for_customer(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    statuses: list[str],
) -> Order | None:
    result = await session.execute(
        select(Order)
        .where(Order.customer_telegram_id == telegram_id)
        .where(Order.status.in_(statuses))
        .order_by(Order.created_at.desc())
    )
    order = result.scalars().first()
    if order:
        return order

    result = await session.execute(
        select(Order)
        .where(Order.buyer_chat_id == telegram_id)
        .where(Order.status.in_(statuses))
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
            .where(Order.status.in_(statuses))
            .order_by(Order.created_at.desc())
        )
        orders = result.scalars().all()
        for item in orders:
            if item.customer_username and item.customer_username.replace("@", "").lower() == clean_username:
                return item

    return None


async def find_waiting_service_order_for_customer(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> Order | None:
    return await find_order_for_customer(session, telegram_id, username, ["waiting_service"])


async def find_active_order_for_customer(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> Order | None:
    return await find_order_for_customer(session, telegram_id, username, ACTIVE_CUSTOMER_STATUSES)


async def create_supplier_request(
    session: AsyncSession,
    order_id: int,
    supplier_telegram_id: int,
    request_type: str,
    supplier_message_id: int | None = None,
) -> SupplierRequest:
    request = SupplierRequest(
        order_id=order_id,
        supplier_telegram_id=supplier_telegram_id,
        request_type=request_type,
        supplier_message_id=supplier_message_id,
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
    result = await session.execute(select(Order).where(Order.id == order_id))
    return result.scalars().first()


async def get_status_text(session: AsyncSession) -> str:
    total_orders = await session.scalar(select(func.count(Order.id)))
    waiting_service = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_service"))
    waiting_number = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_supplier_number"))
    waiting_code = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_supplier_code"))
    confirmed = await session.scalar(select(func.count(Order.id)).where(Order.status == "confirmed"))
    problem = await session.scalar(select(func.count(Order.id)).where(Order.status == "problem"))

    return (
        "Статус бота\n\n"
        f"Всего заказов: {total_orders or 0}\n"
        f"Ждут сервис: {waiting_service or 0}\n"
        f"Ждут номер: {waiting_number or 0}\n"
        f"Ждут код: {waiting_code or 0}\n"
        f"Успешные: {confirmed or 0}\n"
        f"Проблемные: {problem or 0}"
    )


async def get_last_orders_text(session: AsyncSession) -> str:
    result = await session.execute(select(Order).order_by(Order.created_at.desc()).limit(10))
    orders = result.scalars().all()

    if not orders:
        return "Заказов пока нет."

    lines = ["Последние заказы:\n"]
    for order in orders:
        lines.append(
            f"#{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Покупатель ID: {order.customer_telegram_id or order.buyer_chat_id}\n"
            f"Username: @{order.customer_username or 'нет'}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name or 'не указан'}\n"
            f"Статус: {order.status}\n"
            "--------------------"
        )
    return "\n".join(lines)


async def set_customer_by_order_id(session: AsyncSession, order_id: int, telegram_id: int) -> str:
    order = await get_order_by_id(session, order_id)
    if not order:
        return "Заказ не найден."

    order.customer_telegram_id = telegram_id
    order.buyer_chat_id = telegram_id
    order.updated_at = datetime.utcnow()
    await session.commit()

    return f"OK. К заказу #{order.operation_id} привязан покупатель {telegram_id}."
