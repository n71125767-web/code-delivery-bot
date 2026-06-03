import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import ADMIN_IDS, SUPPLIER_IDS, SHOP_BOT_USERNAME
from app.models import Order
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
from app.utils import make_message_key, normalize_username, safe_send_message, notify_admins

logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def is_supplier(user_id: int) -> bool:
    return user_id in SUPPLIER_IDS

async def process_command_message(bot: Bot, message: Message, business_connection_id: str | None = None) -> bool:
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return False

    sender = message.from_user
    if not sender or getattr(sender, "is_bot", False):
        return True

    cmd = text.split()[0].split("@")[0].lower()

    if cmd == "/ping":
        await safe_send_message(bot, message.chat.id, "pong ✅", business_connection_id)
        return True
    if cmd == "/start":
        await safe_send_message(bot, message.chat.id,
            "Бот работает ✅\nДля покупателей: напишите товар/код.\nДля админа: /status, /last_orders",
            business_connection_id
        )
        return True
    # добавьте другие команды как /status, /last_orders, /debug_orders и /done аналогично
    return False

async def handle_buyer_message(bot: Bot, message: Message, business_connection_id: str | None = None):
    if getattr(message.from_user, "is_bot", False):
        return

    key = make_message_key("buyer", message.chat.id, message.message_id, message.text)
    async with message.bot["db"]() as session:
        if await is_message_processed(session, key):
            return
        await mark_message_processed(session, key, "buyer_message", message.text)

        user_id = message.from_user.id
        username = normalize_username(message.from_user.username)

        order = await find_active_paid_order_for_buyer(session, user_id, username, message.text)
        if not order:
            order = await find_waiting_service_order_by_id_or_username_today(session, user_id, username, message.text)

        if not order:
            await safe_send_message(bot, message.chat.id,
                "Не нашёл оплаченный заказ. Напишите номер заказа или username.",
                business_connection_id
            )
            await notify_admins(bot,
                f"Покупатель {username}/{user_id} написал, но заказ не найден: {message.text}"
            )
            return

        if order.status in ("waiting_supplier", "delivered", "completed", "error"):
            await safe_send_message(bot, message.chat.id,
                f"Статус заказа: {order.status}.",
                business_connection_id
            )
            return

        ok, err = await send_supplier_request(bot, session, order, message.text, business_connection_id)
        if not ok:
            await mark_order_error(session, order, err or "Не удалось отправить запрос поставщику")
            return

        await safe_send_message(bot, message.chat.id,
            "✅ Заказ найден. Передал запрос поставщику. Ожидайте.",
            business_connection_id
        )

async def handle_supplier_answer(bot: Bot, message: Message, business_connection_id: str | None = None):
    if getattr(message.from_user, "is_bot", False):
        return

    supplier_id = message.from_user.id
    key = make_message_key("supplier", message.chat.id, message.message_id, message.text)

    async with message.bot["db"]() as session:
        if await is_message_processed(session, key):
            return
        await mark_message_processed(session, key, "supplier_answer", message.text)

        request = await find_waiting_supplier_request(session, supplier_id)
        if not request:
            await safe_send_message(bot, message.chat.id,
                "Нет активного заказа для поставщика.",
                business_connection_id
            )
            return

        order = await get_order_by_id(session, request.order_id)
        if not order:
            return

        clean_answer = message.text.strip()
        if await is_delivered_text_used(session, clean_answer):
            await mark_order_error(session, order, "Дубликат товара/кода")
            return

        await mark_supplier_answered(session, order, request, clean_answer)
        ok, err = await safe_send_message(bot, order.customer_telegram_id, clean_answer)
        if ok:
            await mark_order_delivered(session, order)

def register_handlers(dp: Dispatcher, bot: Bot) -> None:
    """
    Важно:
    1. Обычные команды работают в личке с ботом.
    2. Business-команды работают в Business-чате.
    3. Исходящие сообщения твоего Business-аккаунта игнорируются, чтобы не было цикла.
    4. Сообщения от ботов игнорируются, кроме Admaker/shop-бота.
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
        sender_username = normalize_username(sender.username)
        shop_username = normalize_username(SHOP_BOT_USERNAME)

        logger.info(
            "Business message received: from_id=%s username=%s is_bot=%s text=%s",
            sender.id,
            sender_username,
            getattr(sender, "is_bot", False),
            text[:300],
        )

        # 1. Команды обрабатываем отдельно.
        # Это нужно, чтобы /status и /ping работали даже через Business.
        if text.strip().startswith("/"):
            await process_command_message(bot, message, business_connection_id)
            return

        # 2. Admaker/shop-бот НЕ игнорируем, даже если он bot.
        if sender_username and sender_username == shop_username:
            await process_admaker_message(bot, message)
            return

        # 3. Игнорируем любые сообщения от ботов.
        # Иначе бот может читать ответы других ботов и зациклиться.
        if getattr(sender, "is_bot", False):
            logger.info("Ignored business message from bot: %s", sender_username)
            return

        # 4. КРИТИЧНО: игнорируем исходящие сообщения владельца Business-аккаунта.
        # Обычно Telegram присылает исходящие сообщения как business_message от твоего аккаунта.
        # Если их не игнорировать, бот читает свои же отправленные сообщения и повторяет их.
        if sender.id in ADMIN_IDS:
            logger.info(
                "Ignored own outgoing business message from admin/business owner: %s",
                sender.id,
            )
            return

        # 5. Сообщение от поставщика.
        if is_supplier(sender.id):
            await handle_supplier_answer(bot, message, business_connection_id)
            return

        # 6. Сообщение от покупателя.
        await handle_buyer_message(bot, message, business_connection_id)

    @dp.message(F.text)
    async def normal_message_router(message: Message):
        sender = message.from_user
        text = message.text or ""

        if not sender:
            return

        logger.info(
            "Normal message received: from_id=%s username=%s is_bot=%s text=%s",
            sender.id,
            sender.username,
            getattr(sender, "is_bot", False),
            text[:300],
        )

        # 1. Игнорируем сообщения от ботов.
        if getattr(sender, "is_bot", False):
            logger.info("Ignored normal message from bot: %s", sender.username)
            return

        # 2. Команды.
        if text.strip().startswith("/"):
            await process_command_message(bot, message, None)
            return

        # 3. Поставщик.
        if is_supplier(sender.id):
            await handle_supplier_answer(bot, message, None)
            return

        # 4. Покупатель.
        await handle_buyer_message(bot, message, None)