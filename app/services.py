from datetime import datetime, timedelta
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import POPULAR_SERVICE_THRESHOLD, PROBLEM_COOLDOWN_SECONDS
from app.models import Order, SupplierRequest, Supplier, SupplierProduct, ServiceOption, ServiceList, ServiceListItem, TextTemplate, Cooldown


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
    services = await session.scalar(select(func.count(ServiceOption.id)).where(ServiceOption.is_active == True))

    return (
        "Статус бота\n\n"
        f"Всего заказов: {total_orders or 0}\n"
        f"Ждут сервис: {waiting_service or 0}\n"
        f"Ждут номер: {waiting_number or 0}\n"
        f"Ждут код: {waiting_code or 0}\n"
        f"Успешные: {confirmed or 0}\n"
        f"Проблемные: {problem or 0}\n"
        f"Активные поставщики: {suppliers or 0}\n"
        f"Активные сервисы: {services or 0}"
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

    result = await session.execute(select(Supplier).where(Supplier.telegram_id == telegram_id))
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

    result = await session.execute(
        select(Supplier).where(Supplier.is_active == True).order_by(Supplier.created_at.asc()).limit(1)
    )
    return result.scalars().first()


# ---------- Services ----------

async def add_service(session: AsyncSession, name: str, emoji: str | None = None) -> str:
    name = name.strip()
    if not name:
        return "Название сервиса пустое."

    result = await session.execute(select(ServiceOption).where(ServiceOption.name == name))
    service = result.scalars().first()

    if service:
        service.is_active = True
        if emoji is not None:
            service.emoji = emoji
    else:
        service = ServiceOption(name=name, emoji=emoji, is_active=True)
        session.add(service)

    await session.commit()
    return f"OK. Сервис добавлен/обновлён: {format_service_label(service)}"


async def remove_service(session: AsyncSession, name: str) -> str:
    result = await session.execute(select(ServiceOption).where(func.lower(ServiceOption.name) == name.strip().lower()))
    service = result.scalars().first()

    if not service:
        return "Сервис не найден."

    service.is_active = False
    await session.commit()
    return f"OK. Сервис выключен: {service.name}"


async def set_service_emoji(session: AsyncSession, name: str, emoji: str) -> str:
    result = await session.execute(select(ServiceOption).where(func.lower(ServiceOption.name) == name.strip().lower()))
    service = result.scalars().first()

    if not service:
        return "Сервис не найден."

    service.emoji = emoji.strip()
    await session.commit()
    return f"OK. Эмодзи обновлён: {format_service_label(service)}"


def format_service_label(service: ServiceOption) -> str:
    emoji = service.emoji
    if not emoji and service.usage_count >= POPULAR_SERVICE_THRESHOLD:
        emoji = "🔥"

    if emoji:
        return f"{emoji} {service.name}"

    return service.name


async def get_services_page(session: AsyncSession, page: int, page_size: int) -> tuple[list[ServiceOption], int]:
    total = await session.scalar(select(func.count(ServiceOption.id)).where(ServiceOption.is_active == True))
    total = total or 0
    max_page = max((total - 1) // page_size, 0)

    page = max(0, min(page, max_page))

    result = await session.execute(
        select(ServiceOption)
        .where(ServiceOption.is_active == True)
        .order_by(ServiceOption.usage_count.desc(), ServiceOption.name.asc())
        .offset(page * page_size)
        .limit(page_size)
    )
    return result.scalars().all(), max_page


async def find_service_by_slug(session: AsyncSession, slug: str) -> ServiceOption | None:
    slug = slug.strip().lower()
    result = await session.execute(select(ServiceOption).where(ServiceOption.is_active == True))
    services = result.scalars().all()

    for service in services:
        if service.name.lower().replace(" ", "_") == slug:
            return service

    return None


async def find_service_by_text(session: AsyncSession, text: str) -> ServiceOption | None:
    clean = text.strip().lower()
    result = await session.execute(select(ServiceOption).where(ServiceOption.is_active == True))
    services = result.scalars().all()

    for service in services:
        service_clean = service.name.lower()
        if clean == service_clean or service_clean in clean:
            return service

    return None


async def increment_service_usage(session: AsyncSession, service_name: str) -> None:
    result = await session.execute(select(ServiceOption).where(func.lower(ServiceOption.name) == service_name.strip().lower()))
    service = result.scalars().first()
    if service:
        service.usage_count += 1
        await session.commit()


async def services_text(session: AsyncSession) -> str:
    result = await session.execute(
        select(ServiceOption).order_by(ServiceOption.is_active.desc(), ServiceOption.usage_count.desc(), ServiceOption.name.asc())
    )
    services = result.scalars().all()

    if not services:
        return "Сервисов пока нет."

    lines = ["Сервисы:\n"]
    for service in services:
        status = "active" if service.is_active else "disabled"
        lines.append(f"{format_service_label(service)} | использований: {service.usage_count} | {status}")

    return "\n".join(lines)


# ---------- Text templates ----------

async def get_text(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(TextTemplate).where(TextTemplate.key == key))
    template = result.scalars().first()
    return template.value if template else default


async def set_text(session: AsyncSession, key: str, value: str) -> str:
    result = await session.execute(select(TextTemplate).where(TextTemplate.key == key))
    template = result.scalars().first()

    if template:
        template.value = value
        template.updated_at = datetime.utcnow()
    else:
        session.add(TextTemplate(key=key, value=value, updated_at=datetime.utcnow()))

    await session.commit()
    return f"OK. Текст обновлён: {key}"


async def texts_text(session: AsyncSession) -> str:
    result = await session.execute(select(TextTemplate).order_by(TextTemplate.key.asc()))
    templates = result.scalars().all()

    if not templates:
        return "Текстов пока нет."

    lines = ["Тексты:\n"]
    for template in templates:
        value = template.value
        if len(value) > 80:
            value = value[:80] + "..."
        lines.append(f"{template.key}: {value}")

    return "\n".join(lines)


# ---------- Cooldowns ----------

async def check_cooldown(session: AsyncSession, user_id: int, action: str, seconds: int = PROBLEM_COOLDOWN_SECONDS) -> tuple[bool, int]:
    now = datetime.utcnow()

    result = await session.execute(
        select(Cooldown).where(
            Cooldown.user_id == user_id,
            Cooldown.action == action,
        )
    )
    cooldown = result.scalars().first()

    if cooldown:
        delta = now - cooldown.last_at
        if delta.total_seconds() < seconds:
            remaining = int(seconds - delta.total_seconds())
            return False, remaining

        cooldown.last_at = now
    else:
        cooldown = Cooldown(user_id=user_id, action=action, last_at=now)
        session.add(cooldown)

    await session.commit()
    return True, 0


# ---------- Supplier panel and service lists ----------

async def supplier_pending_text(session: AsyncSession, supplier_id: int, page: int, page_size: int) -> tuple[str, int]:
    total = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "sent",
        )
    )
    total = total or 0
    max_page = max((total - 1) // page_size, 0)
    page = max(0, min(page, max_page))

    result = await session.execute(
        select(SupplierRequest, Order)
        .join(Order, SupplierRequest.order_id == Order.id)
        .where(SupplierRequest.supplier_telegram_id == supplier_id, SupplierRequest.status == "sent")
        .order_by(SupplierRequest.created_at.asc())
        .offset(page * page_size)
        .limit(page_size)
    )
    rows = result.fetchall()

    if not rows:
        return "Ожидающих заявок нет.", max_page

    lines = [f"Заявки в ожидании — страница {page + 1}/{max_page + 1}\n"]
    for request, order in rows:
        request_label = "номер" if request.request_type == "number" else "код"
        lines.append(
            f"Заявка ID: {request.id}\n"
            f"Нужно: {request_label}\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name or 'не указан'}\n"
            f"Номер: {order.phone_number or 'ещё нет'}\n"
            "Ответьте сообщением сюда: номер или код.\n"
            "--------------------"
        )

    return "\n".join(lines), max_page


async def get_supplier_pending_rows(session: AsyncSession, supplier_id: int, page: int, page_size: int):
    total = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "sent",
        )
    )
    total = total or 0
    max_page = max((total - 1) // page_size, 0)
    page = max(0, min(page, max_page))

    result = await session.execute(
        select(SupplierRequest, Order)
        .join(Order, SupplierRequest.order_id == Order.id)
        .where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "sent",
        )
        .order_by(SupplierRequest.created_at.asc())
        .offset(page * page_size)
        .limit(page_size)
    )
    return result.fetchall(), max_page


