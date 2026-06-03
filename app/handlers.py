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


async def get_status_text() -> str:
    async with SessionLocal() as session:
        total = await session.scalar(select(func.count(Order.id)))

        waiting_buyer = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_buyer_message")
        )
        waiting_supplier = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_supplier")
        )
        supplier_answered = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "supplier_answered")
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

        old_waiting_service = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_service")
        )
        old_waiting_number = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_supplier_number")
        )
        old_waiting_code = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_supplier_code")
        )

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


async def get_last_orders_text() -> str:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Order).order_by(Order.created_at.desc()).limit(10)
        )
        orders = result.scalars().all()

    if not orders:
        return "Заказов пока нет."

    text = "📦 Последние заказы:\n\n"

    for order in orders:
        text += (
            f"ID в базе: {order.id}\n"
            f"Заказ: #{order.operation_id}\n"
            f"Покупатель ID: {order.customer_telegram_id or 'нет'}\n"
            f"Username: @{order.customer_username or 'нет'}\n"
            f"Товар: {order.product_name or 'нет'}\n"
            f"Статус: {order.status}\n"
            f"Поставщик: {getattr(order, 'supplier_telegram_id', None) or 'нет'}\n"
            f"Ошибка: {getattr(order, 'last_error', None) or 'нет'}\n"
            "--------------------\n"
        )

    return text


async def get_debug_orders_text() -> str:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Order)
            .where(
                Order.status.in_(
                    [
                        "waiting_buyer_message",
                        "waiting_service",
                        "waiting_supplier",
                        "waiting_supplier_number",
                        "number_sent_to_customer",
                        "waiting_supplier_code",
                    ]
                )
            )
            .order_by(Order.created_at.desc())
            .limit(20)
        )
        orders = result.scalars().all()

    if not orders:
        return "Нет активных заказов."

    text = "🔍 Активные заказы:\n\n"

    for order in orders:
        text += (
            f"ID в базе: {order.id}\n"
            f"Заказ: #{order.operation_id}\n"
            f"Покупатель ID: {order.customer_telegram_id or 'нет'}\n"
            f"Username: @{order.customer_username or 'нет'}\n"
            f"Товар: {order.product_name or 'нет'}\n"
            f"Статус: {order.status}\n"
            f"Запрос покупателя: {getattr(order, 'buyer_message', None) or 'нет'}\n"
            "--------------------\n"
        )

    return text


async def set_customer_by_command(text: str) -> str:
    parts = text.split()

    if len(parts) != 3:
        return (
            "Формат команды:\n"
            "/set_customer ID_ЗАКАЗА TELEGRAM_ID\n\n"
            "Пример:\n"
            "/set_customer 5 92463179"
        )

    try:
        order_id = int(parts[1])
        customer_id = int(parts[2])
    except ValueError:
        return "ID заказа и Telegram ID должны быть числами."

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)

        if not order:
            return "Заказ не найден."

        order.customer_telegram_id = customer_id
        await session.commit()

        await log_order_action(
            session,
            order.id,
            "manual_set_customer",
            f"customer_telegram_id={customer_id}",
        )

    return f"✅ Заказ ID {order_id} привязан к покупателю {customer_id}"


async def answer_message(
    bot: Bot,
    message: Message,
    text: str,
    business_connection_id: str | None = None,
) -> None:
    ok, err = await safe_send_message(
        bot=bot,
        chat_id=message.chat.id,
        text=text,
        business_connection_id=business_connection_id,
    )

    if not ok:
        logger.error("Failed to answer message: %s", err)


