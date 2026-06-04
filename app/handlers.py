import asyncio
import logging
import re
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message, CallbackQuery

from app.config import (
    ADMIN_IDS,
    AUTO_DELETE_MESSAGES,
    AUTO_DELETE_DELAY_SECONDS,
    AUTO_DELETE_UNKNOWN_BUYERS,
    IGNORE_NON_BUYERS,
    NOTIFY_UNKNOWN_BUYERS,
    ADMIN_ALERT_CHAT_ID,
    SHOP_BOT_USERNAME,
    IGNORE_OTHER_BOTS,
    ADMIN_BUSINESS_CONNECTION_ID,
    SERVICE_PAGE_SIZE,
    SUPPLIER_PAGE_SIZE,
    PROBLEM_COOLDOWN_SECONDS,
    BUTTON_COOLDOWN_SECONDS,
    BUYER_ORDERS_LIMIT,
)
from app.database import SessionLocal
from app.keyboards import (
    confirm_keyboard,
    number_keyboard,
    service_keyboard,
    service_keyboard_from_services,
    service_confirm_keyboard,
    admin_panel_keyboard,
    supplier_panel_keyboard,
    supplier_request_actions_keyboard,
    supplier_reply_keyboard,
    supplier_orders_keyboard,
    supplier_commands_keyboard,
    supplier_filter_keyboard,
    buyer_reply_keyboard,
    buyer_inline_menu_keyboard,
    supplier_inline_menu_keyboard,
    supplier_new_order_keyboard,
    buyer_back_keyboard,
    buyer_active_order_keyboard,
    supplier_requests_menu_keyboard,
    admin_text_keys_keyboard,
    admin_back_keyboard,
    admin_suppliers_keyboard,
    admin_services_keyboard,
    admin_lists_keyboard,
    admin_texts_menu_keyboard,
    admin_settings_keyboard,
    admin_profile_keyboard,
    admin_order_card_keyboard,
    admin_orders_keyboard,
)
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
    add_service,
    remove_service,
    set_service_emoji,
    get_services_page,
    find_service_by_slug,
    find_service_by_text,
    increment_service_usage,
    services_text,
    get_text,
    set_text,
    texts_text,
    check_cooldown,
    supplier_pending_text,
    get_supplier_pending_rows,
    set_supplier_request_message_id,
    create_action_event,
    admin_stats_text,
    admin_profile_text,
    supplier_profile_text,
    buyer_profile_text,
    supplier_filter_text,
    supplier_rows_by_filter,
    buyer_orders_text,
    select_supplier_request,
    find_selected_supplier_request,
    add_service_list,
    add_service_to_list,
    lists_text,
    admin_create_supplier_request_for_order,
    find_active_supplier_request,
    mark_supplier_request_in_progress,
    get_supplier_request_order,
    set_order_status,
    order_card_text,
    get_recent_order_rows,
    get_problem_order_rows,
)

logger = logging.getLogger(__name__)
logger.info("FIX_MARKER_ROLE_MENUS_DYNAMIC=v6 loaded")

ADMIN_TEXT_EDIT_WAIT: dict[int, str] = {}

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

    return (
        getattr(message, "business_connection_id", None)
        or fallback
        or ADMIN_BUSINESS_CONNECTION_ID
    )


def contains_forbidden_contact(text: str) -> bool:
    return bool(CONTACT_RE.search(text or ""))


def admin_panel_text() -> str:
    return (
        "Админ-панель\n\n"
        "Выберите раздел:"
    )


async def update_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    """
    Пытается обновить старое сообщение с кнопками.
    Если Telegram не разрешает edit_text — отправляет новое сообщение.
    В логах видно, была ли клавиатура и какой callback её вызвал.
    """
    has_keyboard = reply_markup is not None
    data = callback.data or ""

    if not callback.message:
        logger.warning("UPDATE_OR_SEND_NO_MESSAGE data=%s has_keyboard=%s", data, has_keyboard)
        return

    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        logger.info(
            "UPDATE_OR_SEND_EDIT_OK chat_id=%s message_id=%s data=%s has_keyboard=%s",
            callback.message.chat.id,
            callback.message.message_id,
            data,
            has_keyboard,
        )
    except Exception as exc:
        logger.info(
            "UPDATE_OR_SEND_EDIT_FAILED_SEND_NEW chat_id=%s message_id=%s data=%s has_keyboard=%s error=%s",
            callback.message.chat.id,
            callback.message.message_id,
            data,
            has_keyboard,
            exc,
        )
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
            logger.info(
                "UPDATE_OR_SEND_NEW_OK chat_id=%s data=%s has_keyboard=%s",
                callback.message.chat.id,
                data,
                has_keyboard,
            )
        except Exception as send_exc:
            logger.exception(
                "UPDATE_OR_SEND_NEW_FAILED chat_id=%s data=%s has_keyboard=%s error=%s",
                callback.message.chat.id,
                data,
                has_keyboard,
                send_exc,
            )


async def delete_later(bot: Bot, chat_id: int, message_id: int, delay: int | None = None) -> None:
    if not AUTO_DELETE_MESSAGES:
        return

    if delay is None:
        delay = AUTO_DELETE_DELAY_SECONDS

    await asyncio.sleep(delay)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info("AUTO_DELETE_OK chat_id=%s message_id=%s", chat_id, message_id)
    except Exception as exc:
        error_text = str(exc)
        # Это обычная ситуация для Telegram Business: сообщение уже удалено,
        # недоступно для удаления или Telegram не разрешил его удалить.
        # Не считаем это ошибкой, чтобы логи не засорялись WARNING.
        if "message to delete not found" in error_text.lower():
            logger.info("AUTO_DELETE_SKIPPED_NOT_FOUND chat_id=%s message_id=%s", chat_id, message_id)
            return
        logger.warning("AUTO_DELETE_FAILED chat_id=%s message_id=%s error=%s", chat_id, message_id, exc)


async def maybe_delete_message(bot: Bot, message: Message, delay: int | None = None) -> None:
    if not AUTO_DELETE_MESSAGES:
        return

    try:
        asyncio.create_task(delete_later(bot, message.chat.id, message.message_id, delay))
    except Exception:
        logger.exception("Failed to schedule incoming delete")


async def maybe_delete_sent(bot: Bot, sent_message, delay: int | None = None) -> None:
    if not AUTO_DELETE_MESSAGES:
        return

    if not sent_message or not hasattr(sent_message, "chat") or not hasattr(sent_message, "message_id"):
        return

    # ВАЖНО: сообщения с inline-кнопками не удаляем автоматически,
    # иначе покупатель/поставщик может не успеть увидеть кнопки.
    if getattr(sent_message, "reply_markup", None):
        logger.info(
            "AUTO_DELETE_SKIP_BUTTON_MESSAGE chat_id=%s message_id=%s",
            sent_message.chat.id,
            sent_message.message_id,
        )
        return

    try:
        asyncio.create_task(delete_later(bot, sent_message.chat.id, sent_message.message_id, delay))
    except Exception:
        logger.exception("Failed to schedule outgoing delete")


async def temp_answer(
    bot: Bot,
    message: Message,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
    delay: int | None = None,
) -> None:
    sent = await answer_message(bot, message, text, business_connection_id, reply_markup=reply_markup)
    await maybe_delete_sent(bot, sent, delay)
    await maybe_delete_message(bot, message, delay=5)


async def send_buyer_menu(
    bot: Bot,
    chat_id: int,
    text: str = "Меню покупателя",
    business_connection_id: str | None = None,
):
    """Отправляет покупателю inline-кнопки, которые видны прямо под сообщением."""
    logger.info(
        "SEND_BUYER_INLINE_MENU chat_id=%s business_id=%s",
        chat_id,
        business_connection_id,
    )
    return await safe_send_message(
        bot,
        chat_id,
        text,
        business_connection_id=business_connection_id,
        reply_markup=buyer_inline_menu_keyboard(),
    )


