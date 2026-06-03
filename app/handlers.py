import logging
from datetime import datetime

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


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_supplier(user_id: int) -> bool:
    return user_id in SUPPLIER_IDS


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text)


async def process_admaker_message(bot: Bot, message: Message) -> None:
    sender = message.from_user
    text = message.text or ""

    sender_username = sender.username if sender else None
    chat_id = message.chat.id if message.chat else None
    message_id = message.message_id

    logger.info(
        "Admaker/business message received: from=%s chat_id=%s message_id=%s text=%s",
        sender_username,
        chat_id,
        message_id,
        text[:500],
    )

    key = make_message_key("admaker", chat_id, message_id, text)

    async with SessionLocal() as session:
        if await is_message_processed(session, key):
            logger.info("Duplicate Admaker message ignored: %s", key)
            return

        data = extract_purchase_data(text)

        if not data:
            await mark_message_processed(session, key, "admaker_unparsed", text)
            await notify_admins(
                bot,
                "⚠️ Получил сообщение от Admaker/shop-бота, но не смог распарсить оплату.\n\n"
                f"От: @{sender_username or 'нет'}\n\n"
                f"Текст:\n{text}",
            )
            return

        order = await create_or_update_order_from_admaker_message(session, data)
        await mark_message_processed(session, key, "admaker_paid_order", text)

    await notify_admins(
        bot,
        "✅ Оплата сохранена в базе.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Покупатель ID: {order.customer_telegram_id or 'нет'}\n"
        f"Username: @{order.customer_username or 'нет'}\n"
        f"Товар: {order.product_name}\n"
        f"Статус: {order.status}",
    )


async def handle_buyer_message(
    bot: Bot,
    message: Message,
    business_connection_id: str | None = None,
) -> None:
    sender = message.from_user
    text = (message.text or "").strip()

    if not sender:
        return

    user_id = sender.id
    username = normalize_username(sender.username)

    logger.info(
        "Buyer message: user_id=%s username=%s business_connection_id=%s text=%s",
        user_id,
        username,
        business_connection_id,
        text,
    )

    key = make_message_key("buyer", message.chat.id, message.message_id, text)

    async with SessionLocal() as session:
        if await is_message_processed(session, key):
            logger.info("Duplicate buyer message ignored: %s", key)
            return

        await mark_message_processed(session, key, "buyer_message", text)

        order = await find_active_paid_order_for_buyer(
            session=session,
            telegram_id=user_id,
            username=username,
            user_message=text,
        )

        if not order:
            order = await find_waiting_service_order_by_id_or_username_today(
                session=session,
                telegram_id=user_id,
                username=username,
                user_message=text,
            )

        if not order:
            await log_order_action(
                session,
                None,
                "buyer_order_not_found",
                f"user_id={user_id}, username={username}, text={text}",
            )

            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Не нашёл оплаченный заказ. Напишите номер заказа или username, с которого была оплата.",
            )

            await notify_admins(
                bot,
                "⚠️ Покупатель написал, но оплаченный заказ не найден.\n\n"
                f"ID: {user_id}\n"
                f"Username: @{username or 'нет'}\n"
                f"Текст: {text}",
            )
            return

        if order.status == "waiting_supplier":
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Ваш заказ уже передан поставщику. Ожидайте выдачу товара/кода/номера.",
            )
            return

        if order.status == "delivered":
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Товар уже был выдан. Если всё хорошо — напишите /done. Если проблема — напишите админу.",
            )
            return

        if order.status == "completed":
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Этот заказ уже завершён.",
            )
            return

        if order.status == "error":
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="По этому заказу возникла ошибка. Напишите админу.",
            )
            return

        ok, err = await send_supplier_request(
            bot=bot,
            session=session,
            order=order,
            buyer_message=text,
            buyer_business_connection_id=business_connection_id,
        )

        if not ok:
            await mark_order_error(session, order, err or "Не удалось отправить запрос поставщику")
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Ошибка: не удалось отправить запрос поставщику. Админ уже уведомлён.",
            )
            await notify_admins(
                bot,
                "❌ Не удалось отправить запрос поставщику.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Ошибка: {err}",
            )
            return

    await safe_send_message(
        bot=bot,
        chat_id=message.chat.id,
        business_connection_id=business_connection_id,
        text="✅ Заказ найден. Передал запрос поставщику. Ожидайте товар/код/номер.",
    )

    await notify_admins(
        bot,
        "📨 Покупатель найден, запрос поставщику отправлен.\n\n"
        f"Покупатель: @{username or 'нет'} / {user_id}\n"
        f"Запрос: {text}",
    )