async def process_command_message(
    bot: Bot,
    message: Message,
    business_connection_id: str | None = None,
) -> bool:
    text = (message.text or "").strip()

    if not text.startswith("/"):
        return False

    sender = message.from_user
    if not sender:
        return True

    cmd = text.split()[0].split("@")[0].lower()

    logger.info(
        "COMMAND: cmd=%s from_id=%s username=%s business_connection_id=%s",
        cmd,
        sender.id,
        sender.username,
        business_connection_id,
    )

    try:
        if cmd == "/start":
            await answer_message(
                bot,
                message,
                (
                    "Бот работает ✅\n\n"
                    "Покупатель пишет сюда товар/номер/код после оплаты.\n"
                    "Админ: /status, /last_orders, /debug_orders."
                ),
                business_connection_id,
            )
            return True

        if cmd == "/ping":
            await answer_message(bot, message, "pong ✅", business_connection_id)
            return True

        if cmd == "/done":
            async with SessionLocal() as session:
                order = await find_active_paid_order_for_buyer(
                    session=session,
                    telegram_id=sender.id,
                    username=sender.username,
                    user_message=None,
                )

                if not order:
                    await answer_message(bot, message, "Активный заказ не найден.", business_connection_id)
                    return True

                await mark_order_completed(session, order)

            await answer_message(bot, message, "✅ Заказ завершён.", business_connection_id)
            return True

        if not is_admin(sender.id):
            await answer_message(bot, message, "Команда доступна только админу.", business_connection_id)
            return True

        if cmd == "/status":
            await answer_message(bot, message, await get_status_text(), business_connection_id)
            return True

        if cmd == "/last_orders":
            await answer_message(bot, message, await get_last_orders_text(), business_connection_id)
            return True

        if cmd == "/debug_orders":
            await answer_message(bot, message, await get_debug_orders_text(), business_connection_id)
            return True

        if cmd == "/set_customer":
            await answer_message(bot, message, await set_customer_by_command(text), business_connection_id)
            return True

        if cmd == "/help":
            await answer_message(
                bot,
                message,
                (
                    "Команды:\n\n"
                    "/start — запуск\n"
                    "/ping — проверка\n"
                    "/done — завершить свой заказ\n\n"
                    "Админ:\n"
                    "/status — статус\n"
                    "/last_orders — последние заказы\n"
                    "/debug_orders — активные заказы\n"
                    "/set_customer ID_ЗАКАЗА TELEGRAM_ID — привязать покупателя"
                ),
                business_connection_id,
            )
            return True

        await answer_message(bot, message, "Неизвестная команда. Напишите /help", business_connection_id)
        return True

    except Exception as e:
        logger.exception("Command processing error")
        await answer_message(bot, message, f"Ошибка команды: {e}", business_connection_id)
        return True