async def send_supplier_menu(
    bot: Bot,
    chat_id: int,
    text: str = "Меню поставщика",
    business_connection_id: str | None = None,
):
    """Отправляет поставщику inline-кнопки, которые видны прямо под сообщением."""
    logger.info(
        "SEND_SUPPLIER_INLINE_MENU chat_id=%s business_id=%s",
        chat_id,
        business_connection_id,
    )
    return await safe_send_message(
        bot,
        chat_id,
        text,
        business_connection_id=business_connection_id,
        reply_markup=supplier_inline_menu_keyboard(),
    )


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text)
    if ADMIN_ALERT_CHAT_ID:
        await safe_send_message(bot, ADMIN_ALERT_CHAT_ID, text)


async def send_service_keyboard(
    bot: Bot,
    message: Message,
    order_id: int,
    business_connection_id: str | None,
    page: int = 0,
) -> None:
    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order or order.status != "waiting_service":
            closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
            await answer_message(bot, message, closed_text, business_connection_id)
            return
        services, max_page = await get_services_page(session, page, SERVICE_PAGE_SIZE)
        text = await get_text(session, "service_select", "Выберите сервис кнопкой ниже или напишите название из списка.")

    if not services:
        await answer_message(bot, message, "Сервисы не настроены. Админ должен добавить /add_service Название", business_connection_id)
        return

    await answer_message(
        bot,
        message,
        f"{text}\n\nСтраница {page + 1}/{max_page + 1}",
        business_connection_id,
        reply_markup=service_keyboard_from_services(services, page, max_page, order_id),
    )



async def handle_unknown_buyer(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
    text: str,
) -> None:
    logger.info(
        "UNKNOWN_BUYER_IGNORED from_id=%s username=%s chat_id=%s text=%s",
        message.from_user.id if message.from_user else None,
        message.from_user.username if message.from_user else None,
        message.chat.id,
        text[:200],
    )

    if AUTO_DELETE_UNKNOWN_BUYERS:
        await maybe_delete_message(bot, message, delay=5)

    if NOTIFY_UNKNOWN_BUYERS and message.from_user:
        await notify_admins(
            bot,
            "Написал человек без активного заказа.\n\n"
            f"Telegram ID: {message.from_user.id}\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
            f"Текст: {text}",
        )

    if IGNORE_NON_BUYERS:
        return

    async with SessionLocal() as session:
        order_not_found_text = await get_text(
            session,
            "order_not_found",
            "Заказ не найден.\n\nЕсли вы уже оплатили, напишите админу.",
        )

    await temp_answer(bot, message, order_not_found_text, business_connection_id)


