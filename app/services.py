from datetime import datetime, timedelta
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import POPULAR_SERVICE_THRESHOLD, PROBLEM_COOLDOWN_SECONDS
from app.models import Order, SupplierRequest, Supplier, SupplierProduct, ServiceOption, ServiceList, ServiceListItem, TextTemplate, Cooldown, AdminUser, BugReport


ACTIVE_CUSTOMER_STATUSES = [
    "waiting_service",
    "waiting_proxy_country",
    "waiting_proxy_period",
    "waiting_proxy_confirm",
    "proxy_processing",
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

        # Идемпотентность: повторное уведомление Admaker обновляет данные,
        # но никогда не возвращает уже обработанный заказ в начало сценария.
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
            SupplierRequest.status.in_(["sent", "in_progress", "selected"]),
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


async def mark_code_waiting_buyer_confirm(session: AsyncSession, request_id: int) -> None:
    """
    После отправки кода поставщиком заявка НЕ закрывается окончательно.
    Она остаётся видимой поставщику как "ждём подтверждение покупателя".
    Закрывать её можно только после кнопки покупателя OK.
    """
    request = await get_supplier_request_by_id(session, request_id)
    if request:
        request.status = "waiting_buyer_confirm"
        request.answered_at = datetime.utcnow()


async def close_waiting_supplier_requests_for_order(session: AsyncSession, order_id: int) -> int:
    """
    Закрывает supplier_requests по заказу только после подтверждения покупателем.
    Возвращает количество обновлённых заявок.
    """
    result = await session.execute(
        select(SupplierRequest).where(
            SupplierRequest.order_id == order_id,
            SupplierRequest.status.in_(["waiting_buyer_confirm", "sent", "selected", "in_progress"]),
        )
    )
    requests = result.scalars().all()
    for request in requests:
        request.status = "answered"
        if not request.answered_at:
            request.answered_at = datetime.utcnow()
    return len(requests)


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


async def get_supplier_request_by_id(session: AsyncSession, request_id: int) -> SupplierRequest | None:
    result = await session.execute(select(SupplierRequest).where(SupplierRequest.id == request_id))
    return result.scalars().first()


async def get_supplier_request_order(session: AsyncSession, request_id: int) -> tuple[SupplierRequest | None, Order | None]:
    request = await get_supplier_request_by_id(session, request_id)
    if not request:
        return None, None
    order = await get_order_by_id(session, request.order_id)
    return request, order


async def mark_supplier_request_in_progress(session: AsyncSession, request_id: int) -> tuple[bool, str, SupplierRequest | None, Order | None]:
    request, order = await get_supplier_request_order(session, request_id)
    if not request or not order:
        return False, "Заявка или заказ не найдены.", request, order

    if request.status == "answered":
        return False, "Эта заявка уже обработана.", request, order

    if request.status not in ["sent", "in_progress"]:
        return False, "Эта заявка неактивна.", request, order

    request.status = "in_progress"
    order.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(request)
    await session.refresh(order)

    return True, "OK. Заявка взята в работу.", request, order


async def find_active_supplier_request(session: AsyncSession, supplier_telegram_id: int) -> SupplierRequest | None:
    result = await session.execute(
        select(SupplierRequest)
        .where(SupplierRequest.supplier_telegram_id == supplier_telegram_id)
        .where(SupplierRequest.status.in_(["in_progress", "selected", "sent"]))
        .order_by(SupplierRequest.status.asc(), SupplierRequest.created_at.asc())
    )
    return result.scalars().first()


async def supplier_pending_rows(session: AsyncSession, supplier_id: int, page: int, page_size: int):
    result_total = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status.in_(["sent", "in_progress", "waiting_buyer_confirm"]),
        )
    )
    total = result_total or 0
    max_page = max((total - 1) // page_size, 0)
    page = max(0, min(page, max_page))

    result = await session.execute(
        select(SupplierRequest, Order)
        .join(Order, SupplierRequest.order_id == Order.id)
        .where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status.in_(["sent", "in_progress", "waiting_buyer_confirm"]),
        )
        .order_by(SupplierRequest.created_at.asc())
        .offset(page * page_size)
        .limit(page_size)
    )
    return result.fetchall(), max_page