async def find_selected_supplier_request(session: AsyncSession, supplier_id: int) -> SupplierRequest | None:
    result = await session.execute(
        select(SupplierRequest)
        .where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "selected",
        )
        .order_by(SupplierRequest.created_at.asc())
    )
    return result.scalars().first()


async def select_supplier_request(session: AsyncSession, supplier_id: int, request_id: int) -> tuple[bool, str, SupplierRequest | None, Order | None]:
    result = await session.execute(
        select(SupplierRequest, Order)
        .join(Order, SupplierRequest.order_id == Order.id)
        .where(
            SupplierRequest.id == request_id,
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "sent",
        )
    )
    row = result.first()
    if not row:
        return False, "Заявка не найдена или уже обработана.", None, None

    request, order = row

    result_selected = await session.execute(
        select(SupplierRequest).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "selected",
        )
    )
    for selected in result_selected.scalars().all():
        selected.status = "sent"

    request.status = "selected"
    await session.commit()
    await session.refresh(request)
    await session.refresh(order)

    return True, "OK. Заявка выбрана.", request, order


async def add_service_list(session: AsyncSession, name: str) -> str:
    name = name.strip()
    if not name:
        return "Название листа пустое."

    result = await session.execute(select(ServiceList).where(ServiceList.name == name))
    item = result.scalars().first()
    if item:
        item.is_active = True
    else:
        session.add(ServiceList(name=name, is_active=True))

    await session.commit()
    return f"OK. Лист создан/включён: {name}"


