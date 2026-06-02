import re


def extract_purchase_data(text: str) -> dict | None:
    if "Статус: PAID" not in text and "Статус:PAID" not in text:
        return None

    operation_id = search_int(r"ID операции:\s*(\d+)", text)
    customer_telegram_id = search_int(r"ID пользователя:\s*(\d+)", text)
    product_id = search_int(r"ID товара:\s*(\d+)", text)

    external_id = search_text(r"Внешний ID:\s*([^\n]+)", text)
    username = search_text(r"Пользователь:\s*(@\w+)", text)
    product_name = search_text(r"Купил:\s*(.+)", text)

    amount = None
    currency = None

    amount_match = re.search(r"Сумма:\s*([\d.]+)\s*([A-Z]+)", text)
    if amount_match:
        amount = float(amount_match.group(1))
        currency = amount_match.group(2)

    if not operation_id or not customer_telegram_id or not product_id or not product_name:
        return None

    return {
        "operation_id": operation_id,
        "external_id": external_id,
        "customer_telegram_id": customer_telegram_id,
        "customer_username": username,
        "product_id": product_id,
        "product_name": product_name,
        "amount": amount,
        "currency": currency,
        "raw_message": text,
    }


def extract_phone(text: str) -> str | None:
    clean = text.replace(" ", "")
    match = re.search(r"\+?\d{8,15}", clean)

    if not match:
        return None

    return match.group(0)


def extract_code(text: str) -> str | None:
    clean = text.replace(" ", "")
    matches = re.findall(r"\d{4,12}", clean)

    if not matches:
        return None

    return matches[-1]


def search_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)

    if not match:
        return None

    return int(match.group(1))


def search_text(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)

    if not match:
        return None

    return match.group(1).strip()
    from datetime import datetime, timedelta
from sqlalchemy import select
from app.models import Order


def normalize_username(username: str | None) -> str | None:
    if not username:
        return None

    username = username.strip().lower()

    if username.startswith("@"):
        username = username[1:]

    return username or None


async def find_waiting_service_order_by_id_or_username_today(
    session,
    customer_telegram_id: int,
    customer_username: str | None,
    hours: int = 24,
) -> Order | None:
    """
    Ищем заказ за последние N часов.

    Сначала ищем по Telegram ID.
    Если не нашли — ищем по username.
    """

    time_limit = datetime.utcnow() - timedelta(hours=hours)

    # 1. Сначала ищем по Telegram ID — это самый надёжный вариант.
    result = await session.scalars(
        select(Order)
        .where(Order.customer_telegram_id == customer_telegram_id)
        .where(Order.status == "waiting_service")
        .where(Order.created_at >= time_limit)
        .order_by(Order.id.desc())
    )

    order = result.first()

    if order:
        return order

    # 2. Если по ID не нашли — пробуем по username.
    username_clean = normalize_username(customer_username)

    if not username_clean:
        return None

    result = await session.scalars(
        select(Order)
        .where(Order.customer_username.is_not(None))
        .where(Order.status == "waiting_service")
        .where(Order.created_at >= time_limit)
        .order_by(Order.id.desc())
    )

    orders = list(result.all())

    for order in orders:
        order_username = normalize_username(order.customer_username)

        if order_username == username_clean:
            return order

    return None


async def find_number_sent_order_by_id_or_username_today(
    session,
    customer_telegram_id: int,
    customer_username: str | None,
    hours: int = 24,
) -> Order | None:
    """
    Ищем заказ за последние N часов, где покупателю уже выдали номер.
    Нужно для сообщения 'код отправлен'.
    """

    time_limit = datetime.utcnow() - timedelta(hours=hours)

    # 1. Сначала по Telegram ID.
    result = await session.scalars(
        select(Order)
        .where(Order.customer_telegram_id == customer_telegram_id)
        .where(Order.status == "number_sent_to_customer")
        .where(Order.created_at >= time_limit)
        .order_by(Order.id.desc())
    )

    order = result.first()

    if order:
        return order

    # 2. Потом по username.
    username_clean = normalize_username(customer_username)

    if not username_clean:
        return None

    result = await session.scalars(
        select(Order)
        .where(Order.customer_username.is_not(None))
        .where(Order.status == "number_sent_to_customer")
        .where(Order.created_at >= time_limit)
        .order_by(Order.id.desc())
    )

    orders = list(result.all())

    for order in orders:
        order_username = normalize_username(order.customer_username)

        if order_username == username_clean:
            return order

    return None