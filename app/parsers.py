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