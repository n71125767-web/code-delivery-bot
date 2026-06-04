import logging
from datetime import datetime

from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, Update

from app.config import (
    ADMIN_IDS,
    SUPPLIER_IDS,
    SHOP_BOT_USERNAME,
    IGNORE_OTHER_BOTS,
    ADMIN_BUSINESS_CONNECTION_ID,
)
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


def get_business_id(message: Message | None, fallback: str | None = None) -> str | None:
    if message is None:
        return fallback or ADMIN_BUSINESS_CONNECTION_ID
    return getattr(message, "business_connection_id", None) or fallback or ADMIN_BUSINESS_CONNECTION_ID


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text)


async def process_command_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    text = (message.text or "").strip()
    user_id = message.from_user.id
    username = message.from_user.username

    logger.info("COMMAND from_id=%s text=%s business_id=%s", user_id, text, business_connection_id)

    if text == "/start":
        async with SessionLocal() as session:
            order = await find_active_order_for_customer(session, user_id, username)

        if order and order.status == "waiting_service":
            await answer_message(
                bot,
                message,
                "Оплата получена.\n\nНапишите, для какого сервиса нужен номер.\nНапример: Telegram, WhatsApp, Google.",
                business_connection_id,
            )
            return

        await answer_message(bot, message, "Бот работает. Проверка: /ping", business_connection_id)
        return

    if text == "/ping":
        await answer_message(bot, message, "pong OK", business_connection_id)
        return

    if text == "/status":
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        async with SessionLocal() as session:
            status_text = await get_status_text(session)
        await answer_message(bot, message, status_text, business_connection_id)
        return

    if text == "/last_orders":
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        async with SessionLocal() as session:
            text = await get_last_orders_text(session)
        await answer_message(bot, message, text, business_connection_id)
        return

    if text.startswith("/set_customer"):
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        parts = text.split()
        if len(parts) != 3:
            await answer_message(bot, message, "Формат: /set_customer ID_ЗАКАЗА TELEGRAM_ID", business_connection_id)
            return
        try:
            order_id = int(parts[1])
            telegram_id = int(parts[2])
        except ValueError:
            await answer_message(bot, message, "ID должны быть числами.", business_connection_id)
            return
        async with SessionLocal() as session:
            result = await set_customer_by_order_id(session, order_id, telegram_id)
        await answer_message(bot, message, result, business_connection_id)
        return

    await answer_message(bot, message, "Неизвестная команда. Напишите /ping или /status", business_connection_id)


async def process_admaker_message(bot: Bot, message: Message) -> None:
    text = message.text or ""
    data = extract_purchase_data(text)

    if not data:
        await notify_admins(bot, f"Shop-бот прислал сообщение, но покупку распарсить не удалось.\n\nТекст:\n{text}")
        return

    async with SessionLocal() as session:
        order = await create_or_update_order_from_purchase(session, data)

    await notify_admins(bot, f"OK. Покупка обработана.\n\nЗаказ: #{order.operation_id}\nID в базе: {order.id}\nПокупатель ID: {order.customer_telegram_id}\nUsername: @{order.customer_username or 'нет'}\nТовар: {order.product_name}\nСтатус: {order.status}")


async def handle_buyer_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id
    username = message.from_user.username
    text = (message.text or "").strip()

    async with SessionLocal() as session:
        order = await find_waiting_service_order_for_customer(session, user_id, username)
        if not order:
            await answer_message(
                bot,
                message,
                "Заказ не найден.\nЕсли вы уже оплатили, напишите админу.",
                business_connection_id,
            )
            await notify_admins(bot, f"Покупатель написал, но заказ не найден.\nTelegram ID: {user_id}\nUsername: @{username or 'нет'}\nТекст: {text}")
            return
        order.service_name = text
        order.status = "waiting_supplier_number"
        order.buyer_chat_id = message.chat.id
        order.customer_telegram_id = user_id
        order.business_connection_id = business_connection_id
        order.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)

    supplier_id = SUPPLIER_IDS[0]
    supplier_text = f"Новый заказ.\n\nЗаказ: #{order.operation_id}\nID в базе: {order.id}\nТовар: {order.product_name}\nСервис: {order.service_name}\n\nПришлите номер для покупателя.\nПример: +79990000000"

    ok = await safe_send_message(bot, supplier_id, supplier_text, business_connection_id)
    if not ok:
        ok = await safe_send_message(bot, supplier_id, supplier_text)
    if not ok:
        await answer_message(bot, message, "Сервис принят, но не смог написать поставщику. Админ уведомлён.", business_connection_id)
        await notify_admins(bot, f"Не смог отправить заявку поставщику по заказу #{order.operation_id}")
        return
    async with SessionLocal() as session:
        await create_supplier_request(session, order.id, supplier_id, "number")
    await answer_message(bot, message, "OK. Сервис принят. Ожидайте номер.", business_connection_id)