async def set_supplier_request_message_id(session: AsyncSession, request_id: int, message_id: int | None) -> None:
    request = await get_supplier_request_by_id(session, request_id)
    if not request:
        return
    request.supplier_message_id = message_id
    await session.commit()


# ---------- Final UX helpers ----------

async def create_action_event(
    session: AsyncSession,
    event_type: str,
    text: str | None = None,
    user_id: int | None = None,
    order_id: int | None = None,
) -> None:
    try:
        session.add(ActionEvent(user_id=user_id, order_id=order_id, event_type=event_type, text=text))
        await session.commit()
    except Exception:
        # Лог событий не должен ломать основной сценарий.
        await session.rollback()




async def supplier_rows_by_filter(session: AsyncSession, supplier_id: int, mode: str, page: int, page_size: int):
    # В панели поставщика показываем не только новые/в работе,
    # но и заявки, где код уже отправлен покупателю и ждём OK.
    visible_statuses = ["sent", "in_progress", "selected", "waiting_buyer_confirm"]

    if mode == "number":
        statuses = visible_statuses
        req_type = "number"
    elif mode == "code":
        statuses = visible_statuses
        req_type = "code"
    elif mode == "active":
        statuses = visible_statuses
        req_type = None
    else:
        statuses = visible_statuses
        req_type = None

    conditions = [
        SupplierRequest.supplier_telegram_id == supplier_id,
        SupplierRequest.status.in_(statuses),
    ]
    if req_type:
        conditions.append(SupplierRequest.request_type == req_type)

    total = await session.scalar(select(func.count(SupplierRequest.id)).where(*conditions))
    total = total or 0
    max_page = max((total - 1) // page_size, 0)
    page = max(0, min(page, max_page))

    result = await session.execute(
        select(SupplierRequest, Order)
        .join(Order, SupplierRequest.order_id == Order.id)
        .where(*conditions)
        .order_by(SupplierRequest.created_at.asc())
        .offset(page * page_size)
        .limit(page_size)
    )
    rows = result.fetchall()

    return rows, max_page


async def supplier_filter_text(mode: str, rows_count: int, page: int, max_page: int) -> str:
    titles = {
        "active": "⏳ Все активные заявки",
        "number": "📞 Ждут номер",
        "code": "🔑 Ждут код",
        "problem": "⚠️ Проблемные",
    }
    title = titles.get(mode, "⏳ Заявки")
    if rows_count == 0:
        return f"{title}\n\nЗаявок нет."
    return f"{title}\n\nСтраница {page + 1}/{max_page + 1}\nВыберите заявку кнопкой ниже."










# ---------------- Section lists patch v7 ----------------
async def get_buyer_order_rows(session: AsyncSession, user_id: int, username: str | None, limit: int = 10):
    clean_username = (username or "").replace("@", "").lower()

    query = (
        select(Order)
        .where((Order.customer_telegram_id == user_id) | (Order.buyer_chat_id == user_id))
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    orders = result.scalars().all()

    if not orders and clean_username:
        result = await session.execute(
            select(Order)
            .where(func.lower(Order.customer_username) == clean_username)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        orders = result.scalars().all()

    return orders






# -----------------------------------------------------


# ---------- Extra admins + bug reports ----------

async def is_db_admin(session: AsyncSession, telegram_id: int | None) -> bool:
    if not telegram_id:
        return False
    result = await session.execute(
        select(AdminUser).where(AdminUser.telegram_id == telegram_id, AdminUser.is_active == True)
    )
    return result.scalars().first() is not None


async def add_admin_user(session: AsyncSession, telegram_id: int, name: str | None, added_by: int | None = None) -> AdminUser:
    result = await session.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id))
    admin = result.scalars().first()
    if admin:
        admin.name = name or admin.name
        admin.is_active = True
        admin.added_by = added_by or admin.added_by
    else:
        admin = AdminUser(telegram_id=telegram_id, name=name, is_active=True, added_by=added_by)
        session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin


async def remove_admin_user(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id))
    admin = result.scalars().first()
    if not admin:
        return False
    admin.is_active = False
    await session.commit()
    return True