async def process_admin_pending_input(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user or not is_admin(message.from_user.id):
        return False

    admin_id = message.from_user.id
    key = ADMIN_TEXT_EDIT_WAIT.get(admin_id)
    if not key:
        return False

    text = (message.text or "").strip()

    if not text:
        await temp_answer(bot, message, "Пришлите новый текст сообщением.", business_connection_id)
        return True

    if text.lower() in {"отмена", "cancel", "/cancel"}:
        ADMIN_TEXT_EDIT_WAIT.pop(admin_id, None)
        await temp_answer(bot, message, "Редактирование отменено.", business_connection_id)
        return True

    async with SessionLocal() as session:
        result = await set_text(session, key, text)

    ADMIN_TEXT_EDIT_WAIT.pop(admin_id, None)

    await temp_answer(
        bot,
        message,
        f"{result}\n\nНовый текст:\n{text}",
        business_connection_id,
        reply_markup=admin_panel_keyboard(),
    )
    return True



async def process_admin_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user or not is_admin(message.from_user.id):
        return False

    text = (message.text or "").strip()
    parts = text.split()

    if text in {"/admin", "/panel", "/menu"}:
        await answer_message(bot, message, admin_panel_text(), business_connection_id, reply_markup=admin_panel_keyboard())
        return True

    if text == "/services":
        async with SessionLocal() as session:
            result = await services_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text == "/texts":
        async with SessionLocal() as session:
            result = await texts_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text == "/lists":
        async with SessionLocal() as session:
            result = await lists_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/add_list"):
        name = text.replace("/add_list", "", 1).strip()
        if not name:
            await answer_message(bot, message, "Формат:\n/add_list Название\n\nПример:\n/add_list numbers", business_connection_id)
            return True
        async with SessionLocal() as session:
            result = await add_service_list(session, name)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/list_add_service"):
        payload = text.replace("/list_add_service", "", 1).strip()
        if "|" not in payload:
            await answer_message(bot, message, "Формат:\n/list_add_service Лист | Сервис", business_connection_id)
            return True
        list_name, service_name = [x.strip() for x in payload.split("|", 1)]
        async with SessionLocal() as session:
            result = await add_service_to_list(session, list_name, service_name)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/add_service"):
        name = text.replace("/add_service", "", 1).strip()
        if not name:
            await answer_message(bot, message, "Формат:\n/add_service Название\n\nПример:\n/add_service Telegram", business_connection_id)
            return True

        async with SessionLocal() as session:
            result = await add_service(session, name)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/remove_service"):
        name = text.replace("/remove_service", "", 1).strip()
        if not name:
            await answer_message(bot, message, "Формат:\n/remove_service Название", business_connection_id)
            return True

        async with SessionLocal() as session:
            result = await remove_service(session, name)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/set_service_emoji"):
        payload = text.replace("/set_service_emoji", "", 1).strip()
        if "|" not in payload:
            await answer_message(
                bot,
                message,
                "Формат:\n/set_service_emoji Название | эмодзи\n\nПример:\n/set_service_emoji Telegram | 🔥",
                business_connection_id,
            )
            return True

        name, emoji = [x.strip() for x in payload.split("|", 1)]

        async with SessionLocal() as session:
            result = await set_service_emoji(session, name, emoji)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/set_text"):
        payload = text.replace("/set_text", "", 1).strip()
        if "|" not in payload:
            await answer_message(
                bot,
                message,
                "Формат:\n/set_text ключ | новый текст\n\n"
                "Ключи:\n"
                "thank_you\nservice_accepted\nservice_select\norder_not_found\ncontact_forbidden\n"
                "\nПример:\n/set_text thank_you | Спасибо за покупку!",
                business_connection_id,
            )
            return True

        key, value = [x.strip() for x in payload.split("|", 1)]

        async with SessionLocal() as session:
            result = await set_text(session, key, value)

        await answer_message(bot, message, result, business_connection_id)
        return True

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
        await safe_send_message(bot, supplier_id, "Вы добавлены как поставщик. Откройте панель кнопкой ниже.", reply_markup=supplier_inline_menu_keyboard())

        await answer_message(bot, message, f"OK. Поставщик добавлен.\nID: {supplier.telegram_id}\nИмя: {supplier.name}", business_connection_id)
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


async def is_supplier_user(user_id: int) -> bool:
    async with SessionLocal() as session:
        from app.models import Supplier
        from sqlalchemy import select
        result = await session.execute(select(Supplier).where(Supplier.telegram_id == user_id, Supplier.is_active == True))
        return result.scalars().first() is not None




async def send_supplier_reply_buttons(bot: Bot, supplier_id: int) -> None:
    await safe_send_message(
        bot,
        supplier_id,
        "Кнопки поставщика включены ниже.",
        reply_markup=supplier_reply_keyboard(),
    )


def supplier_empty_panel_text() -> str:
    return (
        "🚚 Панель поставщика\n\n"
        "Ожидающих заявок сейчас нет.\n\n"
        "Когда появится новая заявка, бот сам пришлёт уведомление с кнопками.\n"
        "Пока можно пользоваться меню ниже.\n\n"
        "Команды:\n"
        "/supplier — открыть панель поставщика\n"
        "/pending — заявки в ожидании\n"
        "/work — все активные заявки\n"
        "/profile — профиль поставщика\n"
        "/commands — список команд"
    )


def supplier_commands_text() -> str:
    return (
        "📖 Команды поставщика\n\n"
        "Основные команды:\n"
        "/start — открыть меню\n"
        "/supplier — открыть панель поставщика\n"
        "/pending — заявки в ожидании\n"
        "/work — все активные заявки\n"
        "/profile — профиль поставщика\n"
        "/commands — список команд\n\n"
        "Как работать:\n"
        "1. Дождитесь новой заявки или откройте /pending.\n"
        "2. Нажмите заявку.\n"
        "3. Нажмите «Взять в работу» или «Отправить номер/код».\n"
        "4. Отправьте номер или код обычным сообщением.\n\n"
        "Важно: если нужно отправить номер или код — сначала выберите конкретную заявку кнопкой.\n"
        "Если заявок нет — это нормально, значит сейчас ничего не ждёт поставщика."
    )



def supplier_main_panel_text() -> str:
    return (
        "🚚 Панель поставщика\n\n"
        "Выберите раздел:\n\n"
        "📋 Заявки — список заявок и фильтры\n"
        "📞 Ждут номер — заявки, где нужно выдать номер\n"
        "🔑 Ждут код — заявки, где нужно выдать код\n"
        "👤 Мой профиль — ваша статистика\n"
        "📖 Команды — справка по работе"
    )


def supplier_requests_panel_text() -> str:
    return (
        "📋 Заявки поставщика\n\n"
        "Выберите, какие заявки показать.\n"
        "После выбора конкретной заявки бот будет ждать номер или код обычным сообщением."
    )


def buyer_main_panel_text() -> str:
    return (
        "🏠 Меню покупателя\n\n"
        "Выберите раздел:\n\n"
        "📦 Активный заказ — текущий заказ и действия\n"
        "🧾 Мои заказы — история последних заказов\n"
        "👤 Мой профиль — краткая информация\n"
        "🆘 Помощь — что делать на каждом этапе"
    )


def format_buyer_active_order_text(order) -> str:
    if not order:
        return (
            "📦 Активный заказ\n\n"
            "Активного заказа сейчас нет.\n\n"
            "Если вы уже оплатили заказ, напишите в поддержку или дождитесь обновления данных от shop-бота."
        )

    status_labels = {
        "waiting_service": "ожидает выбора сервиса",
        "waiting_supplier_number": "поставщик готовит номер",
        "number_sent_to_customer": "номер отправлен, ждём код",
        "waiting_supplier_code": "поставщик готовит код",
        "code_sent_to_customer": "код отправлен, ждём подтверждение",
        "confirmed": "закрыт успешно",
        "problem": "есть проблема",
        "cancelled": "отменён",
    }
    return (
        "📦 Активный заказ\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"Товар: {order.product_name or 'не указан'}\n"
        f"Сервис: {order.service_name or 'ещё не выбран'}\n"
        f"Статус: {status_labels.get(order.status, order.status)}\n"
        f"Номер: {order.phone_number or 'ещё нет'}\n"
        f"Код: {order.verification_code or 'ещё нет'}\n\n"
        "Доступные действия показаны кнопками ниже."
    )


SUPPLIER_PANEL_TEXT_BUTTONS = {
    "🚚 Панель поставщика",
    "⏳ Заявки в ожидании",
    "⏳ Все активные",
    "📞 Ждут номер",
    "🔑 Ждут код",
}

SUPPLIER_KNOWN_COMMANDS = {
    "/start",
    "/supplier",
    "/pending",
    "/work",
    "/profile",
    "/commands",
}


def is_supplier_command_like_text(text: str) -> bool:
    """
    Защита от бага, когда команда поставщика попадает в обработчик номера/кода.
    Любой текст, начинающийся с '/', считаем командой, а не номером или кодом.
    """
    return (text or "").strip().startswith("/")


async def send_supplier_unknown_command(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
    text: str,
) -> None:
    command = (text or "").strip()[:80]
    await answer_message(
        bot,
        message,
        (
            f"Неизвестная команда поставщика: {command}\n\n"
            "Используйте меню ниже или команду /commands.\n\n"
            + supplier_commands_text()
        ),
        business_connection_id,
        reply_markup=supplier_inline_menu_keyboard(),
    )


async def send_supplier_pending_panel(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    supplier_id = message.from_user.id
    async with SessionLocal() as session:
        pending_text, max_page = await supplier_pending_text(session, supplier_id, 0, SUPPLIER_PAGE_SIZE)
        rows, max_page = await get_supplier_pending_rows(session, supplier_id, 0, SUPPLIER_PAGE_SIZE)

    if rows:
        text = pending_text + "\n\nВыберите заявку кнопкой ниже, потом отправьте номер или код сообщением."
        markup = supplier_orders_keyboard(rows, 0, max_page)
    else:
        text = supplier_empty_panel_text()
        markup = supplier_inline_menu_keyboard()

    await answer_message(bot, message, text, business_connection_id, reply_markup=markup)


async def process_supplier_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user:
        return False
    if not await is_supplier_user(message.from_user.id):
        return False

    text = (message.text or "").strip()

    if text in {"/commands", "📖 Команды"}:
        await answer_message(bot, message, supplier_commands_text(), business_connection_id, reply_markup=supplier_commands_keyboard())
        return True

    if text in {"/start", "/supplier"} or text == "🚚 Панель поставщика":
        await answer_message(bot, message, supplier_main_panel_text(), business_connection_id, reply_markup=supplier_inline_menu_keyboard())
        return True

    if text in {"/work", "/pending"} or text in SUPPLIER_PANEL_TEXT_BUTTONS:
        await send_supplier_pending_panel(bot, message, business_connection_id)
        return True

    if text == "/profile" or text == "👤 Мой профиль":
        async with SessionLocal() as session:
            profile_text = await supplier_profile_text(session, message.from_user.id, message.from_user.username)
        await answer_message(bot, message, profile_text, business_connection_id, reply_markup=supplier_inline_menu_keyboard())
        return True

    # ВАЖНО: неизвестные команды поставщика не должны попадать в обработчик номера/кода.
    # Иначе бот может отвечать «Не смог найти номер» или «Ожидающих заявок нет» на любую команду.
    if is_supplier_command_like_text(text):
        await send_supplier_unknown_command(bot, message, business_connection_id, text)
        return True

    return False


async def process_command_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    text = (message.text or "").strip()
    user_id = message.from_user.id
    username = message.from_user.username

    if await process_admin_command(bot, message, business_connection_id):
        return

    if await process_supplier_command(bot, message, business_connection_id):
        return

    if text == "/start":
        async with SessionLocal() as session:
            order = await find_active_order_for_customer(session, user_id, username)

        if order and order.status == "waiting_service":
            await send_service_keyboard(bot, message, order.id, business_connection_id, page=0)
            return

        if await is_supplier_user(user_id):
            await send_supplier_pending_panel(bot, message, business_connection_id)
            return

        await answer_message(bot, message, buyer_main_panel_text(), business_connection_id, reply_markup=buyer_inline_menu_keyboard())
        return

    if text == "👤 Мой профиль" or text == "/profile":
        if is_admin(user_id):
            async with SessionLocal() as session:
                profile_text = await admin_profile_text(session, user_id, username)
            await answer_message(bot, message, profile_text, business_connection_id, reply_markup=admin_profile_keyboard())
            return

        if await is_supplier_user(user_id):
            async with SessionLocal() as session:
                profile_text = await supplier_profile_text(session, user_id, username)
            await answer_message(bot, message, profile_text, business_connection_id, reply_markup=supplier_inline_menu_keyboard())
            return

        async with SessionLocal() as session:
            profile_text = await buyer_profile_text(session, user_id, username)
        await answer_message(bot, message, profile_text, business_connection_id, reply_markup=buyer_inline_menu_keyboard())
        return

    if text == "📦 Мои заказы" or text == "/orders":
        async with SessionLocal() as session:
            orders_text = await buyer_orders_text(session, user_id, username, BUYER_ORDERS_LIMIT)
        await answer_message(bot, message, orders_text, business_connection_id, reply_markup=buyer_back_keyboard())
        return

    if text == "🆘 Помощь":
        await answer_message(
            bot,
            message,
            "Помощь\n\nЕсли заказ активен — используйте кнопки в чате.\nЕсли есть проблема — нажмите кнопку проблемы под номером или кодом.",
            business_connection_id,
            reply_markup=buyer_back_keyboard(),
        )
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
            last_orders = await get_last_orders_text(session)
        await answer_message(bot, message, last_orders, business_connection_id)
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
            result_text = await set_customer_by_order_id(session, order_id, telegram_id)
        await answer_message(bot, message, result_text, business_connection_id)
        return

    await answer_message(bot, message, "Неизвестная команда. Напишите /ping или /admin", business_connection_id)


async def process_admaker_message(bot: Bot, message: Message) -> None:
    text = message.text or ""
    data = extract_purchase_data(text)

    if not data:
        await notify_admins(bot, f"Shop-бот прислал сообщение, но покупку распарсить не удалось.\n\nТекст:\n{text}")
        return

    async with SessionLocal() as session:
        order = await create_or_update_order_from_purchase(session, data)

    await notify_admins(
        bot,
        "OK. Покупка обработана.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Покупатель ID: {order.customer_telegram_id}\n"
        f"Username: @{order.customer_username or 'нет'}\n"
        f"Товар ID: {order.product_id or 'нет'}\n"
        f"Товар: {order.product_name}\n"
        f"Статус: {order.status}",
    )


async def send_supplier_request_for_order(bot: Bot, order, business_connection_id: str | None) -> bool:
    order_id_value = getattr(order, "id", order)
    actual_business_id = business_connection_id or getattr(order, "business_connection_id", None)

    async with SessionLocal() as session:
        db_order = await get_order_by_id(session, order_id_value)
        if not db_order:
            return False
        supplier = await find_supplier_for_order(session, db_order)

    if not supplier:
        await notify_admins(
            bot,
            "Нет активного поставщика для заказа.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"Товар: {order.product_name}\n"
            "Добавь поставщика и привяжи товар:\n"
            "/add_supplier TELEGRAM_ID Имя\n"
            "/bind_supplier TELEGRAM_ID товар_или_ID",
        )
        return False

    supplier_text = (
        "Новый заказ.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Товар ID: {order.product_id or 'нет'}\n"
        f"Товар: {order.product_name}\n"
        f"Сервис: {order.service_name}\n\n"
        "Пришлите номер для покупателя.\n"
        "Пример: +79990000000"
    )

    ok = await safe_send_message(bot, supplier.telegram_id, supplier_text, actual_business_id, reply_markup=supplier_inline_menu_keyboard())
    if not ok:
        ok = await safe_send_message(bot, supplier.telegram_id, supplier_text)

    if not ok:
        await notify_admins(bot, f"Не смог отправить заявку поставщику {supplier.telegram_id} по заказу #{order.operation_id}")
        return False

    async with SessionLocal() as session:
        supplier_request = await create_supplier_request(session, order_id_value, supplier.telegram_id, "number")

    # Повторно отправим короткое сообщение с кнопками именно по этой заявке.
    # Старое текстовое уведомление выше оставлено для совместимости.
    button_text = (
        "📦 Новый заказ\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Товар: {order.product_name}\n"
        f"Сервис: {order.service_name}\n\n"
        "Выберите действие кнопкой ниже."
    )
    sent_with_buttons = await safe_send_message(
        bot,
        supplier.telegram_id,
        button_text,
        actual_business_id,
        reply_markup=supplier_new_order_keyboard(supplier_request.id, "number"),
    )
    if not sent_with_buttons:
        sent_with_buttons = await safe_send_message(
            bot,
            supplier.telegram_id,
            button_text,
            reply_markup=supplier_new_order_keyboard(supplier_request.id, "number"),
        )

    if sent_with_buttons and hasattr(sent_with_buttons, "message_id"):
        async with SessionLocal() as session:
            await set_supplier_request_message_id(session, supplier_request.id, sent_with_buttons.message_id)

    return True


async def accept_service_for_order(bot: Bot, message: Message | None, order_id: int, service_name: str, business_connection_id: str | None) -> None:
    # ВАЖНО:
    # Не используем ORM-объект order после выхода из async with SessionLocal().
    # Иначе SQLAlchemy может дать DetachedInstanceError.
    order_id_value = order_id
    actual_business_id = business_connection_id
    service_accepted_text = "OK. Сервис принят. Ожидайте номер."

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            if message:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
            return

        if order.status != "waiting_service":
            closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
            if message:
                await answer_message(bot, message, closed_text, business_connection_id or order.business_connection_id)
            return

        order.service_name = service_name
        order.status = "waiting_supplier_number"

        if message and message.from_user:
            order.buyer_chat_id = message.chat.id
            order.customer_telegram_id = message.from_user.id

        if business_connection_id:
            order.business_connection_id = business_connection_id

        order.updated_at = datetime.utcnow()
        await increment_service_usage(session, service_name)
        await session.commit()
        await session.refresh(order)

        order_id_value = order.id
        actual_business_id = business_connection_id or order.business_connection_id
        service_accepted_text = await get_text(session, "service_accepted", "OK. Сервис принят. Ожидайте номер.")

        try:
            await create_action_event(
                session,
                "service_confirmed",
                f"service={service_name}",
                user_id=order.customer_telegram_id,
                order_id=order.id,
            )
        except Exception:
            logger.exception("create_action_event failed")

    # Берём свежий объект заказа в новой сессии и передаём его дальше.
    async with SessionLocal() as session:
        fresh_order = await get_order_by_id(session, order_id_value)

    if not fresh_order:
        if message:
            await answer_message(bot, message, "Заказ не найден после обновления.", actual_business_id)
        return

    ok = await send_supplier_request_for_order(bot, fresh_order, actual_business_id)

    if message:
        if ok:
            await answer_message(bot, message, service_accepted_text, actual_business_id)
        else:
            await answer_message(
                bot,
                message,
                "Сервис принят, но поставщик для этого товара не найден или недоступен. Админ уведомлён.",
                actual_business_id,
            )


async def handle_buyer_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    username = message.from_user.username
    text = (message.text or "").strip()

    async with SessionLocal() as session:
        contact_forbidden_text = await get_text(session, "contact_forbidden", "Нельзя отправлять контакты, username, ссылки или номера для связи.")
        order_not_found_text = await get_text(session, "order_not_found", "Заказ не найден.\n\nЕсли вы уже оплатили, напишите админу.")

    if not text:
        await temp_answer(bot, message, "Пришлите только название сервиса текстом или выберите кнопку. Фото/файлы поставщику не отправляются.", business_connection_id)
        return

    if contains_forbidden_contact(text):
        await temp_answer(bot, message, contact_forbidden_text, business_connection_id)
        return

    async with SessionLocal() as session:
        order = await find_waiting_service_order_for_customer(session, user_id, username)

        if not order:
            await handle_unknown_buyer(bot, message, business_connection_id, text)
            return

        order.buyer_chat_id = message.chat.id
        order.customer_telegram_id = user_id
        if business_connection_id:
            order.business_connection_id = business_connection_id

        service = await find_service_by_text(session, text)
        await session.commit()
        await session.refresh(order)

    if not service:
        await send_service_keyboard(bot, message, order.id, business_connection_id or order.business_connection_id, page=0)
        await maybe_delete_message(bot, message)
        return

    await accept_service_for_order(bot, message, order.id, service.name, business_connection_id or order.business_connection_id)
    await maybe_delete_message(bot, message)


async def handle_supplier_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    supplier_id = message.from_user.id
    text = (message.text or "").strip()

    # Дополнительная страховка: даже если route_message по какой-то причине пропустил команду,
    # команда поставщика не должна восприниматься как номер или код.
    if is_supplier_command_like_text(text):
        await send_supplier_unknown_command(bot, message, business_connection_id, text)
        return

    async with SessionLocal() as session:
        # ВАЖНО: active_request всегда создаётся до использования.
        # Это полностью убирает UnboundLocalError.
        active_request = await find_active_supplier_request(session, supplier_id)

        number_request = (
            active_request
            if active_request and active_request.request_type == "number"
            else await find_waiting_supplier_request(session, supplier_id, "number")
        )

        if number_request:
            phone = extract_phone(text)
            if not phone:
                await answer_message(bot, message, "Не смог найти номер. Пример: +79990000000", business_connection_id)
                return

            order = await get_order_by_id(session, number_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
                return

            if order.status == "confirmed":
                await answer_message(bot, message, "Заказ уже закрыт.", business_connection_id)
                return

            order.phone_number = phone
            order.status = "number_sent_to_customer"
            order.updated_at = datetime.utcnow()
            number_request.status = "answered"
            number_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id or business_connection_id or ADMIN_BUSINESS_CONNECTION_ID

            ok = False
            if target_chat_id:
                ok = await safe_send_message(
                    bot,
                    target_chat_id,
                    phone,
                    business_connection_id=target_business_id,
                    reply_markup=number_keyboard(order.id),
                )

            if not ok:
                await answer_message(bot, message, "Номер принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(
                    bot,
                    f"Не смог отправить номер покупателю.\nЗаказ #{order.operation_id}\nbusiness_connection_id: {target_business_id}",
                )
                return

            sent = await answer_message(bot, message, "OK. Номер отправлен покупателю.", business_connection_id, reply_markup=supplier_inline_menu_keyboard())
            try:
                await maybe_delete_sent(bot, sent)
                await maybe_delete_message(bot, message, delay=5)
            except NameError:
                pass
            return

        # Если active_request уже был number и обработался выше, сюда не попадём.
        # Если active_request code или активной нет — ищем заявку на код.
        active_request = await find_active_supplier_request(session, supplier_id)

        code_request = (
            active_request
            if active_request and active_request.request_type == "code"
            else await find_waiting_supplier_request(session, supplier_id, "code")
        )

        if code_request:
            code = extract_code(text)
            if not code:
                await answer_message(bot, message, "Не смог найти код. Пример: 123456", business_connection_id)
                return

            order = await get_order_by_id(session, code_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
                return

            if order.status == "confirmed":
                await answer_message(bot, message, "Заказ уже закрыт.", business_connection_id)
                return

            order.verification_code = code
            order.status = "code_sent_to_customer"
            order.updated_at = datetime.utcnow()
            code_request.status = "answered"
            code_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id or business_connection_id or ADMIN_BUSINESS_CONNECTION_ID

            ok = False
            if target_chat_id:
                ok = await safe_send_message(
                    bot,
                    target_chat_id,
                    code,
                    business_connection_id=target_business_id,
                    reply_markup=confirm_keyboard(order.id),
                )

            if not ok:
                await answer_message(bot, message, "Код принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(
                    bot,
                    f"Не смог отправить код покупателю.\nЗаказ #{order.operation_id}\nbusiness_connection_id: {target_business_id}",
                )
                return

            sent = await answer_message(bot, message, "OK. Код отправлен покупателю.", business_connection_id, reply_markup=supplier_inline_menu_keyboard())
            try:
                await maybe_delete_sent(bot, sent)
                await maybe_delete_message(bot, message, delay=5)
            except NameError:
                pass
            return

    # Сюда попадаем только если у поставщика нет активной заявки.
    try:
        await answer_message(
            bot,
            message,
            (
                "Нет активного запроса для вас.\n\n"
                "Откройте панель кнопкой ниже и выберите конкретную заявку. "
                "После этого отправьте номер или код обычным сообщением."
            ),
            business_connection_id,
            reply_markup=supplier_inline_menu_keyboard(),
        )
    except NameError:
        await answer_message(bot, message, "Нет активного запроса для вас. Панель: /supplier", business_connection_id)


async def route_message(bot: Bot, message: Message, is_business: bool) -> None:
    if not message.from_user:
        return

    me = await bot.me()
    sender = message.from_user
    user_id = sender.id
    username = (sender.username or "").replace("@", "").lower()
    text = (message.text or "").strip()
    business_connection_id = get_business_id(message) if is_business else None

    logger.info(
        "HANDLED_TEXT is_business=%s from_id=%s username=%s is_bot=%s chat_id=%s business_id=%s text=%s",
        is_business, user_id, username, sender.is_bot, message.chat.id, business_connection_id, text[:200],
    )

    if user_id == me.id:
        logger.info("IGNORED: own bot message")
        return

    if is_admin(user_id) and not text.startswith("/"):
        if await process_admin_pending_input(bot, message, business_connection_id):
            return
        logger.info("IGNORED: admin non-command message to avoid self-cycle")
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

    async with SessionLocal() as session:
        from app.models import Supplier
        from sqlalchemy import select
        result = await session.execute(select(Supplier).where(Supplier.telegram_id == user_id, Supplier.is_active == True))
        supplier = result.scalars().first()

    if supplier:
        await handle_supplier_message(bot, message, business_connection_id)
        return

    await handle_buyer_message(bot, message, business_connection_id)


async def resend_problem_to_supplier(bot: Bot, order, problem_type: str) -> None:
    async with SessionLocal() as session:
        supplier = await find_supplier_for_order(session, order)

    if not supplier:
        await notify_admins(bot, f"Проблема по заказу #{order.operation_id}, но поставщик не найден.")
        return

    if problem_type == "code":
        request_type = "code"
        supplier_text = (
            "Проблема: код не работает.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name}\n"
            f"Номер: {order.phone_number or 'нет'}\n"
            f"Старый код: {order.verification_code or 'нет'}\n\n"
            "Проверьте цифры и пришлите новый/правильный код.\n"
            "Панель поставщика: /supplier"
        )
    else:
        request_type = "number"
        supplier_text = (
            "Проблема: номер не работает.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name}\n"
            f"Старый номер: {order.phone_number or 'нет'}\n\n"
            "Пришлите новый номер.\n"
            "Панель поставщика: /supplier"
        )

    async with SessionLocal() as session:
        problem_request = await create_supplier_request(session, order.id, supplier.telegram_id, request_type)

    ok = await safe_send_message(
        bot,
        supplier.telegram_id,
        supplier_text,
        order.business_connection_id,
        reply_markup=supplier_new_order_keyboard(problem_request.id, request_type),
    )
    if not ok:
        ok = await safe_send_message(
            bot,
            supplier.telegram_id,
            supplier_text,
            reply_markup=supplier_new_order_keyboard(problem_request.id, request_type),
        )

    if ok and hasattr(ok, "message_id"):
        async with SessionLocal() as session:
            await set_supplier_request_message_id(session, problem_request.id, ok.message_id)


async def handle_admin_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user or not is_admin(callback.from_user.id):
        return False

    data = callback.data or ""

    if data == "admin:profile":
        async with SessionLocal() as session:
            text = await admin_profile_text(
                session,
                callback.from_user.id,
                callback.from_user.username if callback.from_user else None,
            )
        await update_or_send(callback, text, reply_markup=admin_profile_keyboard())
        await callback.answer()
        return True


    if data == "admin:stats":
        async with SessionLocal() as session:
            text = await admin_stats_text(session)
        await update_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()
        return True



    if data == "admin:problems":
        async with SessionLocal() as session:
            orders = await get_problem_order_rows(session)
        if not orders:
            await update_or_send(callback, "⚠️ Проблемные заказы\n\nПроблемных заказов сейчас нет.", reply_markup=admin_back_keyboard())
        else:
            await update_or_send(
                callback,
                "⚠️ Проблемные заказы\n\nВыберите заказ:",
                reply_markup=admin_orders_keyboard(orders, back_callback="admin:panel"),
            )
        await callback.answer()
        return True

    if data == "admin:last_orders":
        async with SessionLocal() as session:
            orders = await get_recent_order_rows(session)
        if not orders:
            await update_or_send(callback, "🧾 Заказы\n\nЗаказов пока нет.", reply_markup=admin_back_keyboard())
        else:
            await update_or_send(
                callback,
                "🧾 Последние заказы\n\nВыберите заказ:",
                reply_markup=admin_orders_keyboard(orders, back_callback="admin:panel"),
            )
        await callback.answer()
        return True

    if data.startswith("admin:order:"):
        order_id = int(data.split(":")[2])
        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return True

        await update_or_send(callback, order_card_text(order), reply_markup=admin_order_card_keyboard(order.id))
        await callback.answer()
        return True

    if data.startswith("admin:order_status:"):
        parts = data.split(":")
        order_id = int(parts[2])
        status = parts[3]

        async with SessionLocal() as session:
            result = await set_order_status(session, order_id, status)
            order = await get_order_by_id(session, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return True

        await update_or_send(callback, result + "\n\n" + order_card_text(order), reply_markup=admin_order_card_keyboard(order.id))
        await callback.answer("Статус обновлён")
        return True

    if data.startswith("admin:order_resend:"):
        order_id = int(data.split(":")[2])

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return True

            # Если уже был номер, чаще всего нужно повторно запросить код.
            request_type = "code" if order.phone_number else "number"
            ok, result, order, supplier = await admin_create_supplier_request_for_order(session, order_id, request_type)

        if not ok or not order or not supplier:
            await update_or_send(callback, result, reply_markup=admin_back_keyboard())
            await callback.answer("Не получилось", show_alert=True)
            return True

        if request_type == "code":
            supplier_text = (
                "Повторный запрос от админа: нужен код.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"ID в базе: {order.id}\n"
                f"Товар: {order.product_name}\n"
                f"Сервис: {order.service_name}\n"
                f"Номер: {order.phone_number or 'нет'}\n\n"
                "Пришлите код."
            )
        else:
            supplier_text = (
                "Повторный запрос от админа: нужен номер.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"ID в базе: {order.id}\n"
                f"Товар: {order.product_name}\n"
                f"Сервис: {order.service_name}\n\n"
                "Пришлите номер."
            )

        sent = await safe_send_message(bot, supplier.telegram_id, supplier_text, order.business_connection_id)
        if not sent:
            sent = await safe_send_message(bot, supplier.telegram_id, supplier_text)

        text = (
            f"{result}\n\n"
            f"Поставщик: {supplier.telegram_id}\n"
            f"Запрос: {'код' if request_type == 'code' else 'номер'}\n"
            f"Отправка поставщику: {'OK' if sent else 'не удалось'}\n\n"
            + order_card_text(order)
        )
        await update_or_send(callback, text, reply_markup=admin_order_card_keyboard(order.id))
        await callback.answer("Повторный запрос создан")
        return True


    # Clean section navigation.
    if data == "admin:panel":
        await update_or_send(callback, admin_panel_text(), reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:suppliers":
        await update_or_send(callback, "🚚 Поставщики\n\nВыберите действие:", reply_markup=admin_suppliers_keyboard())
        await callback.answer()
        return True

    if data == "admin:services":
        await update_or_send(callback, "🧩 Сервисы\n\nВыберите действие:", reply_markup=admin_services_keyboard())
        await callback.answer()
        return True

    if data == "admin:lists":
        await update_or_send(callback, "📚 Листы сервисов\n\nВыберите действие:", reply_markup=admin_lists_keyboard())
        await callback.answer()
        return True

    if data == "admin:texts":
        await update_or_send(callback, "✏️ Тексты\n\nМожно посмотреть текущие тексты или выбрать текст для изменения.", reply_markup=admin_texts_menu_keyboard())
        await callback.answer()
        return True

    if data == "admin:settings":
        await update_or_send(callback, "⚙️ Настройки\n\nВыберите действие:", reply_markup=admin_settings_keyboard())
        await callback.answer()
        return True

    if data == "admin:suppliers_list":
        async with SessionLocal() as session:
            text = await list_suppliers_text(session)
        await update_or_send(callback, text, reply_markup=admin_suppliers_keyboard())
        await callback.answer()
        return True

    if data == "admin:services_list":
        async with SessionLocal() as session:
            text = await services_text(session)
        await update_or_send(callback, text, reply_markup=admin_services_keyboard())
        await callback.answer()
        return True

    if data == "admin:lists_list":
        async with SessionLocal() as session:
            text = await lists_text(session)
        await update_or_send(callback, text, reply_markup=admin_lists_keyboard())
        await callback.answer()
        return True

    if data == "admin:texts_list":
        async with SessionLocal() as session:
            text = await texts_text(session)
        await update_or_send(callback, text, reply_markup=admin_texts_menu_keyboard())
        await callback.answer()
        return True


    if data == "admin:panel":
        await update_or_send(callback, admin_panel_text(), reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:status":
        async with SessionLocal() as session:
            text = await get_status_text(session)
        await update_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()
        return True

    if data == "admin:last_orders":
        async with SessionLocal() as session:
            text = await get_last_orders_text(session)
        await update_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()
        return True

    if data == "admin:suppliers":
        async with SessionLocal() as session:
            text = await list_suppliers_text(session)
        await update_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()
        return True

    if data == "admin:services":
        async with SessionLocal() as session:
            text = await services_text(session)
        await update_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()
        return True


    if data == "admin:set_text_help":
        await update_or_send(
            callback,
            "Выберите текст, который хотите изменить.\n\nПосле выбора пришлите новый текст одним сообщением.",
            reply_markup=admin_text_keys_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("admin:edit_text:"):
        key = data.split(":", 2)[2]
        ADMIN_TEXT_EDIT_WAIT[callback.from_user.id] = key

        async with SessionLocal() as session:
            current = await get_text(session, key, "")

        await update_or_send(
            callback,
            f"Редактирование текста: {key}\n\nТекущий текст:\n{current or 'пусто'}\n\nПришлите новый текст одним сообщением.\nДля отмены напишите: отмена",
            reply_markup=admin_panel_keyboard(),
        )
        await callback.answer("Жду новый текст")
        return True

    if data == "admin:texts":
        async with SessionLocal() as session:
            text = await texts_text(session)
        await update_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()
        return True

    if data == "admin:lists":
        async with SessionLocal() as session:
            text = await lists_text(session)
        await update_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()
        return True

    help_texts = {
        "admin:add_supplier_help": "Добавить поставщика:\n/add_supplier TELEGRAM_ID Имя\n\nПример:\n/add_supplier 123456789 proxy_supplier",
        "admin:bind_supplier_help": "Привязать товар:\n/bind_supplier TELEGRAM_ID товар_или_ID\n\nПример:\n/bind_supplier 123456789 proxy",
        "admin:add_service_help": "Добавить сервис:\n/add_service Название\n\nПример:\n/add_service Telegram",
        "admin:service_emoji_help": "Эмодзи сервиса:\n/set_service_emoji Название | эмодзи\n\nПример:\n/set_service_emoji Telegram | 🔥",
        "admin:set_text_help": "Изменить текст:\n/set_text ключ | новый текст\n\nКлючи:\nthank_you\nservice_accepted\nservice_select\norder_not_found\ncontact_forbidden\norder_closed\nproblem_sent",
        "admin:list_help": "Листы сервисов:\n/add_list Название\n/list_add_service Лист | Сервис\n\nПоставщика можно привязать к листу:\n/bind_supplier TELEGRAM_ID НазваниеЛиста",
        "admin:commands": admin_panel_text(),
    }

    if data in help_texts:
        await update_or_send(callback, help_texts[data], reply_markup=admin_back_keyboard())
        await callback.answer()
        return True

    return False


async def handle_supplier_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user or not await is_supplier_user(callback.from_user.id):
        return False

    data = callback.data or ""

    if data == "supplier:panel":
        await update_or_send(callback, supplier_main_panel_text(), reply_markup=supplier_inline_menu_keyboard())
        await callback.answer()
        return True

    if data == "supplier:requests":
        await update_or_send(callback, supplier_requests_panel_text(), reply_markup=supplier_requests_menu_keyboard())
        await callback.answer()
        return True

    if data.startswith("supplier:filter:"):
        _, _, mode, page_raw = data.split(":")
        page = int(page_raw)

        async with SessionLocal() as session:
            rows, max_page = await supplier_rows_by_filter(session, callback.from_user.id, mode, page, SUPPLIER_PAGE_SIZE)
            text = await supplier_filter_text(mode, len(rows), page, max_page)

        await update_or_send(
            callback,
            text,
            reply_markup=supplier_orders_keyboard(rows, page, max_page) if rows else supplier_filter_keyboard(mode, page, max_page),
        )
        await callback.answer()
        return True


    if data == "supplier:profile":
        async with SessionLocal() as session:
            text = await supplier_profile_text(session, callback.from_user.id, callback.from_user.username)
        await update_or_send(callback, text, reply_markup=supplier_inline_menu_keyboard())
        await callback.answer()
        return True


    if data == "supplier:commands":
        await update_or_send(callback, supplier_commands_text(), reply_markup=supplier_commands_keyboard())
        await callback.answer()
        return True


    if data.startswith("supplier:take:"):
        request_id = int(data.split(":")[2])

        async with SessionLocal() as session:
            ok, result, request, order = await mark_supplier_request_in_progress(session, request_id)

        if not ok or not request or not order:
            await callback.answer(result, show_alert=True)
            return True

        if request.request_type == "number":
            buyer_text = "Номер уже в обработке. Ожидайте выдачи."
            supplier_text = (
                "📞 Заявка взята в работу.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Товар: {order.product_name}\n"
                f"Сервис: {order.service_name}\n\n"
                "Теперь отправьте номер сообщением."
            )
        else:
            buyer_text = "Код уже в обработке. Ожидайте выдачи."
            supplier_text = (
                "🔑 Заявка взята в работу.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Товар: {order.product_name}\n"
                f"Сервис: {order.service_name}\n"
                f"Номер: {order.phone_number or 'нет'}\n\n"
                "Теперь отправьте код сообщением."
            )

        target_chat_id = order.buyer_chat_id or order.customer_telegram_id
        target_business_id = order.business_connection_id or ADMIN_BUSINESS_CONNECTION_ID
        if target_chat_id:
            await safe_send_message(bot, target_chat_id, buyer_text, business_connection_id=target_business_id)

        await update_or_send(callback, supplier_text, reply_markup=supplier_request_actions_keyboard(request.id, request.request_type))
        await callback.answer("Заявка в работе")
        return True

    if data.startswith("supplier:answer:"):
        request_id = int(data.split(":")[2])

        async with SessionLocal() as session:
            ok, result, request, order = await mark_supplier_request_in_progress(session, request_id)

        if not ok:
            await callback.answer(result or "Заявка неактивна или уже обработана", show_alert=True)
            return True

        if not request or not order:
            await callback.answer("Заявка не найдена", show_alert=True)
            return True

        if request.request_type == "number":
            text = (
                "✍️ Отправьте номер сообщением.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Товар: {order.product_name}\n"
                f"Сервис: {order.service_name}"
            )
        else:
            text = (
                "✍️ Отправьте код сообщением.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Товар: {order.product_name}\n"
                f"Сервис: {order.service_name}\n"
                f"Номер: {order.phone_number or 'нет'}"
            )

        await update_or_send(callback, text, reply_markup=supplier_request_actions_keyboard(request.id, request.request_type))
        await callback.answer("Жду сообщение")
        return True


    if data.startswith("supplier:pending:"):
        page = int(data.split(":")[2])
        async with SessionLocal() as session:
            text, max_page = await supplier_pending_text(session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE)
            rows, max_page = await get_supplier_pending_rows(session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE)

        if rows:
            text = text + "\n\nВыберите заявку кнопкой ниже, потом отправьте номер или код сообщением."
            markup = supplier_orders_keyboard(rows, page, max_page)
        else:
            text = supplier_empty_panel_text()
            markup = supplier_inline_menu_keyboard()

        await update_or_send(callback, text, reply_markup=markup)
        await callback.answer()
        return True

    if data.startswith("supplier:req:"):
        parts = data.split(":")
        request_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        async with SessionLocal() as session:
            ok, msg, request, order = await select_supplier_request(session, callback.from_user.id, request_id)
            rows, max_page = await get_supplier_pending_rows(session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE)

        if not ok or not request or not order:
            await callback.answer(msg, show_alert=True)
            await update_or_send(callback, msg, reply_markup=supplier_orders_keyboard(rows, page, max_page))
            return True

        need_text = "номер" if request.request_type == "number" else "код"
        icon = "📞" if request.request_type == "number" else "🔑"
        selected_text = (
            f"{icon} Заявка выбрана.\n\n"
            f"Нужно отправить: {need_text}\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name or 'не указан'}\n"
            f"Номер: {order.phone_number or 'ещё нет'}\n\n"
            "Теперь отправьте ответ обычным сообщением в этот чат."
        )
        await update_or_send(callback, selected_text, reply_markup=supplier_orders_keyboard(rows, page, max_page))
        await callback.answer("Заявка выбрана")
        return True

    return False




async def handle_buyer_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user:
        return False

    data = callback.data or ""
    user_id = callback.from_user.id
    username = callback.from_user.username

    if data == "buyer:panel":
        await update_or_send(callback, buyer_main_panel_text(), reply_markup=buyer_inline_menu_keyboard())
        await callback.answer()
        return True

    if data == "buyer:active":
        async with SessionLocal() as session:
            order = await find_active_order_for_customer(session, user_id, username)
            text = format_buyer_active_order_text(order)
            order_id = order.id if order else None
            status = order.status if order else None
        await update_or_send(callback, text, reply_markup=buyer_active_order_keyboard(order_id, status))
        await callback.answer()
        return True

    if data == "buyer:profile":
        async with SessionLocal() as session:
            text = await buyer_profile_text(session, user_id, username)
        await update_or_send(callback, text, reply_markup=buyer_back_keyboard())
        await callback.answer()
        return True

    if data == "buyer:orders":
        async with SessionLocal() as session:
            text = await buyer_orders_text(session, user_id, username, BUYER_ORDERS_LIMIT)
        await update_or_send(callback, text, reply_markup=buyer_back_keyboard())
        await callback.answer()
        return True

    if data == "buyer:help":
        text = (
            "Помощь\n\n"
            "Если заказ активен — выберите сервис кнопкой или напишите название сервиса.\n"
            "После номера нажмите «Код отправлен».\n"
            "Если номер или код не работает — нажмите кнопку проблемы под сообщением."
        )
        await update_or_send(callback, text, reply_markup=buyer_back_keyboard())
        await callback.answer()
        return True

    return False


async def check_button_cooldown(callback: CallbackQuery, action: str) -> bool:
    if not callback.from_user:
        return True

    async with SessionLocal() as session:
        ok, remaining = await check_cooldown(
            session,
            callback.from_user.id,
            f"button:{action}",
            BUTTON_COOLDOWN_SECONDS,
        )

    if not ok:
        await callback.answer("Слишком часто. Попробуйте ещё раз через пару секунд.", show_alert=False)
        return False

    return True


async def handle_callback(bot: Bot, callback: CallbackQuery) -> None:
    data = callback.data or ""

    # BUTTON_COOLDOWN_APPLIED
    if data and not data.startswith("admin:"):
        if not await check_button_cooldown(callback, data.split(":")[0]):
            return

    logger.info("HANDLED_CALLBACK from_id=%s data=%s", callback.from_user.id if callback.from_user else None, data)

    if data.startswith("admin:"):
        handled = await handle_admin_callback(bot, callback)
        if handled:
            return
        await callback.answer("Команда только для админа", show_alert=True)
        return

    if data.startswith("supplier:"):
        handled = await handle_supplier_callback(bot, callback)
        if handled:
            return
        await callback.answer("Команда только для поставщика", show_alert=True)
        return

    if data.startswith("buyer:"):
        handled = await handle_buyer_callback(bot, callback)
        if handled:
            return
        await callback.answer("Неизвестная кнопка покупателя", show_alert=True)
        return

    if data.startswith("svcpage:"):

        _, order_id_raw, page_raw = data.split(":")
        order_id = int(order_id_raw)
        page = int(page_raw)

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id) if order_id else None
            if not order or order.status != "waiting_service":
                closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
                await callback.answer(closed_text, show_alert=True)
                return
            services, max_page = await get_services_page(session, page, SERVICE_PAGE_SIZE)
            text = await get_text(session, "service_select", "Выберите сервис кнопкой ниже или напишите название из списка.")

        await update_or_send(callback, f"{text}\n\nСтраница {page + 1}/{max_page + 1}", reply_markup=service_keyboard_from_services(services, page, max_page, order_id))
        await callback.answer()
        return

    if data.startswith("service:"):
        _, order_id_raw, service_slug = data.split(":", 2)
        order_id = int(order_id_raw)

        async with SessionLocal() as session:
            service = await find_service_by_slug(session, service_slug)
            order = await get_order_by_id(session, order_id) if order_id else None

            if not order or order.status != "waiting_service":
                closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
                await callback.answer(closed_text, show_alert=True)
                return

        if not service:
            await callback.answer("Сервис не найден", show_alert=True)
            return

        confirm_text = (
            "Подтвердите выбор сервиса\n\n"
            f"Вы выбрали: {service.name}\n\n"
            "После подтверждения заявка уйдёт поставщику."
        )

        await update_or_send(
            callback,
            confirm_text,
            reply_markup=service_confirm_keyboard(order_id, service_slug),
        )
        await callback.answer("Подтвердите выбор")
        return

    if data.startswith("service_confirm:"):
        _, order_id_raw, service_slug = data.split(":", 2)
        order_id = int(order_id_raw)
        message = callback.message if isinstance(callback.message, Message) else None

        async with SessionLocal() as session:
            service = await find_service_by_slug(session, service_slug)
            order = await get_order_by_id(session, order_id) if order_id else None

            if not order or order.status != "waiting_service":
                closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
                await callback.answer(closed_text, show_alert=True)
                return

            business_id = order.business_connection_id

        if not service:
            await callback.answer("Сервис не найден", show_alert=True)
            return

        await accept_service_for_order(bot, message, order_id, service.name, business_id)
        await callback.answer("Сервис подтверждён")
        return

    if data.startswith("code_sent:"):
        order_id = int(data.split(":")[1])

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            if order.status == "waiting_supplier_code":
                await callback.answer("Код уже запрошен. Подождите ответ поставщика.", show_alert=True)
                return

            order.status = "waiting_supplier_code"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

        async with SessionLocal() as session:
            db_order = await get_order_by_id(session, order_id)
            supplier = await find_supplier_for_order(session, db_order)

        if not supplier:
            if callback.message:
                await callback.message.answer("Поставщик для этого товара не найден.")
            await callback.answer()
            return

        supplier_text = (
            "Нужен код.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name}\n"
            f"Номер: {order.phone_number}\n\n"
            "Пришлите код. Пример: 123456\n"
            "Панель поставщика: /supplier"
        )

        async with SessionLocal() as session:
            code_request = await create_supplier_request(session, order.id, supplier.telegram_id, "code")

        ok = await safe_send_message(
            bot,
            supplier.telegram_id,
            supplier_text,
            order.business_connection_id,
            reply_markup=supplier_new_order_keyboard(code_request.id, "code"),
        )
        if not ok:
            ok = await safe_send_message(
                bot,
                supplier.telegram_id,
                supplier_text,
                reply_markup=supplier_new_order_keyboard(code_request.id, "code"),
            )

        if ok and hasattr(ok, "message_id"):
            async with SessionLocal() as session:
                await set_supplier_request_message_id(session, code_request.id, ok.message_id)

        if callback.message:
            await callback.message.answer("OK. Запросил код у поставщика." if ok else "Не смог написать поставщику.")

        await callback.answer()
        return

    if data.startswith("confirm_success:"):
        order_id = int(data.split(":")[1])

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            order.status = "confirmed"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)
            thank_you_text = await get_text(session, "thank_you", "Спасибо за покупку!")

        target_chat_id = order.buyer_chat_id or order.customer_telegram_id
        target_business_id = order.business_connection_id or ADMIN_BUSINESS_CONNECTION_ID

        thanks_sent = False
        if target_chat_id:
            thanks_sent = await safe_send_message(bot, target_chat_id, thank_you_text, business_connection_id=target_business_id, reply_markup=buyer_inline_menu_keyboard())

        if not thanks_sent and callback.message:
            await callback.message.answer(thank_you_text, reply_markup=buyer_inline_menu_keyboard())

        await callback.answer("Заказ завершён")
        return

    if data.startswith("number_invalid:") or data.startswith("code_invalid:"):
        order_id = int(data.split(":")[1])
        user_id = callback.from_user.id if callback.from_user else 0

        async with SessionLocal() as session:
            ok_cd, remaining = await check_cooldown(session, user_id, "problem", PROBLEM_COOLDOWN_SECONDS)

            if not ok_cd:
                minutes = max(1, remaining // 60)
                await callback.answer(f"Проблему можно отправлять раз в 1 минуту. Осталось примерно {minutes} мин.", show_alert=True)
                return

            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            order.status = "problem"
            order.updated_at = datetime.utcnow()
            await session.commit()

        problem_type = "code" if data.startswith("code_invalid:") else "number"
        await resend_problem_to_supplier(bot, order, problem_type)

        if callback.message:
            await callback.message.answer("Понял. Передал проблему админу и поставщику.")

        await notify_admins(
            bot,
            "Покупатель сообщил о проблеме.\n\n"
            f"Тип: {'код' if problem_type == 'code' else 'номер'}\n"
            f"Заказ ID в базе: {order_id}\n"
            f"Сервис: {order.service_name or 'нет'}\n"
            f"Номер: {order.phone_number or 'нет'}\n"
            f"Код: {order.verification_code or 'нет'}\n\n"
            "Запрос повторно отправлен поставщику."
        )
        await callback.answer()
        return

    await callback.answer("Неизвестная кнопка", show_alert=True)


async def on_message(message: Message, bot: Bot) -> None:
    logger.info("DISPATCHER_MESSAGE text=%s", message.text)
    await route_message(bot, message, is_business=False)


async def on_business_message(message: Message, bot: Bot) -> None:
    logger.info("DISPATCHER_BUSINESS_MESSAGE text=%s", message.text)
    await route_message(bot, message, is_business=True)


async def on_callback_query(callback: CallbackQuery, bot: Bot) -> None:
    logger.info("DISPATCHER_CALLBACK data=%s", callback.data)
    await handle_callback(bot, callback)


async def on_business_connection(event, bot: Bot) -> None:
    logger.info("DISPATCHER_BUSINESS_CONNECTION event=%s", event)


async def on_edited_business_message(message: Message, bot: Bot) -> None:
    logger.info("DISPATCHER_EDITED_BUSINESS_MESSAGE ignored text=%s", message.text)


async def on_deleted_business_messages(event, bot: Bot) -> None:
    logger.info("DISPATCHER_DELETED_BUSINESS_MESSAGES ignored event=%s", event)
