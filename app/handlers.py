import asyncio
import logging
import re
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message, CallbackQuery

from app.config import (
    ADMIN_IDS,
    SHOP_BOT_USERNAME,
    IGNORE_OTHER_BOTS,
    ADMIN_BUSINESS_CONNECTION_ID,
    SERVICE_OPTIONS,
)
from app.database import SessionLocal
from app.keyboards import confirm_keyboard, number_keyboard, service_keyboard
from app.parsers import extract_purchase_data, extract_phone, extract_code
from app.senders import safe_send_message, answer_message
from app.services import (
    create_or_update_order_from_purchase,
    find_active_order_for_customer,
    find_waiting_service_order_for_customer,
    create_supplier_request,
    find_waiting_supplier_request,
    get_order_by_id,
    get_status_text,
    get_last_orders_text,
    set_customer_by_order_id,
    add_supplier,
    remove_supplier,
    list_suppliers_text,
    bind_supplier_to_product,
    unbind_supplier_from_product,
    find_supplier_for_order,
)

logger = logging.getLogger(__name__)

CONTACT_PATTERNS = [
    r"@[a-zA-Z0-9_]{3,}",
    r"(?:https?://)?t\.me/[a-zA-Z0-9_]{3,}",
    r"(?:https?://)?telegram\.me/[a-zA-Z0-9_]{3,}",
    r"\b(?:мой|моя|напиши|пиши|свяжись|связь|контакт|личка|лс|л/с)\b.*\b[a-zA-Z0-9_]{4,}\b",
    r"\+?\d[\d\s\-\(\)]{8,}\d",
]

CONTACT_RE = re.compile("|".join(CONTACT_PATTERNS), re.IGNORECASE)


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def get_business_id(message: Message | None, fallback: str | None = None) -> str | None:
    if message is None:
        return fallback or ADMIN_BUSINESS_CONNECTION_ID
    return getattr(message, "business_connection_id", None) or fallback or ADMIN_BUSINESS_CONNECTION_ID


def normalize_service_from_text(text: str) -> str | None:
    clean = text.strip().lower()
    for service in SERVICE_OPTIONS:
        service_clean = service.lower()
        if clean == service_clean or service_clean in clean:
            return service
    return None


def contains_forbidden_contact(text: str) -> bool:
    return bool(CONTACT_RE.search(text or ""))


async def delete_later(bot: Bot, chat_id: int, message_id: int, delay: int = 20) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.info("Message delete skipped chat_id=%s message_id=%s", chat_id, message_id)


async def maybe_delete_message(bot: Bot, message: Message, delay: int = 20) -> None:
    try:
        asyncio.create_task(delete_later(bot, message.chat.id, message.message_id, delay))
    except Exception:
        logger.exception("Failed to schedule delete")


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text)


# ---------------- admin commands ----------------
async def process_admin_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user or not is_admin(message.from_user.id):
        return False

    text = (message.text or "").strip()
    parts = text.split()

    if text == "/suppliers":
        async with SessionLocal() as session:
            result = await list_suppliers_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/add_supplier"):
        if len(parts) < 3:
            await answer_message(bot, message, "Формат:\n/add_supplier TELEGRAM_ID Имя", business_connection_id)
            return True
        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True
        name = " ".join(parts[2:]).strip()
        async with SessionLocal() as session:
            supplier = await add_supplier(session, supplier_id, name)
        await answer_message(bot, message, f"OK. Поставщик добавлен: {supplier.telegram_id} {supplier.name}", business_connection_id)
        return True

    if text.startswith("/remove_supplier"):
        if len(parts) != 2:
            await answer_message(bot, message, "Формат:\n/remove_supplier TELEGRAM_ID", business_connection_id)
            return True
        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True
        async with SessionLocal() as session:
            ok = await remove_supplier(session, supplier_id)
        await answer_message(bot, message, "OK. Поставщик выключен." if ok else "Поставщик не найден.", business_connection_id)
        return True

    if text.startswith("/bind_supplier"):
        if len(parts) < 3:
            await answer_message(bot, message, "Формат:\n/bind_supplier TELEGRAM_ID товар_или_ключ", business_connection_id)
            return True
        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True
        product_key = " ".join(parts[2:]).strip()
        async with SessionLocal() as session:
            result = await bind_supplier_to_product(session, supplier_id, product_key)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/unbind_supplier"):
        if len(parts) < 3:
            await answer_message(bot, message, "Формат:\n/unbind_supplier TELEGRAM_ID товар_или_ключ", business_connection_id)
            return True
        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True
        product_key = " ".join(parts[2:]).strip()
        async with SessionLocal() as session:
            result = await unbind_supplier_from_product(session, supplier_id, product_key)
        await answer_message(bot, message, result, business_connection_id)
        return True

    return False
