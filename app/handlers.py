import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import ADMIN_IDS, SUPPLIER_IDS, SHOP_BOT_USERNAME
from app.database import SessionLocal
from app.models import Order
from app.parsers import extract_purchase_data, extract_clean_product_answer
from app.services import (
    create_or_update_order_from_admaker_message,
    find_active_paid_order_for_buyer,
    find_waiting_service_order_by_id_or_username_today,
    find_waiting_supplier_request,
    get_order_by_id,
    is_delivered_text_used,
    is_message_processed,
    mark_message_processed,
    mark_order_delivered,
    mark_order_error,
    mark_supplier_answered,
    mark_order_completed,
    log_order_action,
)
from app.suppliers import send_supplier_request
from app.utils import make_message_key, normalize_username, safe_send_message

logger = logging.getLogger(__name__)


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def is_supplier(user_id: int | None) -> bool:
    return bool(user_id and user_id in SUPPLIER_IDS)


def looks_like_own_bot_message(text: str) -> bool:
    clean = (text or "").strip().lower()
    own_starts = [
        "новый заказ:",
        "✅ заказ найден",
        "заказ найден",
        "передал запрос поставщику",
        "пожалуйста, выдайте товар",
        "📨 покупатель найден",
        "✅ оплата сохранена",
        "⚠️ покупатель написал",
        "❌ не удалось",
        "✅ ответ принят",
        "нет активного заказа",
        "не нашёл оплаченный заказ",
        "бот работает",
        "📊 статус бота",
        "📦 последние заказы",
        "🔍 активные заказы",
        "pong",
        "команда доступна только админу",
        "неизвестная команда",
    ]
    return any(clean.startswith(x) for x in own_starts)


async def answer_message(bot: Bot, message: Message, text: str, business_connection_id: str | None = None):
    ok, err = await safe_send_message(
        bot=bot, chat_id=message.chat.id, text=text, business_connection_id=business_connection_id
    )
    if not ok:
        logger.error("Failed to answer message: %s", err)


def register_handlers(dp: Dispatcher, bot: Bot):
    @dp.message(Command("start"))
    async def start_handler(message: Message):
        await answer_message(bot, message, "Бот работает ✅")

    @dp.message(Command("ping"))
    async def ping_handler(message: Message):
        await answer_message(bot, message, "pong OK")

    @dp.message(Command("status"))
    async def status_handler(message: Message):
        from app.handlers import get_status_text
        await answer_message(bot, message, await get_status_text())

    @dp.message(Command("last_orders"))
    async def last_orders_handler(message: Message):
        from app.handlers import get_last_orders_text
        await answer_message(bot, message, await get_last_orders_text())

    @dp.business_message(F.text)
    async def business_router(message: Message):
        sender = message.from_user
        if not sender or sender.is_bot:
            return

        text = message.text or ""
        business_connection_id = getattr(message, "business_connection_id", None)
        sender_username = normalize_username(sender.username)
        shop_username = normalize_username(SHOP_BOT_USERNAME)

        # Игнор своих сообщений
        if looks_like_own_bot_message(text):
            return

        # Команды
        if text.startswith("/"):
            from app.handlers import process_command_message
            await process_command_message(bot, message, business_connection_id)
            return

        # Сообщение от Shop-бота
        if sender_username == shop_username:
            from app.handlers import process_admaker_message
            await process_admaker_message(bot, message)
            return

        # Поставщик
        if is_supplier(sender.id):
            from app.handlers import handle_supplier_answer
            await handle_supplier_answer(bot, message, business_connection_id)
            return

        # Покупатель
        from app.handlers import handle_buyer_message
        await handle_buyer_message(bot, message, business_connection_id)
