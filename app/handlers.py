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


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_supplier(user_id: int) -> bool:
    return user_id in SUPPLIER_IDS


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text)


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

        # поддержка старых статусов, если они остались в базе
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
            f"Поставщик: {order.supplier_telegram_id or 'нет'}\n"
            f"Ошибка: {order.last_error or 'нет'}\n"
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
            f"Запрос покупателя: {order.buyer_message or 'нет'}\n"
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


async def process_command_message(
    bot: Bot,
    message: Message,
    business_connection_id: str | None = None,
) -> bool:
    """
    Обрабатывает команды и в обычном чате с ботом, и через Telegram Business.
    Возвращает True, если сообщение было командой.
    """

    text = (message.text or "").strip()

    if not text.startswith("/"):
        return False

    sender = message.from_user
    if not sender:
        return True

    cmd = text.split()[0].split("@")[0].lower()

    logger.info(
        "Command received: cmd=%s from_id=%s username=%s business_connection_id=%s",
        cmd,
        sender.id,
        sender.username,
        business_connection_id,
    )

    if cmd == "/start":
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text=(
                "Бот работает ✅\n\n"
                "Если вы покупатель — напишите, какой товар/номер/код вам нужен.\n"
                "Если вы админ — используйте /status, /last_orders, /debug_orders."
            ),
        )
        return True

    if cmd == "/ping":
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text="pong ✅",
        )
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
                await safe_send_message(
                    bot=bot,
                    chat_id=message.chat.id,
                    business_connection_id=business_connection_id,
                    text="Активный заказ не найден.",
                )
                return True

            await mark_order_completed(session, order)

        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text="✅ Заказ завершён.",
        )
        return True

    # дальше только админские команды
    if not is_admin(sender.id):
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text="Команда доступна только админу.",
        )
        return True

    if cmd == "/status":
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text=await get_status_text(),
        )
        return True

    if cmd == "/last_orders":
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text=await get_last_orders_text(),
        )
        return True

    if cmd == "/debug_orders":
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text=await get_debug_orders_text(),
        )
        return True

    if cmd == "/set_customer":
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text=await set_customer_by_command(text),
        )
        return True

    if cmd == "/help":
        await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            business_connection_id=business_connection_id,
            text=(
                "Команды:\n\n"
                "/start — запуск\n"
                "/ping — проверка ответа\n"
                "/done — завершить свой заказ\n\n"
                "Админ:\n"
                "/status — статус бота\n"
                "/last_orders — последние заказы\n"
                "/debug_orders — активные заказы\n"
                "/set_customer ID_ЗАКАЗА TELEGRAM_ID — привязать покупателя"
            ),
        )
        return True

    await safe_send_message(
        bot=bot,
        chat_id=message.chat.id,
        business_connection_id=business_connection_id,
        text="Неизвестная команда. Напишите /help",
    )
    return True


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
    """
    ВАЖНО:
    Команды обрабатываются и через обычные message, и через business_message.
    Поэтому /start, /status, /last_orders будут работать даже если ты пишешь в Business-аккаунт.
    """

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

        if not sender:
            return

        business_connection_id = getattr(message, "business_connection_id", None)

        # 1. Сначала команды внутри Business
        if text.strip().startswith("/"):
            await process_command_message(bot, message, business_connection_id)
            return

        sender_username = normalize_username(sender.username)

        # 2. Сообщение от Admaker/shop-бота
        if sender_username and sender_username == normalize_username(SHOP_BOT_USERNAME):
            await process_admaker_message(bot, message)
            return

        # 3. Сообщение от поставщика
        if is_supplier(sender.id):
            await handle_supplier_answer(bot, message, business_connection_id)
            return

        # 4. Сообщение от покупателя
        await handle_buyer_message(bot, message, business_connection_id)

    @dp.message(F.text)
    async def normal_message_router(message: Message):
        sender = message.from_user
        text = message.text or ""

        if not sender:
            return

        # команды уже обработаны выше
        if text.strip().startswith("/"):
            await process_command_message(bot, message, None)
            return

        if is_supplier(sender.id):
            await handle_supplier_answer(bot, message, None)
            return

        await handle_buyer_message(bot, message, None)