async def handle_supplier_answer(
    bot: Bot,
    message: Message,
    business_connection_id: str | None = None,
) -> None:
    sender = message.from_user
    text = (message.text or "").strip()

    if not sender:
        return

    supplier_id = sender.id

    logger.info(
        "Supplier answer: supplier_id=%s username=%s text=%s",
        supplier_id,
        sender.username,
        text,
    )

    key = make_message_key("supplier", message.chat.id, message.message_id, text)

    async with SessionLocal() as session:
        if await is_message_processed(session, key):
            logger.info("Duplicate supplier message ignored: %s", key)
            return

        await mark_message_processed(session, key, "supplier_answer", text)

        request = await find_waiting_supplier_request(
            session=session,
            supplier_telegram_id=supplier_id,
            request_type="product",
        )

        if not request:
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Нет активного заказа, по которому я жду от вас товар/код/номер.",
            )
            return

        order = await get_order_by_id(session, request.order_id)

        if not order:
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Ошибка: заказ для этого запроса не найден.",
            )
            return

        clean_answer = extract_clean_product_answer(text)

        if await is_delivered_text_used(session, clean_answer):
            await mark_order_error(session, order, "Поставщик прислал товар/код/номер, который уже выдавался.")
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="❌ Этот товар/код/номер уже выдавался раньше. Пришлите другой.",
            )
            await notify_admins(
                bot,
                "❌ Защита от дубля сработала.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Ответ поставщика: {clean_answer}",
            )
            return

        await mark_supplier_answered(session, order, request, clean_answer)

        ok, err = await deliver_product_to_buyer(
            bot=bot,
            session=session,
            order=order,
            product_text=clean_answer,
        )

        if not ok:
            await mark_order_error(session, order, err or "Не удалось отправить товар покупателю")
            await safe_send_message(
                bot=bot,
                chat_id=message.chat.id,
                business_connection_id=business_connection_id,
                text="Ответ принят, но не удалось отправить покупателю. Админ уведомлён.",
            )
            await notify_admins(
                bot,
                "❌ Не удалось отправить товар покупателю.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Ошибка: {err}",
            )
            return

        await mark_order_delivered(session, order, clean_answer)

    await safe_send_message(
        bot=bot,
        chat_id=message.chat.id,
        business_connection_id=business_connection_id,
        text="✅ Ответ принят и отправлен покупателю.",
    )

    await notify_admins(
        bot,
        "✅ Товар/код/номер выдан покупателю.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"Поставщик: {supplier_id}",
    )


async def deliver_product_to_buyer(
    bot: Bot,
    session,
    order: Order,
    product_text: str,
) -> tuple[bool, str | None]:
    if not order.customer_telegram_id:
        return False, "У заказа нет Telegram ID покупателя."

    return await safe_send_message(
        bot=bot,
        chat_id=order.customer_telegram_id,
        business_connection_id=order.customer_business_connection_id,
        text=product_text,
    )


def register_handlers(dp: Dispatcher, bot: Bot) -> None:
    @dp.message(Command("start"))
    async def start_handler(message: Message):
        await message.answer("Бот работает ✅\n\nЕсли вы оплатили заказ, напишите сюда ваш запрос.")

    @dp.message(Command("done"))
    async def done_handler(message: Message):
        sender = message.from_user
        if not sender:
            return

        async with SessionLocal() as session:
            order = await find_active_paid_order_for_buyer(
                session=session,
                telegram_id=sender.id,
                username=sender.username,
                user_message=None,
            )

            if not order:
                await message.answer("Активный заказ не найден.")
                return

            await mark_order_completed(session, order)

        await message.answer("✅ Заказ завершён.")

    @dp.message(Command("status"))
    async def status_handler(message: Message):
        if not message.from_user or not is_admin(message.from_user.id):
            return

        async with SessionLocal() as session:
            total = await session.scalar(select(func.count(Order.id)))
            waiting_buyer = await session.scalar(
                select(func.count(Order.id)).where(Order.status == "waiting_buyer_message")
            )
            waiting_supplier = await session.scalar(
                select(func.count(Order.id)).where(Order.status == "waiting_supplier")
            )
            delivered = await session.scalar(
                select(func.count(Order.id)).where(Order.status == "delivered")
            )
            completed = await session.scalar(
                select(func.count(Order.id)).where(Order.status == "completed")
            )
            error = await session.scalar(
                select(func.count(Order.id)).where(Order.status == "error")
            )

        await message.answer(
            "📊 Статус\n\n"
            f"Всего заказов: {total or 0}\n"
            f"Ждут покупателя: {waiting_buyer or 0}\n"
            f"Ждут поставщика: {waiting_supplier or 0}\n"
            f"Выданы: {delivered or 0}\n"
            f"Завершены: {completed or 0}\n"
            f"Ошибки: {error or 0}"
        )

    @dp.message(Command("last_orders"))
    async def last_orders_handler(message: Message):
        if not message.from_user or not is_admin(message.from_user.id):
            return

        async with SessionLocal() as session:
            result = await session.execute(
                select(Order).order_by(Order.created_at.desc()).limit(10)
            )
            orders = result.scalars().all()

        if not orders:
            await message.answer("Заказов нет.")
            return

        text = "📦 Последние заказы:\n\n"

        for order in orders:
            text += (
                f"ID в базе: {order.id}\n"
                f"Заказ: #{order.operation_id}\n"
                f"Покупатель: @{order.customer_username or 'нет'} / {order.customer_telegram_id or 'нет'}\n"
                f"Товар: {order.product_name}\n"
                f"Статус: {order.status}\n"
                f"Ошибка: {order.last_error or 'нет'}\n"
                "--------------------\n"
            )

        await message.answer(text)

    @dp.business_message(F.text)
    async def business_message_router(message: Message):
        sender = message.from_user
        text = message.text or ""

        if not sender:
            return

        sender_username = normalize_username(sender.username)
        business_connection_id = getattr(message, "business_connection_id", None)

        if sender_username and sender_username == normalize_username(SHOP_BOT_USERNAME):
            await process_admaker_message(bot, message)
            return

        if is_supplier(sender.id):
            await handle_supplier_answer(bot, message, business_connection_id)
            return

        await handle_buyer_message(bot, message, business_connection_id)

    @dp.message(F.text)
    async def normal_message_router(message: Message):
        sender = message.from_user
        if not sender:
            return

        if message.text and message.text.startswith("/"):
            return

        if is_supplier(sender.id):
            await handle_supplier_answer(bot, message, None)
            return

        await handle_buyer_message(bot, message, None)