async def add_service_to_list(session: AsyncSession, list_name: str, service_name: str) -> str:
    list_name = list_name.strip()
    service_name = service_name.strip()

    if not list_name or not service_name:
        return "Формат: /list_add_service Лист | Сервис"

    await add_service_list(session, list_name)
    await add_service(session, service_name)

    result = await session.execute(
        select(ServiceListItem).where(ServiceListItem.list_name == list_name, ServiceListItem.service_name == service_name)
    )
    exists = result.scalars().first()
    if not exists:
        session.add(ServiceListItem(list_name=list_name, service_name=service_name))
        await session.commit()

    return f"OK. Сервис {service_name} добавлен в лист {list_name}"


async def lists_text(session: AsyncSession) -> str:
    result = await session.execute(select(ServiceList).where(ServiceList.is_active == True).order_by(ServiceList.name.asc()))
    lists = result.scalars().all()
    if not lists:
        return "Листов пока нет."

    lines = ["Листы сервисов:\n"]
    for item in lists:
        result_items = await session.execute(select(ServiceListItem.service_name).where(ServiceListItem.list_name == item.name))
        services = [row[0] for row in result_items.fetchall()]
        lines.append(f"{item.name}: {', '.join(services) if services else 'пусто'}")

    return "\n".join(lines)


# ---------- Admin order control ----------

async def get_problem_order_rows(session: AsyncSession, limit: int = 20):
    result = await session.execute(
        select(Order)
        .where(Order.status == "problem")
        .order_by(Order.updated_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_recent_order_rows(session: AsyncSession, limit: int = 20):
    result = await session.execute(
        select(Order)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


def order_status_label(status: str | None) -> str:
    labels = {
        "waiting_service": "⏳ ждёт выбор сервиса",
        "waiting_supplier_number": "📞 ждёт номер от поставщика",
        "number_sent_to_customer": "📩 номер отправлен покупателю",
        "waiting_supplier_code": "🔑 ждёт код от поставщика",
        "code_sent_to_customer": "🔐 код отправлен покупателю",
        "confirmed": "✅ закрыт успешно",
        "problem": "⚠️ проблема",
    }
    return labels.get(status or "", status or "неизвестно")


def order_card_text(order: Order) -> str:
    return (
        "🧾 Карточка заказа\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Статус: {order_status_label(order.status)}\n\n"
        f"Покупатель ID: {order.customer_telegram_id or order.buyer_chat_id or 'нет'}\n"
        f"Username: @{order.customer_username or 'нет'}\n\n"
        f"Товар ID: {order.product_id or 'нет'}\n"
        f"Товар: {order.product_name or 'нет'}\n"
        f"Сервис: {order.service_name or 'нет'}\n\n"
        f"Номер: {order.phone_number or 'нет'}\n"
        f"Код: {order.verification_code or 'нет'}\n\n"
        f"Создан: {order.created_at}\n"
        f"Обновлён: {order.updated_at}"
    )


async def set_order_status(session: AsyncSession, order_id: int, status: str) -> str:
    order = await get_order_by_id(session, order_id)
    if not order:
        return "Заказ не найден."

    order.status = status
    order.updated_at = datetime.utcnow()
    await session.commit()
    return f"OK. Статус заказа #{order.operation_id} изменён на {order_status_label(status)}."


async def get_order_supplier(session: AsyncSession, order_id: int) -> Supplier | None:
    order = await get_order_by_id(session, order_id)
    if not order:
        return None
    return await find_supplier_for_order(session, order)


async def admin_create_supplier_request_for_order(
    session: AsyncSession,
    order_id: int,
    request_type: str,
) -> tuple[bool, str, Order | None, Supplier | None]:
    order = await get_order_by_id(session, order_id)
    if not order:
        return False, "Заказ не найден.", None, None

    supplier = await find_supplier_for_order(session, order)
    if not supplier:
        return False, "Поставщик для этого заказа не найден.", order, None

    if request_type == "number":
        order.status = "waiting_supplier_number"
    elif request_type == "code":
        order.status = "waiting_supplier_code"

    order.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(order)

    await create_supplier_request(session, order.id, supplier.telegram_id, request_type)
    return True, "OK. Запрос создан.", order, supplier