async def process_admaker_message(bot: Bot, message: Message) -> None:
    sender = message.from_user
    text = message.text or ""

    sender_username = sender.username if sender else None
    chat_id = message.chat.id if message.chat else None
    message_id = message.message_id

    logger.info(
        "ADMAKER MESSAGE: from=%s chat_id=%s message_id=%s text=%s",
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
                "⚠️ Получил сообщение от shop-бота, но не смог распарсить оплату.\n\n"
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

    if not sender or not text:
        return

    user_id = sender.id
    username = normalize_username(sender.username)

    logger.info(
        "BUYER MESSAGE: user_id=%s username=%s business_connection_id=%s text=%s",
        user_id,
        username,
        business_connection_id,
        text[:500],
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

            await answer_message(
                bot,
                message,
                "Не нашёл оплаченный заказ. Напишите номер заказа или username, с которого была оплата.",
                business_connection_id,
            )

            await notify_admins(
                bot,
                "⚠️ Покупатель написал, но заказ не найден.\n\n"
                f"ID: {user_id}\n"
                f"Username: @{username or 'нет'}\n"
                f"Текст: {text}",
            )
            return

        if order.status in ("waiting_supplier", "waiting_supplier_number", "waiting_supplier_code"):
            await answer_message(
                bot,
                message,
                "Ваш заказ уже передан поставщику. Ожидайте выдачу товара/кода/номера.",
                business_connection_id,
            )
            return

        if order.status in ("delivered", "completed"):
            await answer_message(
                bot,
                message,
                "По этому заказу товар уже был выдан. Если всё успешно — напишите /done.",
                business_connection_id,
            )
            return

        if order.status == "error":
            await answer_message(
                bot,
                message,
                "По этому заказу возникла ошибка. Напишите админу.",
                business_connection_id,
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
            await answer_message(
                bot,
                message,
                "Ошибка: не удалось отправить запрос поставщику. Админ уже уведомлён.",
                business_connection_id,
            )
            await notify_admins(
                bot,
                "❌ Не удалось отправить запрос поставщику.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Ошибка: {err}",
            )
            return

    await answer_message(
        bot,
        message,
        "✅ Заказ найден. Передал запрос поставщику. Ожидайте товар/код/номер.",
        business_connection_id,
    )

    await notify_admins(
        bot,
        "📨 Покупатель найден, запрос поставщику отправлен.\n\n"
        f"Покупатель: @{username or 'нет'} / {user_id}\n"
        f"Запрос: {text}",
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
        business_connection_id=getattr(order, "customer_business_connection_id", None),
        text=product_text,
    )


async def handle_supplier_answer(
    bot: Bot,
    message: Message,
    business_connection_id: str | None = None,
) -> None:
    sender = message.from_user
    text = (message.text or "").strip()

    if not sender or not text:
        return

    supplier_id = sender.id

    logger.info(
        "SUPPLIER ANSWER: supplier_id=%s username=%s text=%s",
        supplier_id,
        sender.username,
        text[:500],
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
            await answer_message(
                bot,
                message,
                "Нет активного заказа, по которому я жду от вас товар/код/номер.",
                business_connection_id,
            )
            return

        order = await get_order_by_id(session, request.order_id)

        if not order:
            await answer_message(
                bot,
                message,
                "Ошибка: заказ для этого запроса не найден.",
                business_connection_id,
            )
            return

        clean_answer = extract_clean_product_answer(text)

        if await is_delivered_text_used(session, clean_answer):
            await mark_order_error(session, order, "Поставщик прислал товар/код/номер, который уже выдавался.")
            await answer_message(
                bot,
                message,
                "❌ Этот товар/код/номер уже выдавался раньше. Пришлите другой.",
                business_connection_id,
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
            await answer_message(
                bot,
                message,
                "Ответ принят, но не удалось отправить покупателю. Админ уведомлён.",
                business_connection_id,
            )
            await notify_admins(
                bot,
                "❌ Не удалось отправить товар покупателю.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Ошибка: {err}",
            )
            return

        await mark_order_delivered(session, order, clean_answer)

    await answer_message(
        bot,
        message,
        "✅ Ответ принят и отправлен покупателю.",
        business_connection_id,
    )

    await notify_admins(
        bot,
        "✅ Товар/код/номер выдан покупателю.\n\n"
        f"Поставщик: {supplier_id}",
    )


def register_handlers(dp: Dispatcher, bot: Bot) -> None:
    @dp.message(Command("start"))
    async def start_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.message(Command("ping"))
    async def ping_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.message(Command("done"))
    async def done_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.message(Command("status"))
    async def status_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.message(Command("last_orders"))
    async def last_orders_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.message(Command("debug_orders"))
    async def debug_orders_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.message(Command("set_customer"))
    async def set_customer_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.message(Command("help"))
    async def help_handler(message: Message):
        await process_command_message(bot, message, None)

    @dp.business_message(F.text)
    async def business_message_router(message: Message):
        sender = message.from_user
        text = message.text or ""

        business_connection_id = getattr(message, "business_connection_id", None)

        if not sender:
            logger.info("BUSINESS ignored: no sender")
            return

        sender_username = normalize_username(sender.username)
        shop_username = normalize_username(SHOP_BOT_USERNAME)

        logger.info(
            "BUSINESS ROUTER: from_id=%s username=%s is_bot=%s chat_id=%s text=%s",
            sender.id,
            sender_username,
            getattr(sender, "is_bot", False),
            message.chat.id if message.chat else None,
            text[:500],
        )

        if text.strip().startswith("/"):
            await process_command_message(bot, message, business_connection_id)
            return

        if sender_username and sender_username == shop_username:
            await process_admaker_message(bot, message)
            return

        if getattr(sender, "is_bot", False):
            logger.info("BUSINESS ignored bot: %s", sender_username)
            return

        if looks_like_own_bot_message(text):
            logger.info("BUSINESS ignored own/generated text: %s", text[:200])
            return

        if is_supplier(sender.id):
            logger.info("BUSINESS routed as supplier")
            await handle_supplier_answer(bot, message, business_connection_id)
            return

        logger.info("BUSINESS routed as buyer")
        await handle_buyer_message(bot, message, business_connection_id)

    @dp.message(F.text)
    async def normal_message_router(message: Message):
        sender = message.from_user
        text = message.text or ""

        if not sender:
            logger.info("NORMAL ignored: no sender")
            return

        logger.info(
            "NORMAL ROUTER: from_id=%s username=%s is_bot=%s chat_id=%s text=%s",
            sender.id,
            sender.username,
            getattr(sender, "is_bot", False),
            message.chat.id if message.chat else None,
            text[:500],
        )

        if text.strip().startswith("/"):
            await process_command_message(bot, message, None)
            return

        if getattr(sender, "is_bot", False):
            logger.info("NORMAL ignored bot: %s", sender.username)
            return

        if looks_like_own_bot_message(text):
            logger.info("NORMAL ignored own/generated text: %s", text[:200])
            return

        if is_supplier(sender.id):
            logger.info("NORMAL routed as supplier")
            await handle_supplier_answer(bot, message, None)
            return

        logger.info("NORMAL routed as buyer")
        await handle_buyer_message(bot, message, None)