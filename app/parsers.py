import re
from decimal import Decimal


def search_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        return None


def search_str(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None

    value = match.group(1).strip()
    return value if value else None


def extract_purchase_data(text: str) -> dict | None:
    """
    Парсит сообщение от Admaker/shop-бота.

    Поддерживает форматы:
    - PAID
    - оплатил
    - оплачено
    - новая покупка через cryptobot
    """

    upper = text.upper()

    paid_markers = [
        "PAID",
        "ОПЛАТИЛ",
        "ОПЛАТИЛА",
        "ОПЛАЧЕН",
        "ОПЛАЧЕНО",
        "НОВАЯ ПОКУПКА",
        "НОВАЯ ПОКУПКА ЧЕРЕЗ CRYPTOBOT",
    ]

    if not any(marker in upper for marker in paid_markers):
        return None

    operation_id = (
        search_int(r"ID операции:\s*(\d+)", text)
        or search_int(r"Операция:\s*#?(\d+)", text)
        or search_int(r"Заказ[:\s#]*(\d+)", text)
        or search_int(r"ORDER[:\s#]*(\d+)", text)
        or search_int(r"сч[её]т\s*#?[A-ZА-Я]*?(\d+)", text)
    )

    external_id = (
        search_str(r"Внешний ID:\s*([^\n]+)", text)
        or search_str(r"External ID:\s*([^\n]+)", text)
    )

    customer_telegram_id = (
        search_int(r"ID пользователя:\s*(\d+)", text)
        or search_int(r"Покупатель ID:\s*(\d+)", text)
        or search_int(r"Telegram ID:\s*(\d+)", text)
        or search_int(r"🆔\s*ID:\s*(\d+)", text)
        or search_int(r"\bID:\s*(\d{5,})", text)
    )

    customer_username = (
        search_str(r"Пользователь:\s*@?([A-Za-z0-9_]+)", text)
        or search_str(r"Покупатель:\s*@?([A-Za-z0-9_]+)", text)
        or search_str(r"Username:\s*@?([A-Za-z0-9_]+)", text)
        or search_str(r"👤\s*Пользователь:\s*@?([A-Za-z0-9_]+)", text)
        or search_str(r"@([A-Za-z0-9_]{3,})", text)
    )

    product_id = (
        search_int(r"ID товара:\s*(\d+)", text)
        or search_int(r"Товар ID:\s*(\d+)", text)
    )

    product_name = (
        search_str(r"Купил:\s*(.+)", text)
        or search_str(r"📦\s*Купил:\s*(.+)", text)
        or search_str(r"Товар:\s*(.+)", text)
        or search_str(r"Product:\s*(.+)", text)
    )

    if product_name:
        product_name = product_name.strip()

    amount_raw = (
        search_str(r"Сумма:\s*([\d.,]+)", text)
        or search_str(r"💵\s*Сумма:\s*([\d.,]+)", text)
    )

    amount = None
    if amount_raw:
        try:
            amount = Decimal(amount_raw.replace(",", "."))
        except Exception:
            amount = None

    currency = (
        search_str(r"Сумма:\s*[\d.,]+\s*([A-ZА-Яа-я]+)", text)
        or search_str(r"💵\s*Сумма:\s*[\d.,]+\s*([A-ZА-Яа-я]+)", text)
    )

    if not operation_id:
        return None

    return {
        "operation_id": operation_id,
        "external_id": external_id,
        "customer_telegram_id": customer_telegram_id,
        "customer_username": customer_username,
        "product_id": product_id,
        "product_name": product_name or "Без названия",
        "amount": amount,
        "currency": currency,
        "raw_message": text,
    }


def extract_clean_product_answer(text: str) -> str:
    text = text.strip()

    prefixes = [
        "товар:",
        "код:",
        "номер:",
        "ответ:",
        "держи:",
        "выдача:",
    ]

    lower = text.lower()

    for prefix in prefixes:
        if lower.startswith(prefix):
            return text[len(prefix):].strip()

    return text


def extract_phone(text: str) -> str | None:
    match = re.search(r"(\+?\d[\d\s\-\(\)]{8,}\d)", text)
    if not match:
        return None

    phone = match.group(1)
    phone = re.sub(r"[^\d+]", "", phone)

    if phone.startswith("++"):
        phone = phone.replace("++", "+")

    if len(re.sub(r"\D", "", phone)) < 9:
        return None

    return phone


def extract_code(text: str) -> str | None:
    patterns = [
        r"код[:\s\-]*([0-9]{4,12})",
        r"code[:\s\-]*([0-9]{4,12})",
        r"\b([0-9]{4,12})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    return None