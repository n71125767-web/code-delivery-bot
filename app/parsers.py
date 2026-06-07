import re
from decimal import Decimal, InvalidOperation


def _search(pattern: str, text: str, flags: int = re.I | re.M):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def extract_purchase_data(text: str) -> dict | None:
    if not text:
        return None
    operation = _search(r"(?:ID\s*операции|Заказ|Operation\s*ID)\s*[:#№-]*\s*(\d+)", text)
    status = _search(r"Статус\s*:\s*([A-ZА-Я_]+)", text)
    paid_marker = bool(re.search(r"(?:Статус\s*:\s*PAID|Новая\s+покупка|Оплачен\s*:)", text, re.I))
    if not operation or not paid_marker:
        return None
    product_id = _search(r"ID\s*товара\s*:\s*(\d+)", text)
    user_id = _search(r"ID\s*пользователя\s*:\s*(\d+)", text) or _search(r"(?<!Внешний\s)ID\s*:\s*(\d+)", text)
    username = _search(r"Пользователь\s*:\s*@?([A-Za-z0-9_]+)", text)
    product_name = _search(r"(?:Купил|Товар)\s*:\s*(.+)", text)
    external_id = _search(r"Внешний\s*ID\s*:\s*([^\n]+)", text)
    amount_raw = _search(r"Сумма\s*:\s*([0-9.,]+)", text)
    currency = _search(r"Сумма\s*:\s*[0-9.,]+\s*([A-Z]{3,5})", text)
    try:
        amount = float(Decimal(amount_raw.replace(',', '.'))) if amount_raw else None
    except (InvalidOperation, ValueError):
        amount = None
    return {
        'operation_id': int(operation),
        'external_id': external_id,
        'customer_telegram_id': int(user_id) if user_id else None,
        'customer_username': username,
        'product_id': int(product_id) if product_id else None,
        'product_name': product_name,
        'amount': amount,
        'currency': currency,
        'status': status or 'PAID',
        'raw_message': text,
    }


def extract_phone(text: str) -> str | None:
    if not text:
        return None
    candidates = re.findall(r"\+?\d[\d\s()\-]{7,18}\d", text)
    for item in candidates:
        normalized = ('+' if item.strip().startswith('+') else '') + re.sub(r'\D', '', item)
        digits = re.sub(r'\D', '', normalized)
        if 8 <= len(digits) <= 15:
            return normalized
    return None


def extract_code(text: str) -> str | None:
    if not text:
        return None
    explicit = re.search(r"(?:код|code)\s*[:#-]?\s*(\d{3,10})", text, re.I)
    if explicit:
        return explicit.group(1)
    values = re.findall(r"(?<!\d)(\d{3,10})(?!\d)", text)
    return values[-1] if values else None
