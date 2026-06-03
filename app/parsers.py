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
    Парсит сообщение о покупке от shop-бота.

    Главное:
    - заказ принимаем только если есть PAID
    - достаём ID операции
    - достаём ID пользователя
    - достаём username
    - достаём товар
    """

    if "PAID" not in text.upper():
        return None

    operation_id = search_int(r"ID операции:\s*(\d+)", text)
    external_id = search_str(r"Внешний ID:\s*([^\n]+)", text)

    customer_telegram_id = search_int(r"ID пользователя:\s*(\d+)", text)

    customer_username = search_str(r"Пользователь:\s*@?([A-Za-z0-9_]+)", text)

    product_id = search_int(r"ID товара:\s*(\d+)", text)

    product_name = search_str(r"Купил:\s*(.+)", text)
    if product_name:
        product_name = product_name.strip()

    amount_raw = search_str(r"Сумма:\s*([\d.,]+)", text)
    amount = None
    if amount_raw:
        try:
            amount = Decimal(amount_raw.replace(",", "."))
        except Exception:
            amount = None

    currency = search_str(r"Сумма:\s*[\d.,]+\s*([A-ZА-Яа-я]+)", text)

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


def extract_phone(text: str) -> str | None:
    """
    Достаёт номер телефона из сообщения поставщика.
    Примеры:
    +79990000000
    79990000000
    Номер: +7 999 000 00 00
    """

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
    """
    Достаёт код из сообщения поставщика.
    Берёт цифровой код 4-8 цифр.
    """

    patterns = [
        r"код[:\s\-]*([0-9]{4,8})",
        r"code[:\s\-]*([0-9]{4,8})",
        r"\b([0-9]{4,8})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    return None