async def get_admin_users(session: AsyncSession, include_disabled: bool = False) -> list[AdminUser]:
    query = select(AdminUser).order_by(AdminUser.created_at.desc())
    if not include_disabled:
        query = query.where(AdminUser.is_active == True)
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_bug_report(
    session: AsyncSession,
    reporter_id: int | None,
    reporter_username: str | None,
    role: str | None,
    text: str,
) -> BugReport:
    report = BugReport(
        reporter_id=reporter_id,
        reporter_username=reporter_username,
        role=role,
        text=text,
        status="new",
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


# ---------------- Full shop visual services patch v15 ----------------
# Единый визуал текстов профилей/статистики/заказов.
# Эти функции переопределяют старые def выше.


def _fmt_money(value) -> str:
    try:
        num = float(value or 0)
    except Exception:
        num = 0.0
    if num.is_integer():
        return f"{int(num)} RUB"
    return f"{num:.2f} RUB"


def _fmt_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


async def _buyer_money_stats(session: AsyncSession, user_id: int, username: str | None):
    clean_username = (username or "").replace("@", "").lower()
    base_filter = (Order.customer_telegram_id == user_id) | (Order.buyer_chat_id == user_id)
    if clean_username:
        base_filter = base_filter | (func.lower(Order.customer_username) == clean_username)

    total_orders = await session.scalar(select(func.count(Order.id)).where(base_filter)) or 0
    total_sum = await session.scalar(select(func.coalesce(func.sum(Order.amount), 0)).where(base_filter)) or 0
    avg_sum = await session.scalar(select(func.coalesce(func.avg(Order.amount), 0)).where(base_filter)) or 0
    max_sum = await session.scalar(select(func.coalesce(func.max(Order.amount), 0)).where(base_filter)) or 0

    now = datetime.utcnow()
    sum_7 = await session.scalar(select(func.coalesce(func.sum(Order.amount), 0)).where(base_filter, Order.created_at >= now - timedelta(days=7))) or 0
    sum_30 = await session.scalar(select(func.coalesce(func.sum(Order.amount), 0)).where(base_filter, Order.created_at >= now - timedelta(days=30))) or 0
    sum_180 = await session.scalar(select(func.coalesce(func.sum(Order.amount), 0)).where(base_filter, Order.created_at >= now - timedelta(days=180))) or 0

    return total_orders, total_sum, avg_sum, max_sum, sum_7, sum_30, sum_180


async def buyer_profile_text(session: AsyncSession, user_id: int, username: str | None) -> str:
    active_order = await find_active_order_for_customer(session, user_id, username)
    total_orders, total_sum, avg_sum, max_sum, sum_7, sum_30, sum_180 = await _buyer_money_stats(session, user_id, username)

    text = (
        "👤 › Профиль покупателя\n\n"
        "Здесь вы можете посмотреть информацию о вашем аккаунте и покупках в магазине.\n\n"
        f"Telegram ID — {user_id}\n"
        f"Username — @{username or 'нет'}\n\n"
        f"Всего {total_orders} заказов на сумму {_fmt_money(total_sum)}\n"
        f"├ Средний — {_fmt_money(avg_sum)}\n"
        f"├ Рекордный — {_fmt_money(max_sum)}\n"
        f"├ За 7 дней — {_fmt_money(sum_7)}\n"
        f"├ За 30 дней — {_fmt_money(sum_30)}\n"
        f"└ За 180 дней — {_fmt_money(sum_180)}\n\n"
    )

    if active_order:
        text += (
            "📦 Активный заказ\n"
            f"├ Заказ — #{active_order.operation_id}\n"
            f"├ Статус — {order_status_label(active_order.status)}\n"
            f"├ Товар — {active_order.product_name or 'нет'}\n"
            f"└ Сервис — {active_order.service_name or 'не выбран'}"
        )
    else:
        text += "📦 Активный заказ\n└ Сейчас активного заказа нет"

    return text


async def buyer_orders_text(session: AsyncSession, user_id: int, username: str | None, limit: int = 10) -> str:
    orders = await get_buyer_order_rows(session, user_id, username, limit)
    if not orders:
        return (
            "🧾 › Мои заказы\n\n"
            "У вас пока нет заказов.\n\n"
            "Когда появится покупка, она будет отображаться в этом разделе."
        )

    lines = ["🧾 › Мои заказы", "", "Последние покупки:", ""]
    for index, order in enumerate(orders, start=1):
        last = index == len(orders)
        prefix = "└" if last else "├"
        lines.append(f"{prefix} #{order.operation_id} — {order_status_label(order.status)}")
        lines.append(f"   Товар — {order.product_name or 'нет'}")
        lines.append(f"   Сервис — {order.service_name or 'не выбран'}")
        if order.amount:
            lines.append(f"   Сумма — {_fmt_money(order.amount)}")
    return "\n".join(lines)


def buyer_order_card_text(order: Order | None) -> str:
    if not order:
        return "🧾 › Заказ не найден."
    return (
        "🧾 › Карточка заказа\n\n"
        f"Заказ — #{order.operation_id}\n"
        f"Статус — {order_status_label(order.status)}\n\n"
        "Детали\n"
        f"├ Товар — {order.product_name or 'нет'}\n"
        f"├ Сервис — {order.service_name or 'не выбран'}\n"
        f"├ Номер — {order.phone_number or 'ещё нет'}\n"
        f"└ Код — {order.verification_code or 'ещё нет'}\n\n"
        "Доступные действия показаны кнопками ниже."
    )


async def supplier_profile_text(session: AsyncSession, supplier_id: int, username: str | None) -> str:
    active_count = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status.in_(["sent", "selected", "in_progress", "waiting_buyer_confirm"]),
        )
    ) or 0
    done_count = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "answered",
        )
    ) or 0
    wait_ok = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.status == "waiting_buyer_confirm",
        )
    ) or 0
    number_count = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.request_type == "number",
            SupplierRequest.status.in_(["sent", "selected", "in_progress"]),
        )
    ) or 0
    code_count = await session.scalar(
        select(func.count(SupplierRequest.id)).where(
            SupplierRequest.supplier_telegram_id == supplier_id,
            SupplierRequest.request_type == "code",
            SupplierRequest.status.in_(["sent", "selected", "in_progress"]),
        )
    ) or 0
    return (
        "🚚 › Профиль поставщика\n\n"
        "Здесь отображается ваша текущая нагрузка и выполненные заявки.\n\n"
        f"Telegram ID — {supplier_id}\n"
        f"Username — @{username or 'нет'}\n\n"
        f"Всего выполнено — {_fmt_int(done_count)}\n"
        f"├ Активные заявки — {_fmt_int(active_count)}\n"
        f"├ Ждут номер — {_fmt_int(number_count)}\n"
        f"├ Ждут код — {_fmt_int(code_count)}\n"
        f"└ Ждут OK покупателя — {_fmt_int(wait_ok)}"
    )


