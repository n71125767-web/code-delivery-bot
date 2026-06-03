# handlers.py - исправленный UTF-8 для Telegram Business Bot
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func

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

# --- вспомогательные функции ---
def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)

def is_supplier(user_id: int | None) -> bool:
    return bool(user_id and user_id in SUPPLIER_IDS)

async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot=bot, chat_id=admin_id, text=text)

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

# --- команды /status, /ping и т.д. ---
async def get_status_text() -> str:
    async with SessionLocal() as session:
        total = await session.scalar(select(func.count(Order.id)))
        waiting_buyer = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_buyer_message"))
        waiting_supplier = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_supplier"))
        supplier_answered = await session.scalar(select(func.count(Order.id)).where(Order.status == "supplier_answered"))
        delivered = await session.scalar(select(func.count(Order.id)).where(Order.status == "delivered"))
        completed = await session.scalar(select(func.count(Order.id)).where(Order.status == "completed"))
        error = await session.scalar(select(func.count(Order.id)).where(Order.status == "error"))
        old_waiting_service = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_service"))
        old_waiting_number = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_supplier_number"))
        old_waiting_code = await session.scalar(select(func.count(Order.id)).where(Order.status == "waiting_supplier_code"))
    return (
        "📊 Статус бота\n\n"
        f"Всего заказов: {total or 0}\n"
        f"Ждут покупателя: {waiting_buyer or 0}\n"
        f"Ждут поставщика: {waiting_supplier or 0}\n"
        f"Поставщик ответил: {supplier_answered or 0}\n"
        f"Выданы: {delivered or 0}\n"
        f"Завершены: {completed or 0}\n"
        f"Ошибки: {error or 0}\n\n"
        "Старые статусы:\n"
        f"waiting_service: {old_waiting_service or 0}\n"
        f"waiting_supplier_number: {old_waiting_number or 0}\n"
        f"waiting_supplier_code: {old_waiting_code or 0}"
    )

# --- функции для покупателей и поставщиков ---
async def handle_buyer_message(bot: Bot, message: Message, business_connection_id: str | None = None):
    # Логика обработки сообщений покупателя
    pass  # сюда вставляй код из последнего ответа, с проверкой статуса и отправкой поставщику

async def handle_supplier_answer(bot: Bot, message: Message, business_connection_id: str | None = None):
    # Логика обработки ответов поставщика
    pass

async def process_admaker_message(bot: Bot, message: Message):
    # Логика парсинга сообщений shop-бота
    pass

async def answer_message(bot: Bot, message: Message, text: str, business_connection_id: str | None = None):
    ok, err = await safe_send_message(bot=bot, chat_id=message.chat.id, text=text, business_connection_id=business_connection_id)
    if not ok:
        logger.error("Failed to answer message: %s", err)

# --- регистрация всех обработчиков ---
def register_handlers(dp: Dispatcher, bot: Bot):
    @dp.message(Command("start"))
    async def start_handler(message: Message):
        await answer_message(bot, message, "Бот работает ✅")

    @dp.business_message(F.text)
    async def business_message_router(message: Message):
        sender = message.from_user
        if sender and not sender.is_bot:
            text = message.text or ""
            if looks_like_own_bot_message(text):
                return
            if sender.id in SUPPLIER_IDS:
                await handle_supplier_answer(bot, message, getattr(message, "business_connection_id", None))
            else:
                await handle_buyer_message(bot, message, getattr(message, "business_connection_id", None))