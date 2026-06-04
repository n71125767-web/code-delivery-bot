from datetime import datetime
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, SupplierRequest, Supplier, SupplierProduct


ACTIVE_CUSTOMER_STATUSES = [
    "waiting_service",
    "waiting_supplier_number",
    "number_sent_to_customer",
    "waiting_supplier_code",
    "code_sent_to_customer",
]


def normalize_key(value: str | int | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


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
    suppliers = await session.scalar(select(func.count(Supplier.id)).where(Supplier.is_active == True))

    return (
        "Статус бота\n\n"
        f"Всего заказов: {total_orders or 0}\n"
        f"Ждут сервис: {waiting_service or 0}\n"
        f"Ждут номер: {waiting_number or 0}\n"
        f"Ждут код: {waiting_code or 0}\n"
        f"Успешные: {confirmed or 0}\n"
        f"Проблемные: {problem or 0}\n"
        f"Активные поставщики: {suppliers or 0}"
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
            f"Товар ID: {order.product_id or 'нет'}\n"
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


# ---------- Suppliers ----------

async def add_supplier(session: AsyncSession, telegram_id: int, name: str) -> Supplier:
    result = await session.execute(select(Supplier).where(Supplier.telegram_id == telegram_id))
    supplier = result.scalars().first()

    if supplier:
        supplier.name = name
        supplier.is_active = True
    else:
        supplier = Supplier(telegram_id=telegram_id, name=name, is_active=True)
        session.add(supplier)

    await session.commit()
    await session.refresh(supplier)
    return supplier


async def remove_supplier(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(select(Supplier).where(Supplier.telegram_id == telegram_id))
    supplier = result.scalars().first()

    if not supplier:
        return False

    supplier.is_active = False
    await session.commit()
    return True


async def list_suppliers_text(session: AsyncSession) -> str:
    result = await session.execute(select(Supplier).order_by(Supplier.created_at.desc()))
    suppliers = result.scalars().all()

    if not suppliers:
        return "Поставщиков пока нет.\nДобавить: /add_supplier TELEGRAM_ID Имя"

    lines = ["Поставщики:\n"]
    for supplier in suppliers:
        products_result = await session.execute(
            select(SupplierProduct.product_key).where(
                SupplierProduct.supplier_telegram_id == supplier.telegram_id
            )
        )
        product_keys = [row[0] for row in products_result.fetchall()]
        lines.append(
            f"ID: {supplier.telegram_id}\n"
            f"Имя: {supplier.name}\n"
            f"Статус: {'active' if supplier.is_active else 'disabled'}\n"
            f"Товары: {', '.join(product_keys) if product_keys else 'не привязаны'}\n"
            "--------------------"
        )

    return "\n".join(lines)


async def bind_supplier_to_product(session: AsyncSession, telegram_id: int, product_key: str) -> str:
    product_key = normalize_key(product_key)

    if not product_key:
        return "Не указан товар/ключ."

    result = await session.execute(
        select(Supplier).where(Supplier.telegram_id == telegram_id)
    )
    supplier = result.scalars().first()

    if not supplier or not supplier.is_active:
        return "Поставщик не найден или выключен. Сначала: /add_supplier TELEGRAM_ID Имя"

    result = await session.execute(
        select(SupplierProduct).where(
            SupplierProduct.supplier_telegram_id == telegram_id,
            SupplierProduct.product_key == product_key,
        )
    )
    exists = result.scalars().first()

    if not exists:
        session.add(SupplierProduct(supplier_telegram_id=telegram_id, product_key=product_key))
        await session.commit()

    return f"OK. Поставщик {telegram_id} привязан к товару/ключу: {product_key}"


async def unbind_supplier_from_product(session: AsyncSession, telegram_id: int, product_key: str) -> str:
    product_key = normalize_key(product_key)

    await session.execute(
        delete(SupplierProduct).where(
            SupplierProduct.supplier_telegram_id == telegram_id,
            SupplierProduct.product_key == product_key,
        )
    )
    await session.commit()

    return f"OK. Привязка удалена: {telegram_id} -> {product_key}"


async def find_supplier_for_order(session: AsyncSession, order: Order) -> Supplier | None:
    keys: list[str] = []

    if order.product_id is not None:
        keys.append(normalize_key(order.product_id))

    if order.product_name:
        product_name = normalize_key(order.product_name)
        keys.append(product_name)

    # 1. точное совпадение product_id или product_name
    if keys:
        result = await session.execute(
            select(Supplier)
            .join(SupplierProduct, Supplier.telegram_id == SupplierProduct.supplier_telegram_id)
            .where(Supplier.is_active == True)
            .where(SupplierProduct.product_key.in_(keys))
            .limit(1)
        )
        supplier = result.scalars().first()
        if supplier:
            return supplier

    # 2. product_key как ключевое слово внутри названия товара
    if order.product_name:
        product_name = normalize_key(order.product_name)
        result = await session.execute(
            select(Supplier, SupplierProduct)
            .join(SupplierProduct, Supplier.telegram_id == SupplierProduct.supplier_telegram_id)
            .where(Supplier.is_active == True)
        )
        rows = result.fetchall()

        for supplier, supplier_product in rows:
            key = normalize_key(supplier_product.product_key)
            if key and key in product_name:
                return supplier

    # 3. fallback: первый активный поставщик
    result = await session.execute(
        select(Supplier).where(Supplier.is_active == True).order_by(Supplier.created_at.asc()).limit(1)
    )
    return result.scalars().first()