async def handle_supplier_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return
    supplier_id = message.from_user.id
    text = message.text or ""

    async with SessionLocal() as session:
        number_request = await find_waiting_supplier_request(session, supplier_id, "number")
        if number_request:
            phone = extract_phone(text)
            if not phone:
                await answer_message(bot, message, "Не смог найти номер. Пример: +79990000000", business_connection_id)
                return
            order = await get_order_by_id(session, number_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
                return
            order.phone_number = phone
            order.status = "number_sent_to_customer"
            order.updated_at = datetime.utcnow()
            number_request.status = "answered"
            number_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id or business_connection_id
            ok = False
            if target_chat_id:
                ok = await safe_send_message(bot, target_chat_id, phone, business_connection_id=target_business_id, reply_markup=number_keyboard(order.id))
            if not ok:
                await answer_message(bot, message, "Номер принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(bot, f"Не смог отправить номер покупателю по заказу #{order.operation_id}")
                return
            await answer_message(bot, message, f"OK. Номер отправлен покупателю.\nЗаказ #{order.operation_id}", business_connection_id)
            return

        code_request = await find_waiting_supplier_request(session, supplier_id, "code")
        if code_request:
            code = extract_code(text)
            if not code:
                await answer_message(bot, message, "Не смог найти код. Пример: 123456", business_connection_id)
                return
            order = await get_order_by_id(session, code_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
                return
            order.verification_code = code
            order.status = "code_sent_to_customer"
            order.updated_at = datetime.utcnow()
            code_request.status = "answered"
            code_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id or business_connection_id
            ok = False
            if target_chat_id:
                ok = await safe_send_message(bot, target_chat_id, code, business_connection_id=target_business_id, reply_markup=confirm_keyboard(order.id))
            if not ok:
                await answer_message(bot, message, "Код принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(bot, f"Не смог отправить код покупателю по заказу #{order.operation_id}")
                return
            await answer_message(bot, message, f"OK. Код отправлен покупателю.\nЗаказ #{order.operation_id}", business_connection_id)
            return

    await answer_message(bot, message, "Нет активного запроса для вас.", business_connection_id)


async def route_message(bot: Bot, message: Message, is_business: bool) -> None:
    if not message.from_user:
        logger.info("MESSAGE WITHOUT from_user")
        return

    me = await bot.me()
    sender = message.from_user
    user_id = sender.id
    username = (sender.username or "").replace("@", "").lower()
    text = (message.text or "").strip()
    business_connection_id = get_business_id(message) if is_business else None

    logger.info("ROUTE_MESSAGE is_business=%s from_id=%s username=%s is_bot=%s chat_id=%s business_id=%s text=%s",
                is_business, user_id, username, sender.is_bot, message.chat.id, business_connection_id, text[:200])

    if user_id == me.id:
        logger.info("IGNORED: own bot message")
        return
    if is_admin(user_id) and not text.startswith("/"):
        logger.info("IGNORED: admin non-command message to avoid self-cycle")
        return
    if not text:
        logger.info("IGNORED: empty/non-text message")
        return
    if IGNORE_OTHER_BOTS and sender.is_bot and username != SHOP_BOT_USERNAME:
        logger.info("IGNORED: other bot username=%s", username)
        return

    if text.startswith("/"):
        await process_command_message(bot, message, business_connection_id)
        return
    if username == SHOP_BOT_USERNAME:
        await process_admaker_message(bot, message)
        return
    if is_supplier(user_id):
        await handle_supplier_message(bot, message, business_connection_id)
        return
    await handle_buyer_message(bot, message, business_connection_id)


async def handle_callback(bot: Bot, callback: CallbackQuery) -> None:
    data = callback.data or ""
    logger.info("CALLBACK from_id=%s data=%s", callback.from_user.id if callback.from_user else None, data)

    # Здесь можно добавить обработку callback_query точно так же, как в старом коде
    await callback.answer("Обработано (или добавь конкретную логику)")