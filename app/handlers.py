import logging
from datetime import datetime
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import ADMIN_IDS, SUPPLIER_IDS, SHOP_BOT_USERNAME, IGNORE_OTHER_BOTS, ADMIN_BUSINESS_CONNECTION_ID
from app.database import SessionLocal
from app.keyboards import confirm_keyboard, number_keyboard
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
)

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def is_supplier(user_id: int | None) -> bool:
    return bool(user_id and user_id in SUPPLIER_IDS)


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text, business_connection_id=ADMIN_BUSINESS_CONNECTION_ID)


# пример исправленного handle_buyer_message
async def handle_buyer_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    # не пишем себе
    if message.from_user.id == bot.id:
        logger.info("Покупатель — это сам бот, пропускаем")
        return

    user_id = message.from_user.id
    username = message.from_user.username
    text = (message.text or "").strip()

    async with SessionLocal() as session:
        order = await find_waiting_service_order_for_customer(session, user_id, username)
        if not order:
            await answer_message(bot, message, "Заказ не найден", business_connection_id=ADMIN_BUSINESS_CONNECTION_ID)
            await notify_admins(bot, f"Покупатель написал, но заказ не найден. Telegram ID: {user_id}, Username: @{username}")
            return

        order.service_name = text
        order.status = "waiting_supplier_number"
        order.buyer_chat_id = message.chat.id
        order.customer_telegram_id = user_id
        order.business_connection_id = ADMIN_BUSINESS_CONNECTION_ID
        order.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)

    supplier_id = SUPPLIER_IDS[0]
    supplier_text = (
        f"Новый заказ #{order.operation_id}\nТовар: {order.product_name}\nСервис: {order.service_name}\nПришлите номер для покупателя"
    )
    await safe_send_message(bot, supplier_id, supplier_text, business_connection_id=ADMIN_BUSINESS_CONNECTION_ID)
    await answer_message(bot, message, "OK. Сервис принят. Ожидайте номер.", business_connection_id=ADMIN_BUSINESS_CONNECTION_ID)