async def admin_profile_text(session: AsyncSession, admin_id: int, username: str | None) -> str:
    total_orders = await session.scalar(select(func.count(Order.id))) or 0
    problem_orders = await session.scalar(select(func.count(Order.id)).where(Order.status == "problem")) or 0
    active_suppliers = await session.scalar(select(func.count(Supplier.id)).where(Supplier.is_active == True)) or 0
    active_admins = await session.scalar(select(func.count(AdminUser.id)).where(AdminUser.is_active == True)) or 0
    return (
        "👮 › Профиль админа\n\n"
        "Служебная информация по управлению магазином.\n\n"
        f"Telegram ID — {admin_id}\n"
        f"Username — @{username or 'нет'}\n\n"
        "Система\n"
        f"├ Всего заказов — {_fmt_int(total_orders)}\n"
        f"├ Проблемные — {_fmt_int(problem_orders)}\n"
        f"├ Активные поставщики — {_fmt_int(active_suppliers)}\n"
        f"└ Доп. админы — {_fmt_int(active_admins)}"
    )


async def admin_stats_text(session: AsyncSession) -> str:
    total = await session.scalar(select(func.count(Order.id))) or 0
    confirmed = await session.scalar(select(func.count(Order.id)).where(Order.status == "confirmed")) or 0
    problem = await session.scalar(select(func.count(Order.id)).where(Order.status == "problem")) or 0
    waiting_number = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_supplier_number")) or 0
    waiting_code = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_supplier_code")) or 0
    code_sent = await session.scalar(select(func.count(Order.id)).where(Order.status == "code_sent_to_customer")) or 0

    result = await session.execute(
        select(ServiceOption.name, ServiceOption.usage_count)
        .where(ServiceOption.is_active == True)
        .order_by(ServiceOption.usage_count.desc())
        .limit(5)
    )
    top_services = result.fetchall()

    lines = [
        "📈 › Статистика магазина",
        "",
        "Заказы",
        f"├ Всего — {_fmt_int(total)}",
        f"├ Успешные — {_fmt_int(confirmed)}",
        f"├ Проблемные — {_fmt_int(problem)}",
        f"├ Ждут номер — {_fmt_int(waiting_number)}",
        f"├ Ждут код — {_fmt_int(waiting_code)}",
        f"└ Ждут OK покупателя — {_fmt_int(code_sent)}",
        "",
        "🔥 Популярные сервисы",
    ]
    if not top_services:
        lines.append("└ Пока нет данных")
    else:
        for i, (name, count) in enumerate(top_services, start=1):
            prefix = "└" if i == len(top_services) else "├"
            lines.append(f"{prefix} {name} — {count}")
    return "\n".join(lines)


