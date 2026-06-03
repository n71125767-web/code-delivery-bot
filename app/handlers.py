import logging
from datetime import datetime

from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import ADMIN_IDS, SUPPLIER_IDS, SHOP_BOT_USERNAME, IGNORE_OTHER_BOTS
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
        await safe_send_message(bot, admin_id, text)


async def process_command_message(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    username = message.from_user.username
    text = (message.text or "").strip()

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

        await answer_message(
            bot,
            message,
            "Бот работает.\n\nЕсли вы оплатили заказ, напишите сюда название сервиса.",
            business_connection_id,
        )
        return

    if text == "/ping":
        await answer_message(bot, message, "pong OK", business_connection_id)
        return

    if text == "/help":
        await answer_message(
            bot,
            message,
            "Команды:\n"
            "/start - запуск\n"
            "/ping - проверка\n"
            "/status - статус, только админ\n"
            "/last_orders - последние заказы, только админ\n"
            "/set_customer ID_ЗАКАЗА TELEGRAM_ID - привязать покупателя, только админ",
            business_connection_id,
        )
        return

    if text == "/status":
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда доступна только админу.", business_connection_id)
            return
        async with SessionLocal() as session:
            status_text = await get_status_text(session)
        await answer_message(bot, message, status_text, business_connection_id)
        return

    if text == "/last_orders":
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда доступна только админу.", business_connection_id)
            return
        async with SessionLocal() as session:
            last_orders_text = await get_last_orders_text(session)
        await answer_message(bot, message, last_orders_text, business_connection_id)
        return

    if text.startswith("/set_customer"):
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда доступна только админу.", business_connection_id)
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
            result_text = await set_customer_by_order_id(session, order_id, telegram_id)

        await answer_message(bot, message, result_text, business_connection_id)
        return

    await answer_message(bot, message, "Неизвестная команда. Напишите /help", business_connection_id)


async def process_admaker_message(bot: Bot, message: Message) -> None:
    text = message.text or ""
    purchase_data = extract_purchase_data(text)

    if not purchase_data:
        await notify_admins(
            bot,
            "Не смог распарсить сообщение от shop-бота.\n\n"
            f"Текст:\n{text}",
        )
        return

    async with SessionLocal() as session:
        order = await create_or_update_order_from_purchase(session, purchase_data)

    await notify_admins(
        bot,
        "OK. Покупка обработана.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Покупатель ID: {order.customer_telegram_id}\n"
        f"Username: @{order.customer_username or 'нет'}\n"
        f"Товар: {order.product_name}\n"
        f"Статус: {order.status}",
    )

    if order.customer_telegram_id:
        ok = await safe_send_message(
            bot,
            order.customer_telegram_id,
            "Оплата получена.\n\nНапишите, для какого сервиса нужен номер.\nНапример: Telegram, WhatsApp, Google.",
        )
        if not ok:
            await notify_admins(
                bot,
                "Не смог написать покупателю в личку.\n"
                "Покупатель должен сначала нажать /start в боте или написать в Business-аккаунт.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"ID в базе: {order.id}\n"
                f"Покупатель ID: {order.customer_telegram_id}",
            )


async def handle_buyer_message(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    username = message.from_user.username
    text = (message.text or "").strip()

    # ВАЖНО: здесь НЕ используем message.bot["db"]().
    # В aiogram Bot не является словарём. Поэтому используем импортированный SessionLocal.
    async with SessionLocal() as session:
        order = await find_waiting_service_order_for_customer(session, user_id, username)

        if not order:
            await answer_message(
                bot,
                message,
                "Заказ не найден.\n\n"
                "Возможные причины:\n"
                "1. Оплата ещё не пришла в систему.\n"
                "2. В заказе другой Telegram ID или username.\n"
                "3. Вы пишете не с того аккаунта.\n\n"
                "Админ может проверить /last_orders и привязать заказ командой /set_customer.",
                business_connection_id,
            )

            await notify_admins(
                bot,
                "Покупатель написал, но заказ не найден.\n\n"
                f"Telegram ID: {user_id}\n"
                f"Username: @{username or 'нет'}\n"
                f"Текст: {text}\n\n"
                "Проверь /last_orders и при необходимости используй:\n"
                f"/set_customer ID_ЗАКАЗА {user_id}",
            )
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
    supplier_text = (
        "Новый заказ.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Товар: {order.product_name}\n"
        f"Сервис: {order.service_name}\n\n"
        "Пришлите номер для покупателя.\n"
        "Пример: +79990000000"
    )

    try:
        supplier_message = await bot.send_message(supplier_id, supplier_text)
        supplier_message_id = supplier_message.message_id
    except Exception as exc:
        logger.exception("Не смог отправить поставщику")
        supplier_message_id = None
        await answer_message(
            bot,
            message,
            "Сервис принят, но я не смог написать поставщику. Админ уже получит ошибку.",
            business_connection_id,
        )
        await notify_admins(bot, f"Ошибка отправки поставщику {supplier_id}: {exc}")
        return

    async with SessionLocal() as session:
        await create_supplier_request(
            session=session,
            order_id=order.id,
            supplier_telegram_id=supplier_id,
            request_type="number",
            supplier_message_id=supplier_message_id,
        )

    await answer_message(bot, message, "OK. Сервис принят. Ожидайте номер.", business_connection_id)

    await notify_admins(
        bot,
        "Запрос поставщику отправлен.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"Покупатель: @{order.customer_username or username or 'нет'} / {user_id}\n"
        f"Сервис: {order.service_name}",
    )


async def handle_supplier_message(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> None:
    if not message.from_user:
        return

    supplier_id = message.from_user.id
    text = message.text or ""

    async with SessionLocal() as session:
        number_request = await find_waiting_supplier_request(session, supplier_id, "number")

        if number_request:
            phone = extract_phone(text)
            if not phone:
                await answer_message(bot, message, "Не смог найти номер. Пришлите в формате +79990000000", business_connection_id)
                return

            order = await get_order_by_id(session, number_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ для этого запроса не найден.", business_connection_id)
                return

            order.phone_number = phone
            order.status = "number_sent_to_customer"
            order.updated_at = datetime.utcnow()
            number_request.status = "answered"
            number_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id

            if not target_chat_id:
                await answer_message(bot, message, "У заказа нет chat_id покупателя. Админ должен привязать покупателя.", business_connection_id)
                return

            ok = await safe_send_message(
                bot,
                target_chat_id,
                f"{phone}",
                business_connection_id=target_business_id,
                reply_markup=number_keyboard(order.id),
            )

            if not ok:
                order.status = "waiting_supplier_number"
                number_request.status = "sent"
                await session.commit()
                await answer_message(bot, message, "Номер принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(bot, f"Не смог отправить номер покупателю по заказу #{order.operation_id}.")
                return

            await answer_message(bot, message, f"OK. Номер принят и отправлен покупателю.\nЗаказ #{order.operation_id}\nНомер: {phone}", business_connection_id)
            await notify_admins(bot, f"Номер отправлен покупателю.\n\nЗаказ #{order.operation_id}\nНомер: {phone}")
            return

        code_request = await find_waiting_supplier_request(session, supplier_id, "code")

        if code_request:
            code = extract_code(text)
            if not code:
                await answer_message(bot, message, "Не смог найти код. Пришлите код, например: 123456", business_connection_id)
                return

            order = await get_order_by_id(session, code_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ для этого запроса не найден.", business_connection_id)
                return

            order.verification_code = code
            order.status = "code_sent_to_customer"
            order.updated_at = datetime.utcnow()
            code_request.status = "answered"
            code_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id

            if not target_chat_id:
                await answer_message(bot, message, "У заказа нет chat_id покупателя. Админ должен привязать покупателя.", business_connection_id)
                return

            ok = await safe_send_message(
                bot,
                target_chat_id,
                f"{code}",
                business_connection_id=target_business_id,
                reply_markup=confirm_keyboard(order.id),
            )

            if not ok:
                order.status = "waiting_supplier_code"
                code_request.status = "sent"
                await session.commit()
                await answer_message(bot, message, "Код принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(bot, f"Не смог отправить код покупателю по заказу #{order.operation_id}.")
                return

            await answer_message(bot, message, f"OK. Код принят и отправлен покупателю.\nЗаказ #{order.operation_id}\nКод: {code}", business_connection_id)
            await notify_admins(bot, f"Код отправлен покупателю.\n\nЗаказ #{order.operation_id}\nКод: {code}")
            return

    await answer_message(bot, message, "Нет активного запроса для вас. Сейчас бот не ждёт номер или код.", business_connection_id)


@router.business_message(F.text)
async def business_message_router(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return

    business_connection_id = getattr(message, "business_connection_id", None)
    text = message.text or ""
    sender = message.from_user
    username = (sender.username or "").replace("@", "").lower()

    logger.info(
        "BUSINESS ROUTER: from_id=%s username=%s is_bot=%s chat_id=%s text=%s",
        sender.id,
        username,
        sender.is_bot,
        message.chat.id,
        text[:200],
    )

    # Не обрабатываем свои ответы, чтобы не было цикла.
    if sender.is_bot and username != SHOP_BOT_USERNAME:
        logger.info("Ignored business message from bot: username=%s", username)
        return

    if text.startswith("/"):
        await process_command_message(bot, message, business_connection_id)
        return

    if username == SHOP_BOT_USERNAME:
        await process_admaker_message(bot, message)
        return

    if is_supplier(sender.id):
        await handle_supplier_message(bot, message, business_connection_id)
        return

    await handle_buyer_message(bot, message, business_connection_id)


@router.message(F.text)
async def normal_message_router(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return

    text = message.text or ""
    user_id = message.from_user.id

    if text.startswith("/"):
        await process_command_message(bot, message, None)
        return

    if IGNORE_OTHER_BOTS and message.from_user.is_bot:
        return

    if is_supplier(user_id):
        await handle_supplier_message(bot, message, None)
        return

    await handle_buyer_message(bot, message, None)


@router.callback_query(F.data.startswith("code_sent:"))
async def code_sent_callback(callback: CallbackQuery, bot: Bot):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        supplier_id = SUPPLIER_IDS[0]
        order.status = "waiting_supplier_code"
        order.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)

    await create_code_request_and_notify_supplier(bot, supplier_id, order)
    await callback.message.answer("OK. Запросил код у поставщика.")
    await callback.answer()


async def create_code_request_and_notify_supplier(bot: Bot, supplier_id: int, order) -> None:
    supplier_text = (
        "Нужен код.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Товар: {order.product_name}\n"
        f"Сервис: {order.service_name}\n"
        f"Номер: {order.phone_number}\n\n"
        "Пришлите код. Пример: 123456"
    )

    msg = await bot.send_message(supplier_id, supplier_text)

    async with SessionLocal() as session:
        await create_supplier_request(
            session=session,
            order_id=order.id,
            supplier_telegram_id=supplier_id,
            request_type="code",
            supplier_message_id=msg.message_id,
        )


@router.callback_query(F.data.startswith("confirm_success:"))
async def confirm_success_callback(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        order.status = "confirmed"
        order.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)

    await callback.message.answer("OK. Заказ завершён.")
    await callback.answer()


@router.callback_query(F.data.startswith("number_invalid:"))
async def number_invalid_callback(callback: CallbackQuery, bot: Bot):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        order.status = "problem"
        order.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)

    await callback.message.answer("Понял. Передал админу проблему с номером.")
    await callback.answer()
    await notify_admins(bot, f"Покупатель сообщил, что номер не работает.\n\nЗаказ #{order.operation_id}\nНомер: {order.phone_number}")


@router.callback_query(F.data.startswith("code_invalid:"))
async def code_invalid_callback(callback: CallbackQuery, bot: Bot):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        order.status = "problem"
        order.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)

    await callback.message.answer("Понял. Передал админу проблему с кодом.")
    await callback.answer()
    await notify_admins(bot, f"Покупатель сообщил, что код не работает.\n\nЗаказ #{order.operation_id}\nКод: {order.verification_code}")