async def list_admin_users_text(session: AsyncSession, env_admin_ids: list[int]) -> str:
    result = await session.execute(select(AdminUser).order_by(AdminUser.created_at.desc()))
    admins = result.scalars().all()
    lines = ["👮 › Админы", "", "Главные админы из Render ADMIN_IDS:"]
    if env_admin_ids:
        for i, item in enumerate(env_admin_ids, start=1):
            prefix = "└" if i == len(env_admin_ids) and not admins else "├"
            lines.append(f"{prefix} {item}")
    else:
        lines.append("└ не заданы")
    lines.append("")
    lines.append("Доп. админы из базы:")
    if not admins:
        lines.append("└ пока нет")
    else:
        for i, admin in enumerate(admins, start=1):
            prefix = "└" if i == len(admins) else "├"
            state = "активен" if admin.is_active else "выключен"
            lines.append(f"{prefix} {admin.telegram_id} — {admin.name or 'без имени'} — {state}")
    return "\n".join(lines)


def supplier_section_title(mode: str) -> str:
    return {
        "pending": "⏳ › Ожидающие заявки",
        "active": "📊 › Все активные заявки",
        "number": "📞 › Ждут номер",
        "code": "🔑 › Ждут код",
    }.get(mode, "📋 › Заявки")


def supplier_section_text(mode: str, rows_count: int, page: int, max_page: int) -> str:
    title = supplier_section_title(mode)
    if rows_count == 0:
        return (
            f"{title}\n\n"
            "В этом разделе сейчас нет заявок.\n\n"
            "Кнопками ниже можно вернуться назад или открыть другой раздел."
        )
    return (
        f"{title}\n\n"
        f"Страница — {page + 1}/{max_page + 1}\n"
        f"Найдено на странице — {rows_count}\n\n"
        "Выберите конкретную заявку кнопкой ниже."
    )
# --------------------------------------------------
