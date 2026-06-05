import asyncio
from decimal import Decimal
import logging
import re
from datetime import datetime

import aiohttp

from aiogram import Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

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
    BOT_TOKEN,
    BUG_REPORT_CHAT_IDS,
    SUPPLIER_IMMUNITY_SKIP_AUTODELETE,
    PROXYLINE_ENABLED,
    PROXYLINE_API_KEY,
    PROXYLINE_COUPON,
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
    supplier_section_orders_keyboard,
    supplier_empty_section_keyboard,
    supplier_wait_confirm_keyboard,
    buyer_orders_list_keyboard,
    buyer_empty_section_keyboard,
    buyer_order_card_keyboard,
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
    admin_admins_keyboard,
    admin_remove_admin_keyboard,
    admin_add_admin_cancel_keyboard,
    admin_proxy_settings_keyboard,
    admin_proxy_countries_keyboard,
    admin_proxy_periods_keyboard,
    admin_proxy_count_keyboard,
    admin_proxy_products_keyboard,
    buyer_proxy_country_keyboard,
    buyer_proxy_period_keyboard,
    buyer_proxy_confirm_keyboard,
    buyer_back_to_panel_keyboard,
    buyer_main_reply_keyboard,
)
from app.parsers import extract_purchase_data, extract_phone, extract_code
from app.proxyline_products import resolve_proxyline_product, is_proxyline_product, ProxylineProduct
from app.proxyline import ProxylineService, ProxylineError, format_proxyline_result
from app.proxy_settings import (
    get_proxy_shop_settings, save_proxy_setting, SUPPORTED_COUNTRIES, SUPPORTED_PERIODS,
    country_label, selection_dump, selection_load,
)
from app.senders import safe_send_message, answer_message
from app.repositories.product_providers import (
    get_product_provider, bind_product_provider, unbind_product_provider,
    list_product_providers, list_recent_admaker_products,
)

from app.models import ShopCategory, ShopProduct

from app.shop_admin_v20 import (
    customer_home_text, customer_home_keyboard,
    admin_shop_text, admin_shop_keyboard,
    all_categories, all_products, category_counts,
    admin_categories_text, admin_categories_keyboard,
    admin_category_text, admin_category_keyboard,
    admin_products_text, admin_products_keyboard,
    product_admin_text, admin_product_keyboard,
    toggle_category, move_category, delete_category,
    toggle_product, delete_product, create_category, create_product,
)
from app.shop import (
    shop_main_text, shop_main_keyboard, list_categories, list_products, get_product as get_shop_product,
    category_text, product_text, products_keyboard, product_keyboard, process_admin_shop_command, sync_products_from_orders,
)

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
    get_buyer_order_rows,
    buyer_order_card_text,
    supplier_section_text,
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
    mark_code_waiting_buyer_confirm,
    close_waiting_supplier_requests_for_order,
    is_db_admin,
    add_admin_user,
    remove_admin_user,
    list_admin_users_text,
    create_bug_report,
    get_admin_users,
)

logger = logging.getLogger(__name__)
logger.info("FIX_MARKER_FULL_VISUAL_SHOP_STYLE=v15 loaded")
logger.info("FIX_MARKER_PROXYLINE_ADMIN_BUYER_SELECT=v17 loaded")
logger.info("FIX_MARKER_RELEASE_REBUILD=v18 loaded")
logger.info("FIX_MARKER_PROXY_BOT_ONLY_SUPPLIER_NO_COOLDOWN=v18.2 loaded")
logger.info("FIX_MARKER_DELIVERY_COMMIT_AFTER_SEND=v18.3 loaded")

logger.info("FIX_MARKER_SHOP_CATALOG_MERGE=v19 loaded")
logger.info("FIX_MARKER_SHOP_UI_ADMIN_CATEGORIES=v20 loaded")
logger.info("FIX_MARKER_SHOP_UI_NAV_FIX=v20.1 loaded")
logger.info("FIX_MARKER_REPLY_KEYBOARD_ADMIN_ACCESS=v20.2 loaded")
logger.info("FIX_MARKER_REPLY_KEYBOARD_SCOPE_FIX=v20.3 loaded")
SHOP_ADMIN_WAIT: dict[int, tuple[str, int | None]] = {}
ADMIN_TEXT_EDIT_WAIT: dict[int, str] = {}
ADMIN_ADD_ADMIN_WAIT: set[int] = set()

# Динамические панели ролей: храним последнее inline-сообщение панели,
# чтобы команды и callback-кнопки редактировали его, а не спамили новым сообщением.
ROLE_PANEL_MESSAGES: dict[tuple[str, int, str], int] = {}
# Запоминаем Business connection по chat_id. CallbackQuery часто приходит без явного
# business_connection_id, но редактировать Business-сообщение без него нельзя.
BUSINESS_CONTEXT_BY_CHAT: dict[int, str] = {}
REPLY_KEYBOARD_CLEANED: set[int] = set()


def _is_message_not_modified_error(exc: Exception | str) -> bool:
    return "message is not modified" in str(exc).lower()


def _reply_markup_to_json(reply_markup):
    if reply_markup is None:
        return None
    if hasattr(reply_markup, "model_dump"):
        return reply_markup.model_dump(exclude_none=True)
    if hasattr(reply_markup, "dict"):
        return reply_markup.dict(exclude_none=True)
    return reply_markup


async def _raw_business_edit_text(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup=None,
    business_connection_id: str | None = None,
) -> bool:
    """
    Редактирует Business-сообщение напрямую через Telegram Bot API.

    Почему это нужно:
    часть версий aiogram 3 не умеет нормально прокидывать business_connection_id
    в edit_message_text. В итоге бот не редактирует старую Business-панель и
    каждый раз создаёт новое сообщение. Raw API фиксит именно это.
    """
    if not business_connection_id:
        return False

    payload = {
        "business_connection_id": business_connection_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    markup_json = _reply_markup_to_json(reply_markup)
    if markup_json is not None:
        payload["reply_markup"] = markup_json

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                data = await response.json(content_type=None)

        if data.get("ok"):
            logger.info(
                "ROLE_PANEL_RAW_BUSINESS_EDIT_OK chat_id=%s message_id=%s business_connection_id=%s",
                chat_id,
                message_id,
                business_connection_id,
            )
            return True

        description = data.get("description", "")
        if _is_message_not_modified_error(description):
            logger.info(
                "ROLE_PANEL_RAW_BUSINESS_EDIT_NOT_MODIFIED chat_id=%s message_id=%s",
                chat_id,
                message_id,
            )
            return True

        logger.info(
            "ROLE_PANEL_RAW_BUSINESS_EDIT_FAILED chat_id=%s message_id=%s status=%s response=%s",
            chat_id,
            message_id,
            data.get("error_code"),
            description,
        )
        return False
    except Exception as exc:
        logger.info(
            "ROLE_PANEL_RAW_BUSINESS_EDIT_EXCEPTION chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )
        return False


async def _bot_edit_text_safe(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup=None,
    business_connection_id: str | None = None,
) -> bool:
    """Редактирует сообщение. Возвращает True, если edit успешен или текст не изменился."""
    try:
        kwargs = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": reply_markup,
        }
        if business_connection_id:
            kwargs["business_connection_id"] = business_connection_id
        await bot.edit_message_text(**kwargs)
        return True
    except TypeError as exc:
        # Aiogram может не поддерживать business_connection_id в edit_message_text.
        # Для Business-панелей не падаем в обычный edit, а редактируем через raw API.
        if business_connection_id:
            raw_ok = await _raw_business_edit_text(
                chat_id,
                message_id,
                text,
                reply_markup=reply_markup,
                business_connection_id=business_connection_id,
            )
            if raw_ok:
                return True
        if _is_message_not_modified_error(exc):
            return True
        logger.info("ROLE_PANEL_EDIT_TYPEERROR chat_id=%s message_id=%s error=%s", chat_id, message_id, exc)
        return False
    except Exception as exc:
        if _is_message_not_modified_error(exc):
            return True

        # Если aiogram принял параметр, но Telegram всё равно не нашёл Business-сообщение,
        # делаем второй заход напрямую в Bot API. Это убирает спам новыми сообщениями.
        if business_connection_id:
            raw_ok = await _raw_business_edit_text(
                chat_id,
                message_id,
                text,
                reply_markup=reply_markup,
                business_connection_id=business_connection_id,
            )
            if raw_ok:
                return True

        logger.info("ROLE_PANEL_EDIT_FAILED chat_id=%s message_id=%s error=%s", chat_id, message_id, exc)
        return False


async def cleanup_reply_keyboard_once(
    bot: Bot,
    chat_id: int,
    business_connection_id: str | None = None,
) -> None:
    """
    Убирает старую нижнюю reply-клавиатуру, из-за которой снизу дублировались
    кнопки вроде «ключ/панель/профиль». Telegram убирает её только отдельным сообщением.
    """
    if chat_id in REPLY_KEYBOARD_CLEANED:
        return
    REPLY_KEYBOARD_CLEANED.add(chat_id)
    try:
        msg = await safe_send_message(
            bot,
            chat_id,
            "Панель обновлена.",
            business_connection_id=business_connection_id,
            reply_markup=ReplyKeyboardRemove(),
            allow_normal_fallback=False if business_connection_id else True,
        )
        await maybe_delete_sent(bot, msg, delay=3)
    except Exception as exc:
        logger.info("REPLY_KEYBOARD_CLEANUP_FAILED chat_id=%s error=%s", chat_id, exc)


async def send_or_edit_role_panel(
    bot: Bot,
    chat_id: int,
    role: str,
    text: str,
    reply_markup=None,
    business_connection_id: str | None = None,
    callback: CallbackQuery | None = None,
):
    """
    Единая динамическая панель как у админа:
    1) callback редактирует текущее сообщение;
    2) текстовая команда редактирует последнюю сохранённую панель;
    3) новое сообщение создаётся только если редактировать нечего/невозможно;
    4) нижняя reply-клавиатура убирается, чтобы не было дублей кнопок.
    """
    # ReplyKeyboardRemove нужен только при текстовой команде.
    # При callback не отправляем лишнее сообщение, иначе получится спам.
    if callback is None:
        await cleanup_reply_keyboard_once(bot, chat_id, business_connection_id)

    if business_connection_id:
        remember_business_context(chat_id, business_connection_id)

    panel_context = business_connection_id or "normal"
    key = (role, chat_id, panel_context)

    # Если пришёл callback — редактируем именно то сообщение, на котором была кнопка.
    # Для Business-сообщений нельзя использовать callback.message.edit_text без
    # business_connection_id: Telegram ответит "message to edit not found".
    if callback and callback.message:
        cb_message_id = callback.message.message_id
        ok = await _bot_edit_text_safe(
            bot,
            chat_id,
            cb_message_id,
            text,
            reply_markup=reply_markup,
            business_connection_id=business_connection_id,
        )
        if ok:
            ROLE_PANEL_MESSAGES[key] = cb_message_id
            logger.info(
                "ROLE_PANEL_CALLBACK_EDIT_OK role=%s chat_id=%s message_id=%s business_context=%s data=%s has_keyboard=%s",
                role,
                chat_id,
                cb_message_id,
                panel_context,
                callback.data,
                reply_markup is not None,
            )
            return callback.message
        logger.info(
            "ROLE_PANEL_CALLBACK_EDIT_FAILED_FINAL role=%s chat_id=%s message_id=%s business_context=%s data=%s",
            role,
            chat_id,
            cb_message_id,
            panel_context,
            callback.data,
        )

    # Если команда текстом — пытаемся редактировать последнее сообщение панели.
    old_message_id = ROLE_PANEL_MESSAGES.get(key)
    if old_message_id:
        ok = await _bot_edit_text_safe(
            bot,
            chat_id,
            old_message_id,
            text,
            reply_markup=reply_markup,
            business_connection_id=business_connection_id,
        )
        if ok:
            logger.info(
                "ROLE_PANEL_STORED_EDIT_OK role=%s chat_id=%s message_id=%s has_keyboard=%s",
                role,
                chat_id,
                old_message_id,
                reply_markup is not None,
            )
            return True

    # Последний fallback: отправляем новое и запоминаем его id.
    msg = await safe_send_message(
        bot,
        chat_id,
        text,
        business_connection_id=business_connection_id,
        reply_markup=reply_markup,
        allow_normal_fallback=False if business_connection_id else True,
    )
    if msg and getattr(msg, "message_id", None):
        ROLE_PANEL_MESSAGES[key] = msg.message_id
        logger.info(
            "ROLE_PANEL_SEND_NEW_OK role=%s chat_id=%s message_id=%s has_keyboard=%s",
            role,
            chat_id,
            msg.message_id,
            reply_markup is not None,
        )
    return msg


async def send_buyer_role_panel(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    business_connection_id: str | None = None,
    callback: CallbackQuery | None = None,
):
    return await send_or_edit_role_panel(
        bot, chat_id, "buyer", text, reply_markup, business_connection_id, callback
    )


async def send_supplier_role_panel(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    business_connection_id: str | None = None,
    callback: CallbackQuery | None = None,
):
    return await send_or_edit_role_panel(
        bot, chat_id, "supplier", text, reply_markup, business_connection_id, callback
    )

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


async def is_admin_user(user_id: int | None) -> bool:
    if is_admin(user_id):
        return True
    if not user_id:
        return False
    async with SessionLocal() as session:
        return await is_db_admin(session, user_id)


async def get_user_role(user_id: int | None) -> str:
    if await is_admin_user(user_id):
        return "admin"
    if user_id and await is_supplier_user(user_id):
        return "supplier"
    return "buyer"


def get_business_id(message: Message | None, fallback: str | None = None) -> str | None:
    if message is None:
        return fallback or ADMIN_BUSINESS_CONNECTION_ID

    return (
        getattr(message, "business_connection_id", None)
        or fallback
        or ADMIN_BUSINESS_CONNECTION_ID
    )


def remember_business_context(chat_id: int | None, business_connection_id: str | None) -> None:
    if chat_id and business_connection_id:
        BUSINESS_CONTEXT_BY_CHAT[chat_id] = business_connection_id


def get_callback_business_id(callback: CallbackQuery | None) -> str | None:
    if callback is None:
        return None

    message = getattr(callback, "message", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)

    return (
        getattr(callback, "business_connection_id", None)
        or getattr(message, "business_connection_id", None)
        or BUSINESS_CONTEXT_BY_CHAT.get(chat_id)
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
    Как у админа: callback редактирует текущее inline-сообщение.
    Важно: если Telegram отвечает "message is not modified", НЕ отправляем новое сообщение.
    """
    if not callback.message:
        logger.warning("UPDATE_OR_SEND_NO_MESSAGE data=%s has_keyboard=%s", callback.data, reply_markup is not None)
        return

    data = callback.data or ""
    chat_id = callback.message.chat.id

    if data.startswith("supplier:"):
        business_id = get_callback_business_id(callback)
        await send_supplier_role_panel(callback.bot, chat_id, text, reply_markup=reply_markup, business_connection_id=business_id, callback=callback)
        return

    if data.startswith("buyer:"):
        business_id = get_callback_business_id(callback)
        await send_buyer_role_panel(callback.bot, chat_id, text, reply_markup=reply_markup, business_connection_id=business_id, callback=callback)
        return

    # Админскую панель оставляем в старом стиле, но без спама на "message is not modified".
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        logger.info(
            "UPDATE_OR_SEND_EDIT_OK chat_id=%s message_id=%s data=%s has_keyboard=%s",
            callback.message.chat.id,
            callback.message.message_id,
            data,
            reply_markup is not None,
        )
    except Exception as exc:
        if _is_message_not_modified_error(exc):
            logger.info("UPDATE_OR_SEND_NOT_MODIFIED chat_id=%s data=%s", callback.message.chat.id, data)
            return
        logger.info(
            "UPDATE_OR_SEND_EDIT_FAILED_SEND_NEW chat_id=%s message_id=%s data=%s has_keyboard=%s error=%s",
            callback.message.chat.id,
            callback.message.message_id,
            data,
            reply_markup is not None,
            exc,
        )
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
        except Exception as send_exc:
            logger.exception("UPDATE_OR_SEND_NEW_FAILED chat_id=%s data=%s error=%s", callback.message.chat.id, data, send_exc)


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
    if not SUPPLIER_IMMUNITY_SKIP_AUTODELETE:
                    await maybe_delete_message(bot, message, delay=5)


async def send_buyer_menu(
    bot: Bot,
    chat_id: int,
    text: str = "Меню покупателя",
    business_connection_id: str | None = None,
):
    """Динамическая inline-панель покупателя без спама новыми сообщениями."""
    return await send_buyer_role_panel(
        bot,
        chat_id,
        text,
        reply_markup=buyer_inline_menu_keyboard(),
        business_connection_id=business_connection_id,
    )


async def send_supplier_menu(
    bot: Bot,
    chat_id: int,
    text: str = "Меню поставщика",
    business_connection_id: str | None = None,
):
    """Динамическая inline-панель поставщика без спама новыми сообщениями."""
    return await send_supplier_role_panel(
        bot,
        chat_id,
        text,
        reply_markup=supplier_inline_menu_keyboard(),
        business_connection_id=business_connection_id,
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



async def notify_bug_report_receivers(bot: Bot, text: str) -> None:
    sent_to: set[int] = set()
    for admin_id in ADMIN_IDS:
        sent_to.add(admin_id)
        await safe_send_message(bot, admin_id, text)
    for chat_id in BUG_REPORT_CHAT_IDS:
        if chat_id not in sent_to:
            sent_to.add(chat_id)
            await safe_send_message(bot, chat_id, text)
    if ADMIN_ALERT_CHAT_ID and ADMIN_ALERT_CHAT_ID not in sent_to:
        await safe_send_message(bot, ADMIN_ALERT_CHAT_ID, text)


async def process_bug_report_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user:
        return False

    text = (message.text or "").strip()
    if not (text == "/bug" or text.startswith("/bug ") or text.startswith("/report ")):
        return False

    payload = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
    if not payload:
        async with SessionLocal() as session:
            hint = await get_text(
                session,
                "bug_report_hint",
                "Опишите проблему так: /bug что случилось, на каком шаге, номер заказа если есть.",
            )
        await answer_message(bot, message, hint, business_connection_id)
        return True

    role = await get_user_role(message.from_user.id)
    async with SessionLocal() as session:
        report = await create_bug_report(
            session,
            message.from_user.id,
            message.from_user.username,
            role,
            payload,
        )

    report_text = (
        "🐞 BUG REPORT\n\n"
        f"ID отчёта: {report.id}\n"
        f"Роль: {role}\n"
        f"От: {message.from_user.id} | @{message.from_user.username or 'нет'}\n"
        f"Business: {business_connection_id or 'нет'}\n"
        f"Chat ID: {message.chat.id}\n\n"
        f"Текст:\n{payload}"
    )
    await notify_bug_report_receivers(bot, report_text)
    await answer_message(
        bot,
        message,
        f"OK. Баг-репорт #{report.id} отправлен админам.",
        business_connection_id,
    )
    return True


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
        async with SessionLocal() as session:
            welcome_text = await get_text(
                session,
                "welcome_start",
                "Здравствуйте. Чтобы открыть меню и связать заказы, нажмите или отправьте команду /start.",
            )
        await temp_answer(bot, message, welcome_text, business_connection_id)
        return

    async with SessionLocal() as session:
        order_not_found_text = await get_text(
            session,
            "order_not_found",
            "Заказ не найден.\n\nЕсли вы уже оплатили, напишите админу.",
        )

    await temp_answer(bot, message, order_not_found_text, business_connection_id)


async def process_admin_pending_input(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user or not await is_admin_user(message.from_user.id):
        return False

    admin_id = message.from_user.id
    text = (message.text or "").strip()

    if admin_id in ADMIN_ADD_ADMIN_WAIT:
        if text.lower() in {"отмена", "cancel", "/cancel"}:
            ADMIN_ADD_ADMIN_WAIT.discard(admin_id)
            await temp_answer(bot, message, "Добавление админа отменено.", business_connection_id, reply_markup=admin_admins_keyboard())
            return True

        parts = text.split(maxsplit=1)
        if not parts:
            await temp_answer(
                bot,
                message,
                "Пришлите Telegram ID и имя. Пример:\n123456789 Иван",
                business_connection_id,
                reply_markup=admin_add_admin_cancel_keyboard(),
            )
            return True
        try:
            new_admin_id = int(parts[0])
        except ValueError:
            await temp_answer(
                bot,
                message,
                "Telegram ID должен быть числом. Пример:\n123456789 Иван",
                business_connection_id,
                reply_markup=admin_add_admin_cancel_keyboard(),
            )
            return True

        name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else f"admin_{new_admin_id}"
        async with SessionLocal() as session:
            admin = await add_admin_user(session, new_admin_id, name, added_by=admin_id)
            admins_text = await list_admin_users_text(session, ADMIN_IDS)

        ADMIN_ADD_ADMIN_WAIT.discard(admin_id)
        await temp_answer(
            bot,
            message,
            f"✅ Доп.админ добавлен.\n\nID: {admin.telegram_id}\nИмя: {admin.name}\n\n{admins_text}",
            business_connection_id,
            reply_markup=admin_admins_keyboard(),
        )
        await safe_send_message(bot, new_admin_id, "Вы назначены дополнительным админом. Откройте /admin")
        return True

    key = ADMIN_TEXT_EDIT_WAIT.get(admin_id)
    if not key:
        return False

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




async def process_shop_admin_pending_input(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user:
        return False
    state = SHOP_ADMIN_WAIT.get(message.from_user.id)
    if not state:
        return False
    action, object_id = state
    text = (message.text or "").strip()
    if text.lower() in {"отмена", "/cancel", "cancel"}:
        SHOP_ADMIN_WAIT.pop(message.from_user.id, None)
        await answer_message(bot, message, "Действие отменено.", business_connection_id, reply_markup=admin_shop_keyboard())
        return True
    try:
        async with SessionLocal() as session:
            if action == "add_category":
                row = await create_category(session, text)
                result = f"✅ Категория «{row.name}» добавлена."
            elif action in {"add_product", "add_product_to"}:
                row = await create_product(session, text, object_id)
                result = f"✅ Товар «{row.name}» сохранён."
            elif action == "category_name":
                row = await session.get(ShopCategory, object_id)
                if not row: raise ValueError("Категория не найдена")
                row.name = text[:120]
                await session.commit()
                result = "✅ Название категории обновлено."
            elif action == "product_name":
                row = await session.get(ShopProduct, object_id)
                if not row: raise ValueError("Товар не найден")
                row.name = text[:255]
                await session.commit()
                result = "✅ Название товара обновлено."
            elif action == "product_desc":
                row = await session.get(ShopProduct, object_id)
                if not row: raise ValueError("Товар не найден")
                row.description = text
                await session.commit()
                result = "✅ Описание товара обновлено."
            elif action == "product_price":
                row = await session.get(ShopProduct, object_id)
                if not row: raise ValueError("Товар не найден")
                parts = text.split()
                row.price = Decimal(parts[0].replace(",", "."))
                if len(parts) > 1: row.currency = parts[1].upper()
                await session.commit()
                result = "✅ Цена товара обновлена."
            elif action == "product_supplier":
                row = await session.get(ShopProduct, object_id)
                if not row: raise ValueError("Товар не найден")
                supplier_id = int(text)
                await bind_product_provider(
                    session, row.admaker_product_id, row.name,
                    "supplier", str(supplier_id),
                )
                result = f"✅ Назначен поставщик {supplier_id}."
            else:
                raise ValueError("Неизвестное действие")
    except Exception as exc:
        await answer_message(
            bot, message,
            f"❌ Не удалось сохранить: {exc}\\n\\nОтправьте данные ещё раз или напишите Отмена.",
            business_connection_id,
        )
        return True
    SHOP_ADMIN_WAIT.pop(message.from_user.id, None)
    await answer_message(bot, message, result, business_connection_id, reply_markup=admin_shop_keyboard())
    return True

async def process_admin_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user or not await is_admin_user(message.from_user.id):
        return False

    text = (message.text or "").strip()
    parts = text.split()

    if text in {"/admin", "/panel", "/menu"}:
        await answer_message(bot, message, admin_panel_text(), business_connection_id, reply_markup=admin_panel_keyboard())
        return True

    if text == "/admins":
        async with SessionLocal() as session:
            result = await list_admin_users_text(session, ADMIN_IDS)
        await answer_message(bot, message, result, business_connection_id, reply_markup=admin_admins_keyboard())
        return True

    if text.startswith("/add_admin"):
        if not is_admin(message.from_user.id):
            await answer_message(bot, message, "Только главный админ из ADMIN_IDS может добавлять доп.админов.", business_connection_id)
            return True
        if len(parts) < 2:
            await answer_message(bot, message, "Формат:\n/add_admin TELEGRAM_ID Имя", business_connection_id)
            return True
        try:
            admin_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True
        name = " ".join(parts[2:]).strip() or f"admin_{admin_id}"
        async with SessionLocal() as session:
            admin = await add_admin_user(session, admin_id, name, added_by=message.from_user.id)
        await answer_message(bot, message, f"OK. Доп.админ добавлен.\nID: {admin.telegram_id}\nИмя: {admin.name}", business_connection_id)
        await safe_send_message(bot, admin_id, "Вы назначены дополнительным админом. Откройте /admin")
        return True

    if text.startswith("/remove_admin"):
        if not is_admin(message.from_user.id):
            await answer_message(bot, message, "Только главный админ из ADMIN_IDS может выключать доп.админов.", business_connection_id)
            return True
        if len(parts) != 2:
            await answer_message(bot, message, "Формат:\n/remove_admin TELEGRAM_ID", business_connection_id)
            return True
        try:
            admin_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True
        async with SessionLocal() as session:
            ok = await remove_admin_user(session, admin_id)
        await answer_message(bot, message, "OK. Доп.админ выключен." if ok else "Доп.админ не найден.", business_connection_id)
        return True

    if text == "/product_providers":
        async with SessionLocal() as session:
            rows = await list_product_providers(session)
        if not rows:
            result = "🔗 › Поставщики товаров\n\nПривязок пока нет."
        else:
            lines = ["🔗 › Поставщики товаров", ""]
            for row in rows:
                state = "✅" if row.enabled else "⛔"
                lines.append(f"{state} {row.admaker_product_id} — {row.product_name or 'Товар'} — {row.provider_type}:{row.provider_key or '-'}")
            result = "\n".join(lines)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text == "/admaker_products":
        async with SessionLocal() as session:
            rows = await list_recent_admaker_products(session)
        result = "📦 › Товары Admaker\n\n" + ("\n".join(f"{pid} — {name}" for pid, name in rows) if rows else "Сначала должен прийти хотя бы один оплаченный заказ.")
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/bind_proxyline"):
        if len(parts) != 2:
            await answer_message(bot, message, "Формат: /bind_proxyline PRODUCT_ID", business_connection_id)
            return True
        try:
            product_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "PRODUCT_ID должен быть числом.", business_connection_id)
            return True
        async with SessionLocal() as session:
            recent = dict(await list_recent_admaker_products(session, 100))
            row = await bind_product_provider(session, product_id, "proxyline", "proxyline", recent.get(product_id))
        await answer_message(bot, message, f"✅ Товар {row.admaker_product_id} привязан к Proxyline.", business_connection_id)
        return True

    if text.startswith("/bind_product_supplier"):
        if len(parts) != 3:
            await answer_message(bot, message, "Формат: /bind_product_supplier PRODUCT_ID SUPPLIER_TELEGRAM_ID", business_connection_id)
            return True
        try:
            product_id, supplier_id = int(parts[1]), int(parts[2])
        except ValueError:
            await answer_message(bot, message, "ID должны быть числами.", business_connection_id)
            return True
        async with SessionLocal() as session:
            recent = dict(await list_recent_admaker_products(session, 100))
            row = await bind_product_provider(session, product_id, "supplier", str(supplier_id), recent.get(product_id))
        await answer_message(bot, message, f"✅ Товар {row.admaker_product_id} привязан к поставщику {supplier_id}.", business_connection_id)
        return True

    if text.startswith("/unbind_product"):
        if len(parts) != 2:
            await answer_message(bot, message, "Формат: /unbind_product PRODUCT_ID", business_connection_id)
            return True
        try:
            product_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "PRODUCT_ID должен быть числом.", business_connection_id)
            return True
        async with SessionLocal() as session:
            ok = await unbind_product_provider(session, product_id)
        await answer_message(bot, message, "✅ Привязка отключена." if ok else "Привязка не найдена.", business_connection_id)
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

    await send_supplier_role_panel(bot, message.chat.id, text, reply_markup=markup, business_connection_id=business_connection_id)


async def process_supplier_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user:
        return False
    if not await is_supplier_user(message.from_user.id):
        return False

    text = (message.text or "").strip()

    if text in {"/commands", "📖 Команды"}:
        await send_supplier_role_panel(bot, message.chat.id, supplier_commands_text(), reply_markup=supplier_commands_keyboard(), business_connection_id=business_connection_id)
        return True

    if text in {"/start", "/supplier"} or text == "🚚 Панель поставщика":
        await send_supplier_role_panel(bot, message.chat.id, supplier_main_panel_text(), reply_markup=supplier_inline_menu_keyboard(), business_connection_id=business_connection_id)
        return True

    if text in {"/work", "/pending"} or text in SUPPLIER_PANEL_TEXT_BUTTONS:
        await send_supplier_pending_panel(bot, message, business_connection_id)
        return True

    if text == "/profile" or text == "👤 Мой профиль":
        async with SessionLocal() as session:
            profile_text = await supplier_profile_text(session, message.from_user.id, message.from_user.username)
        await send_supplier_role_panel(bot, message.chat.id, profile_text, reply_markup=supplier_inline_menu_keyboard(), business_connection_id=business_connection_id)
        return True

    # ВАЖНО: неизвестные команды поставщика не должны попадать в обработчик номера/кода.
    # Иначе бот может отвечать «Не смог найти номер» или «Ожидающих заявок нет» на любую команду.
    if is_supplier_command_like_text(text):
        await send_supplier_unknown_command(bot, message, business_connection_id, text)
        return True

    return False



async def process_main_reply_button(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    """
    Обрабатывает кнопки обычной клавиатуры главного меню.

    Возвращает True, если сообщение было кнопкой меню.
    """
    if not message.from_user:
        return False

    text = (message.text or "").strip()
    user_id = message.from_user.id
    admin_access = await is_admin_user(user_id)

    if text == "🛒 Товары":
        async with SessionLocal() as session:
            await sync_products_from_orders(session)
            categories = await list_categories(session)

        await answer_message(
            bot,
            message,
            customer_home_text(),
            business_connection_id,
            reply_markup=customer_home_keyboard(
                categories,
                is_admin=admin_access,
            ),
        )
        return True

    if text == "👥 Партнерская программа":
        await answer_message(
            bot,
            message,
            "👥 Партнерская программа\n\n"
            "Раздел находится в разработке.",
            business_connection_id,
            reply_markup=buyer_main_reply_keyboard(is_admin=admin_access),
        )
        return True

    if text == "✉️ Обратная связь":
        await answer_message(
            bot,
            message,
            "✉️ Обратная связь\n\n"
            "Опишите проблему или предложение командой:\n"
            "/bug ваш текст\n\n"
            "Сообщение получат администраторы магазина.",
            business_connection_id,
            reply_markup=buyer_main_reply_keyboard(is_admin=admin_access),
        )
        return True

    if text == "📕 FAQ":
        await answer_message(
            bot,
            message,
            "📕 FAQ\n\n"
            "├ Как купить — нажмите «🛒 Товары»\n"
            "├ Как посмотреть заказ — откройте меню заказов\n"
            "├ Где получить прокси — в обычном чате с ботом\n"
            "└ Как сообщить об ошибке — /bug описание",
            business_connection_id,
            reply_markup=buyer_main_reply_keyboard(is_admin=admin_access),
        )
        return True

    if text == "⚙️ Админ меню":
        if not admin_access:
            # Даже если пользователь вручную отправит текст кнопки,
            # доступ к панели он не получит.
            await answer_message(
                bot,
                message,
                "У вас нет доступа к админ-панели.",
                business_connection_id,
                reply_markup=buyer_main_reply_keyboard(is_admin=False),
            )
            return True

        await answer_message(
            bot,
            message,
            admin_panel_text(),
            business_connection_id,
            reply_markup=admin_panel_keyboard(),
        )
        return True

    return False


async def process_command_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    text = (message.text or "").strip()
    user_id = message.from_user.id
    username = message.from_user.username

    if await process_bug_report_command(bot, message, business_connection_id):
        return

    if await process_admin_command(bot, message, business_connection_id):
        return

    if await process_supplier_command(bot, message, business_connection_id):
        return

    if text == "/shop":
        async with SessionLocal() as session:
            await sync_products_from_orders(session)
            categories = await list_categories(session)
        admin_access = await is_admin_user(user_id)
        await answer_message(
            bot,
            message,
            customer_home_text(),
            business_connection_id,
            reply_markup=customer_home_keyboard(
                categories,
                is_admin=admin_access,
            ),
        )
        return

    if text.startswith(("/shop_sync", "/shop_categories", "/shop_add_category", "/shop_set_product", "/shop_set_price", "/shop_toggle")):
        if not await is_admin_user(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        async with SessionLocal() as session:
            result = await process_admin_shop_command(session, text)
        await answer_message(bot, message, result or "Неизвестная команда магазина.", business_connection_id)
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

        admin_access = await is_admin_user(user_id)
        await answer_message(
            bot,
            message,
            "🛍 Магазин\n\n"
            "Используйте кнопки под полем ввода, чтобы открыть нужный раздел.",
            business_connection_id,
            reply_markup=buyer_main_reply_keyboard(is_admin=admin_access),
        )
        return

    if text == "👤 Мой профиль" or text == "/profile":
        if await is_admin_user(user_id):
            async with SessionLocal() as session:
                profile_text = await admin_profile_text(session, user_id, username)
            await answer_message(bot, message, profile_text, business_connection_id, reply_markup=admin_profile_keyboard())
            return

        if await is_supplier_user(user_id):
            async with SessionLocal() as session:
                profile_text = await supplier_profile_text(session, user_id, username)
            await send_supplier_role_panel(bot, message.chat.id, profile_text, reply_markup=supplier_inline_menu_keyboard(), business_connection_id=business_connection_id)
            return

        async with SessionLocal() as session:
            profile_text = await buyer_profile_text(session, user_id, username)
        await send_buyer_role_panel(bot, message.chat.id, profile_text, reply_markup=buyer_inline_menu_keyboard(), business_connection_id=business_connection_id)
        return

    if text == "📦 Мои заказы" or text == "/orders":
        async with SessionLocal() as session:
            orders_text = await buyer_orders_text(session, user_id, username, BUYER_ORDERS_LIMIT)
        await send_buyer_role_panel(bot, message.chat.id, orders_text, reply_markup=buyer_back_keyboard(), business_connection_id=business_connection_id)
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
        if not await is_admin_user(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        async with SessionLocal() as session:
            status_text = await get_status_text(session)
        await answer_message(bot, message, status_text, business_connection_id)
        return

    if text == "/last_orders":
        if not await is_admin_user(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        async with SessionLocal() as session:
            last_orders = await get_last_orders_text(session)
        await answer_message(bot, message, last_orders, business_connection_id)
        return

    if text.startswith("/set_customer"):
        if not await is_admin_user(user_id):
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


async def proxy_settings_text(session) -> tuple[str, object]:
    settings = await get_proxy_shop_settings(session)
    countries = ", ".join(country_label(x) for x in settings.countries)
    periods = ", ".join(f"{x} дней" for x in settings.periods)
    proxy_type = "Выделенные" if settings.proxy_type == "dedicated" else "Общие"
    text = (
        "🌐 › Настройки прокси\n\n"
        "Здесь настраивается автоматическая выдача Proxyline покупателям.\n\n"
        f"Автовыдача: {'включена' if settings.enabled else 'выключена'}\n"
        f"├ Страны — {countries}\n"
        f"├ Сроки — {periods}\n"
        f"├ Тип — {proxy_type}\n"
        f"├ Количество — {settings.count}\n"
        f"└ Версия IP — IPv{settings.ip_version}"
    )
    return text, settings


async def show_proxy_country_selection(bot: Bot, order_id: int, business_connection_id: str | None = None) -> bool:
    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        settings = await get_proxy_shop_settings(session)
        if not order or not settings.enabled:
            return False
        # Proxyline работает только в обычном чате с ботом.
        # Telegram ID покупателя одновременно является chat_id после /start.
        target_chat_id = order.customer_telegram_id or order.buyer_chat_id
        order.buyer_chat_id = target_chat_id
        order.business_connection_id = None
        order.status = "waiting_proxy_country"
        order.service_name = selection_dump()
        order.updated_at = datetime.utcnow()
        await session.commit()
    if not target_chat_id:
        return False
    return await send_buyer_role_panel(
        bot,
        target_chat_id,
        "🌍 › Выбор страны\n\nВыберите страну, в которой должен находиться прокси.",
        business_connection_id=None,
        reply_markup=buyer_proxy_country_keyboard(order_id, settings.countries, SUPPORTED_COUNTRIES),
    )


async def show_proxy_period_selection(callback: CallbackQuery, order_id: int) -> None:
    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        settings = await get_proxy_shop_settings(session)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        country, _ = selection_load(order.service_name)
        if not country:
            order.status = "waiting_proxy_country"
            await session.commit()
            await update_or_send(callback, "Сначала выберите страну.", reply_markup=buyer_proxy_country_keyboard(order_id, settings.countries, SUPPORTED_COUNTRIES))
            await callback.answer()
            return
        order.status = "waiting_proxy_period"
        await session.commit()
    await update_or_send(
        callback,
        f"📅 › Выбор срока\n\nСтрана: {country_label(country)}\n\nВыберите срок аренды прокси.",
        reply_markup=buyer_proxy_period_keyboard(order_id, settings.periods),
    )
    await callback.answer()


async def process_proxyline_order(bot: Bot, order_id: int, business_connection_id: str | None = None) -> bool:
    """
    Автоматическая выдача Proxyline без поставщика.

    Поток:
    Admaker paid -> Order -> Proxyline API -> buyer -> status=code_sent_to_customer.
    Заказ НЕ закрывается сразу: покупатель должен нажать «OK, всё успешно».
    """
    if not PROXYLINE_ENABLED:
        return False

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            await notify_admins(bot, f"Proxyline: заказ {order_id} не найден.")
            return False

        base_cfg = resolve_proxyline_product(order.product_name)
        if not base_cfg:
            return False
        settings = await get_proxy_shop_settings(session)
        selected_country, selected_period = selection_load(order.service_name)
        if not selected_country or not selected_period:
            return False
        if selected_country not in settings.countries or selected_period not in settings.periods:
            order.status = "problem"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await notify_admins(bot, f"Proxyline: выбранные параметры больше недоступны для заказа #{order.operation_id}.")
            return False
        product_cfg = ProxylineProduct(
            country=selected_country,
            period=selected_period,
            count=settings.count,
            ip_version=settings.ip_version,
            proxy_type=settings.proxy_type,
            coupon=base_cfg.coupon,
        )

        if order.verification_code and order.status in {"code_sent_to_customer", "confirmed"}:
            logger.info("PROXYLINE_SKIP_ALREADY_DELIVERED order_id=%s status=%s", order.id, order.status)
            return True

        if not order.customer_telegram_id and not order.buyer_chat_id:
            order.status = "problem"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await notify_admins(bot, f"Proxyline: нет buyer_chat_id/customer_telegram_id для заказа #{order.operation_id}.")
            return False

        # Proxyline выдаётся только в обычном чате с ботом.
        target_chat_id = order.customer_telegram_id or order.buyer_chat_id
        order.buyer_chat_id = target_chat_id
        order.business_connection_id = None
        await session.commit()

        order_operation_id = order.operation_id
        order_product_name = order.product_name
        target_business_id = None

    if not PROXYLINE_API_KEY:
        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if order:
                order.status = "problem"
                order.updated_at = datetime.utcnow()
                await session.commit()
        await notify_admins(
            bot,
            "Proxyline API не настроен. Добавь PROXYLINE_API_KEY и PROXYLINE_ENABLED=1 в Render Environment.\n\n"
            f"Заказ: #{order_operation_id}\nТовар: {order_product_name}",
        )
        return False

    try:
        if PROXYLINE_COUPON and not product_cfg.coupon:
            # dataclass frozen, поэтому создаём новый объект с купоном.
            from dataclasses import replace
            product_cfg = replace(product_cfg, coupon=PROXYLINE_COUPON)

        service = ProxylineService(PROXYLINE_API_KEY)
        available = await service.ips_count(product_cfg)
        if available < product_cfg.count:
            raise ProxylineError(
                f"Недостаточно IP: доступно {available}, нужно {product_cfg.count}. "
                f"country={product_cfg.country}, type={product_cfg.proxy_type}, ipv{product_cfg.ip_version}"
            )
        payload = await service.buy_proxy(product_cfg)
        proxy_text = format_proxyline_result(payload)
    except Exception as exc:
        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if order:
                order.status = "problem"
                order.updated_at = datetime.utcnow()
                await session.commit()
        await notify_admins(
            bot,
            "Proxyline: ошибка автоматической покупки.\n\n"
            f"Заказ: #{order_operation_id}\n"
            f"Товар: {order_product_name}\n"
            f"Ошибка: {exc}",
        )
        logger.exception("PROXYLINE_DELIVERY_FAILED order_id=%s", order_id)
        return False

    delivery_text = (
        "✅ › Ваш прокси готов\n\n"
        "Данные для подключения:\n"
        f"{proxy_text}\n\n"
        "Проверьте прокси и подтвердите результат кнопкой ниже."
    )

    ok = False
    if target_chat_id:
        ok = await send_buyer_role_panel(
            bot,
            target_chat_id,
            delivery_text,
            business_connection_id=target_business_id,
            reply_markup=confirm_keyboard(order_id),
        )

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            return False
        order.verification_code = proxy_text
        order.status = "code_sent_to_customer" if ok else "problem"
        order.updated_at = datetime.utcnow()
        await session.commit()

    if ok:
        await notify_admins(
            bot,
            "✅ Proxyline заказ выдан автоматически.\n\n"
            f"Заказ: #{order_operation_id}\n"
            f"Товар: {order_product_name}\n"
            f"Покупатель: {target_chat_id}",
        )
        logger.info("PROXYLINE_DELIVERY_OK order_id=%s operation_id=%s", order_id, order_operation_id)
        return True

    await notify_admins(
        bot,
        "Proxyline купил прокси, но не смог отправить покупателю.\n\n"
        f"Заказ: #{order_operation_id}\n"
        f"Товар: {order_product_name}\n"
        f"Покупатель: {target_chat_id}\n"
        f"Business ID: {target_business_id}\n\n"
        f"Прокси:\n{proxy_text}",
    )
    return False


async def process_admaker_message(bot: Bot, message: Message) -> None:
    text = message.text or ""
    data = extract_purchase_data(text)

    if not data:
        await notify_admins(bot, f"Shop-бот прислал сообщение, но покупку распарсить не удалось.\n\nТекст:\n{text}")
        return

    current_business_id = get_business_id(message)

    async with SessionLocal() as session:
        order = await create_or_update_order_from_purchase(session, data)
        if current_business_id and not order.business_connection_id:
            order.business_connection_id = current_business_id
            await session.commit()
            await session.refresh(order)

    async with SessionLocal() as session:
        explicit_provider = await get_product_provider(session, order.product_id)
        settings = await get_proxy_shop_settings(session)

    # Основной маршрут — только явная привязка по Admaker product_id.
    # Legacy-проверка по названию оставлена временно для обратной совместимости.
    route_to_proxyline = bool(
        explicit_provider and explicit_provider.enabled and explicit_provider.provider_type == "proxyline"
    )
    legacy_proxyline = explicit_provider is None and is_proxyline_product(order.product_name)

    if PROXYLINE_ENABLED and (route_to_proxyline or legacy_proxyline):
        async with SessionLocal() as session:
            db_order = await get_order_by_id(session, order.id)
            settings = await get_proxy_shop_settings(session)
            if db_order:
                db_order.status = "waiting_proxy_country" if settings.enabled else "problem"
                db_order.service_name = selection_dump()
                # Proxyline flow is strictly in the normal bot chat.
                db_order.buyer_chat_id = db_order.customer_telegram_id or db_order.buyer_chat_id
                db_order.business_connection_id = None
                db_order.updated_at = datetime.utcnow()
                await session.commit()
        await notify_admins(
            bot,
            ("OK. Покупка Proxyline обработана. Покупателю предложен выбор страны и срока.\n\n"
             if settings.enabled else "Proxyline-магазин отключён в админ-панели. Заказ переведён в problem.\n\n")
            + f"Заказ: #{order.operation_id}\n"
            + f"ID в базе: {order.id}\n"
            + f"Покупатель ID: {order.customer_telegram_id}\n"
            + f"Товар: {order.product_name}",
        )
        if settings.enabled:
            sent = await show_proxy_country_selection(bot, order.id, None)
            if not sent:
                await notify_admins(
                    bot,
                    "⚠️ Proxyline: не удалось открыть выбор в обычном боте.\n\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"Покупатель ID: {order.customer_telegram_id}\n\n"
                    "Покупатель должен открыть обычный чат с ботом и нажать /start. "
                    "Заказ сохранён и продолжится после /start.",
                )
        return

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

    ok = await safe_send_message(
        bot,
        supplier.telegram_id,
        supplier_text,
        actual_business_id,
        reply_markup=supplier_inline_menu_keyboard(),
        allow_normal_fallback=False if actual_business_id else True,
    )
    # Если есть business_connection_id, НЕ падаем в обычный бот-чат,
    # иначе уведомления поставщика начинают приходить в бота, а не в Business-чат.
    if not ok and not actual_business_id:
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
        allow_normal_fallback=False if actual_business_id else True,
    )
    # Если есть business_connection_id, НЕ отправляем fallback в обычный бот-чат.
    if not sent_with_buttons and not actual_business_id:
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
        active_order = await find_active_order_for_customer(session, user_id, username)
        if active_order and active_order.status.startswith("waiting_proxy"):
            # Выбор и выдача Proxyline выполняются только в обычном чате с ботом.
            if business_connection_id:
                settings = None
                status = "proxy_business_redirect"
                order_id = active_order.id
                country, period = selection_load(active_order.service_name)
            else:
                active_order.buyer_chat_id = message.chat.id
                active_order.customer_telegram_id = user_id
                active_order.business_connection_id = None
                await session.commit()
                settings = await get_proxy_shop_settings(session)
                status = active_order.status
                order_id = active_order.id
                country, period = selection_load(active_order.service_name)
        else:
            status = None
            order_id = None
            country = None
            period = None
            settings = None

    if order_id and status == "proxy_business_redirect":
        try:
            me = await bot.get_me()
            bot_link = f"@{me.username}" if me.username else "обычный чат с ботом"
        except Exception:
            bot_link = "обычный чат с ботом"
        await temp_answer(
            bot,
            message,
            "🌐 › Выдача прокси\n\n"
            f"Страну, срок и получение прокси нужно выполнить в {bot_link}.\n"
            "Откройте бота и нажмите /start.",
            business_connection_id,
        )
        return

    if order_id and status == "waiting_proxy_country":
        await send_buyer_role_panel(bot, message.chat.id, "🌍 › Выбор страны\n\nВыберите страну, в которой должен находиться прокси.", business_connection_id=business_connection_id, reply_markup=buyer_proxy_country_keyboard(order_id, settings.countries, SUPPORTED_COUNTRIES))
        return
    if order_id and status == "waiting_proxy_period":
        await send_buyer_role_panel(bot, message.chat.id, f"📅 › Выбор срока\n\nСтрана: {country_label(country or settings.countries[0])}\n\nВыберите срок аренды прокси.", business_connection_id=business_connection_id, reply_markup=buyer_proxy_period_keyboard(order_id, settings.periods))
        return
    if order_id and status == "waiting_proxy_confirm":
        await send_buyer_role_panel(bot, message.chat.id, f"✅ › Подтверждение прокси\n\nСтрана: {country_label(country or '')}\nСрок: {period or '?'} дней", business_connection_id=business_connection_id, reply_markup=buyer_proxy_confirm_keyboard(order_id))
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

            # Сохраняем номер, но статус меняем только после реальной доставки.
            order.phone_number = phone
            order.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id

            ok = False
            if target_chat_id and target_business_id:
                ok = bool(await safe_send_message(
                    bot,
                    target_chat_id,
                    phone,
                    business_connection_id=target_business_id,
                    reply_markup=number_keyboard(order.id),
                    allow_normal_fallback=False,
                ))

            if not ok and order.customer_telegram_id:
                normal_sent = await safe_send_message(
                    bot,
                    order.customer_telegram_id,
                    phone,
                    business_connection_id=None,
                    reply_markup=number_keyboard(order.id),
                    allow_normal_fallback=True,
                )
                ok = bool(normal_sent)

            if not ok:
                order.status = "waiting_supplier_number"
                order.updated_at = datetime.utcnow()
                await session.commit()
                await answer_message(
                    bot, message,
                    "Номер сохранён, но Telegram не доставил его покупателю. "
                    "Заявка оставлена в разделе «Ждут номер» — попробуйте повторно.",
                    business_connection_id,
                )
                await notify_admins(
                    bot,
                    "⚠️ Не удалось доставить номер покупателю.\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"buyer_chat_id: {order.buyer_chat_id}\n"
                    f"customer_telegram_id: {order.customer_telegram_id}\n"
                    f"buyer_business_connection_id: {target_business_id or 'нет'}",
                )
                logger.error(
                    "BUYER_NUMBER_DELIVERY_FAILED order_id=%s buyer_chat_id=%s customer_id=%s business_id=%s",
                    order.id, order.buyer_chat_id, order.customer_telegram_id, target_business_id,
                )
                return

            order.status = "number_sent_to_customer"
            order.updated_at = datetime.utcnow()
            number_request.status = "answered"
            number_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)
            logger.info(
                "BUYER_NUMBER_DELIVERY_OK order_id=%s buyer_chat_id=%s",
                order.id, target_chat_id,
            )

            sent = await send_supplier_role_panel(bot, message.chat.id, "OK. Номер отправлен покупателю.", reply_markup=supplier_inline_menu_keyboard(), business_connection_id=business_connection_id)
            try:
                await maybe_delete_sent(bot, sent)
                if not SUPPLIER_IMMUNITY_SKIP_AUTODELETE:
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

            # Сохраняем код, но НЕ меняем статус заявки до подтверждённой доставки.
            # Раньше статус code_sent_to_customer выставлялся заранее, поэтому при ошибке
            # Telegram заявка исчезала у поставщика, хотя покупатель ничего не получил.
            order.verification_code = code
            order.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            # Используем только Business-соединение покупателя. Нельзя подставлять
            # соединение текущего поставщика — это может направить сообщение не туда.
            target_business_id = order.business_connection_id

            delivery_text = (
                f"🔑 Код по заказу #{order.operation_id}:\n\n"
                f"{code}\n\n"
                "Проверьте код и подтвердите результат кнопкой ниже."
            )

            ok = False
            if target_chat_id and target_business_id:
                ok = bool(await send_buyer_role_panel(
                    bot,
                    target_chat_id,
                    delivery_text,
                    business_connection_id=target_business_id,
                    reply_markup=confirm_keyboard(order.id),
                ))

            # Резервная доставка в обычный чат с ботом. Она сработает только если
            # покупатель ранее нажал /start. Это безопаснее, чем терять код.
            if not ok and order.customer_telegram_id:
                normal_sent = await safe_send_message(
                    bot,
                    order.customer_telegram_id,
                    delivery_text,
                    business_connection_id=None,
                    reply_markup=confirm_keyboard(order.id),
                    allow_normal_fallback=True,
                )
                ok = bool(normal_sent)

            if not ok:
                # Оставляем статус waiting_supplier_code и активный запрос.
                # Поставщик сможет повторить отправку, код при этом сохранён в заказе.
                order.status = "waiting_supplier_code"
                order.updated_at = datetime.utcnow()
                await session.commit()
                await answer_message(
                    bot,
                    message,
                    "Код сохранён, но Telegram не доставил его покупателю. "
                    "Заявка оставлена в разделе «Ждут код» — попробуйте повторно.",
                    business_connection_id,
                )
                await notify_admins(
                    bot,
                    "⚠️ Не удалось доставить код покупателю.\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"buyer_chat_id: {order.buyer_chat_id}\n"
                    f"customer_telegram_id: {order.customer_telegram_id}\n"
                    f"buyer_business_connection_id: {target_business_id or 'нет'}",
                )
                logger.error(
                    "BUYER_CODE_DELIVERY_FAILED order_id=%s buyer_chat_id=%s customer_id=%s business_id=%s",
                    order.id, order.buyer_chat_id, order.customer_telegram_id, target_business_id,
                )
                return

            # Только после фактической доставки меняем статус и закрываем запрос кода.
            order.status = "code_sent_to_customer"
            order.updated_at = datetime.utcnow()
            await mark_code_waiting_buyer_confirm(session, code_request.id)
            await session.commit()
            await session.refresh(order)
            await session.refresh(code_request)
            logger.info(
                "BUYER_CODE_DELIVERY_OK order_id=%s buyer_chat_id=%s normal_fallback=%s",
                order.id, target_chat_id, not bool(target_business_id),
            )

            sent = await send_supplier_role_panel(
                bot,
                message.chat.id,
                (
                    "OK. Код отправлен покупателю.\n\n"
                    f"Заказ #{order.operation_id} теперь ожидает подтверждения покупателя.\n"
                    "Пока покупатель не нажмёт «OK, всё успешно», заявка не считается закрытой."
                ),
                reply_markup=supplier_wait_confirm_keyboard("code", 0),
                business_connection_id=business_connection_id,
            )
            try:
                await maybe_delete_sent(bot, sent)
                if not SUPPLIER_IMMUNITY_SKIP_AUTODELETE:
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

    if is_business and business_connection_id:
        remember_business_context(message.chat.id, business_connection_id)

    if user_id == me.id:
        logger.info("IGNORED: own bot message")
        return

    if await is_admin_user(user_id) and not text.startswith("/"):
        # Сначала обрабатываем ввод, который ожидает админка:
        # ID нового администратора, цену, название товара и т.д.
        if await process_shop_admin_pending_input(bot, message, business_connection_id):
            return
        if await process_admin_pending_input(bot, message, business_connection_id):
            return

        # После этого — обычные кнопки главного меню.
        if await process_main_reply_button(bot, message, business_connection_id):
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

    if await process_main_reply_button(bot, message, business_connection_id):
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
    if not callback.from_user or not await is_admin_user(callback.from_user.id):
        return False

    data = callback.data or ""

    if data == "admin:noop":
        await callback.answer()
        return True

    if data == "admin:shop":
        await update_or_send(callback, admin_shop_text(), reply_markup=admin_shop_keyboard())
        await callback.answer()
        return True

    if data == "admin:shop:sync":
        async with SessionLocal() as session:
            count = await sync_products_from_orders(session)
        await callback.answer(f"Добавлено товаров: {count}", show_alert=True)
        await update_or_send(callback, admin_shop_text(), reply_markup=admin_shop_keyboard())
        return True

    if data == "admin:shop:categories":
        async with SessionLocal() as session:
            rows = await all_categories(session)
        await update_or_send(callback, admin_categories_text(rows), reply_markup=admin_categories_keyboard(rows))
        await callback.answer()
        return True

    if data == "admin:shop:products":
        async with SessionLocal() as session:
            rows = await all_products(session)
        await update_or_send(callback, admin_products_text(rows), reply_markup=admin_products_keyboard(rows))
        await callback.answer()
        return True

    if data == "admin:shop:add_category":
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("add_category", None)
        await callback.answer()
        await update_or_send(callback, "➕ Категория\\n\\nОтправьте название. Можно вместе с эмодзи:\\n📱 Номера\\n\\nДля отмены: Отмена", reply_markup=admin_shop_keyboard())
        return True

    if data == "admin:shop:add_product":
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("add_product", None)
        await callback.answer()
        await update_or_send(callback, "➕ Товар\\n\\nФормат:\\nADMAKER_ID | Название | Цена | Валюта\\n\\nПример:\\n613092 | Прокси IPv4 | 500 | RUB", reply_markup=admin_shop_keyboard())
        return True

    if data.startswith("admin:shop:add_product_to:"):
        category_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("add_product_to", category_id)
        await callback.answer()
        await update_or_send(callback, "➕ Товар в категорию\\n\\nФормат:\\nADMAKER_ID | Название | Цена | Валюта", reply_markup=admin_shop_keyboard())
        return True

    if data.startswith("admin:shop:category:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            category = await session.get(ShopCategory, category_id)
            products = await all_products(session, category_id)
            count, _ = await category_counts(session, category_id)
        if not category:
            await callback.answer("Категория не найдена", show_alert=True)
            return True
        await update_or_send(callback, admin_category_text(category, count), reply_markup=admin_category_keyboard(category, products))
        await callback.answer()
        return True

    if data.startswith("admin:shop:category_toggle:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            category = await toggle_category(session, category_id)
            products = await all_products(session, category_id)
            count, _ = await category_counts(session, category_id)
        await update_or_send(callback, admin_category_text(category, count), reply_markup=admin_category_keyboard(category, products))
        await callback.answer("Статус категории изменён")
        return True

    if data.startswith("admin:shop:category_up:") or data.startswith("admin:shop:category_down:"):
        category_id = int(data.rsplit(":", 1)[1])
        delta = -10 if "category_up" in data else 10
        async with SessionLocal() as session:
            category = await move_category(session, category_id, delta)
            products = await all_products(session, category_id)
            count, _ = await category_counts(session, category_id)
        await update_or_send(callback, admin_category_text(category, count), reply_markup=admin_category_keyboard(category, products))
        await callback.answer("Позиция изменена")
        return True

    if data.startswith("admin:shop:category_delete:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            ok, result = await delete_category(session, category_id)
            rows = await all_categories(session)
        await callback.answer(result, show_alert=not ok)
        await update_or_send(callback, admin_categories_text(rows), reply_markup=admin_categories_keyboard(rows))
        return True

    if data.startswith("admin:shop:category_name:"):
        category_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("category_name", category_id)
        await update_or_send(callback, "📝 Отправьте новое название категории.", reply_markup=admin_shop_keyboard())
        await callback.answer()
        return True

    if data.startswith("admin:shop:category_desc:"):
        await callback.answer("Описание категории будет добавлено после миграции базы.", show_alert=True)
        return True

    if data.startswith("admin:shop:product:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            text = await product_admin_text(session, product) if product else "Товар не найден."
        if not product:
            await callback.answer("Товар не найден", show_alert=True)
            return True
        await update_or_send(callback, text, reply_markup=admin_product_keyboard(product))
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_toggle:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await toggle_product(session, product_id)
            text = await product_admin_text(session, product)
        await update_or_send(callback, text, reply_markup=admin_product_keyboard(product))
        await callback.answer("Статус товара изменён")
        return True

    if data.startswith("admin:shop:product_name:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("product_name", product_id)
        await update_or_send(callback, "📝 Отправьте новое название товара.", reply_markup=admin_shop_keyboard())
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_desc:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("product_desc", product_id)
        await update_or_send(callback, "📝 Отправьте новое описание товара.", reply_markup=admin_shop_keyboard())
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_price:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("product_price", product_id)
        await update_or_send(callback, "💵 Отправьте цену и валюту:\\n500 RUB", reply_markup=admin_shop_keyboard())
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_proxy:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            await bind_product_provider(session, product.admaker_product_id, product.name, "proxyline", "proxyline")
            text = await product_admin_text(session, product)
        await update_or_send(callback, text, reply_markup=admin_product_keyboard(product))
        await callback.answer("Proxyline назначен")
        return True

    if data.startswith("admin:shop:product_supplier:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = ("product_supplier", product_id)
        await update_or_send(callback, "🚚 Отправьте Telegram ID поставщика.", reply_markup=admin_shop_keyboard())
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_unbind:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            await unbind_product_provider(session, product.admaker_product_id)
            text = await product_admin_text(session, product)
        await update_or_send(callback, text, reply_markup=admin_product_keyboard(product))
        await callback.answer("Привязка удалена")
        return True

    if data.startswith("admin:shop:product_delete:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            await delete_product(session, product_id)
            rows = await all_products(session)
        await update_or_send(callback, admin_products_text(rows), reply_markup=admin_products_keyboard(rows))
        await callback.answer("Товар удалён")
        return True

    if data == "admin:proxy":
        async with SessionLocal() as session:
            text, settings = await proxy_settings_text(session)
        await update_or_send(callback, text, reply_markup=admin_proxy_settings_keyboard(settings))
        await callback.answer()
        return True

    if data == "admin:proxy:products":
        async with SessionLocal() as session:
            rows = await list_product_providers(session)
        if rows:
            text = "🔗 › Привязки товаров\n\n" + "\n".join(
                f"{'✅' if row.enabled else '⛔'} {row.admaker_product_id} — {row.product_name or 'Товар'} — {row.provider_type}" for row in rows
            )
        else:
            text = "🔗 › Привязки товаров\n\nПривязок пока нет. Сначала откройте список товаров Admaker."
        await update_or_send(callback, text, reply_markup=admin_proxy_products_keyboard())
        await callback.answer()
        return True

    if data == "admin:proxy:products_help":
        text = (
            "🔗 › Привязка товара\n\n"
            "1. Выполните /admaker_products\n"
            "2. Скопируйте Product ID\n"
            "3. Для Proxyline: /bind_proxyline PRODUCT_ID\n"
            "4. Для поставщика: /bind_product_supplier PRODUCT_ID TELEGRAM_ID\n"
            "5. Отвязать: /unbind_product PRODUCT_ID"
        )
        await update_or_send(callback, text, reply_markup=admin_proxy_products_keyboard())
        await callback.answer()
        return True

    if data == "admin:proxy:toggle":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            await save_proxy_setting(session, "proxy_shop_enabled", "0" if settings.enabled else "1")
            text, settings = await proxy_settings_text(session)
        await update_or_send(callback, text, reply_markup=admin_proxy_settings_keyboard(settings))
        await callback.answer("Настройка обновлена")
        return True

    if data == "admin:proxy:countries":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
        await update_or_send(callback, "🌍 › Доступные страны\n\nОтметьте страны, которые сможет выбирать покупатель.", reply_markup=admin_proxy_countries_keyboard(settings, SUPPORTED_COUNTRIES))
        await callback.answer()
        return True

    if data.startswith("admin:proxy:country:"):
        code = data.rsplit(":", 1)[1]
        if code not in SUPPORTED_COUNTRIES:
            await callback.answer("Неизвестная страна", show_alert=True)
            return True
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            countries = list(settings.countries)
            if code in countries:
                if len(countries) == 1:
                    await callback.answer("Нужно оставить хотя бы одну страну", show_alert=True)
                    return True
                countries.remove(code)
            else:
                countries.append(code)
            await save_proxy_setting(session, "proxy_shop_countries", ",".join(countries))
            settings = await get_proxy_shop_settings(session)
        await update_or_send(callback, "🌍 › Доступные страны\n\nОтметьте страны, которые сможет выбирать покупатель.", reply_markup=admin_proxy_countries_keyboard(settings, SUPPORTED_COUNTRIES))
        await callback.answer("Сохранено")
        return True

    if data == "admin:proxy:periods":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
        await update_or_send(callback, "📅 › Доступные сроки\n\nОтметьте сроки аренды, доступные покупателю.", reply_markup=admin_proxy_periods_keyboard(settings, SUPPORTED_PERIODS))
        await callback.answer()
        return True

    if data.startswith("admin:proxy:period:"):
        try:
            period = int(data.rsplit(":", 1)[1])
        except ValueError:
            await callback.answer("Некорректный срок", show_alert=True)
            return True
        if period not in SUPPORTED_PERIODS:
            await callback.answer("Недоступный срок", show_alert=True)
            return True
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            periods = list(settings.periods)
            if period in periods:
                if len(periods) == 1:
                    await callback.answer("Нужно оставить хотя бы один срок", show_alert=True)
                    return True
                periods.remove(period)
            else:
                periods.append(period)
                periods.sort()
            await save_proxy_setting(session, "proxy_shop_periods", ",".join(map(str, periods)))
            settings = await get_proxy_shop_settings(session)
        await update_or_send(callback, "📅 › Доступные сроки\n\nОтметьте сроки аренды, доступные покупателю.", reply_markup=admin_proxy_periods_keyboard(settings, SUPPORTED_PERIODS))
        await callback.answer("Сохранено")
        return True

    if data == "admin:proxy:type":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            new_type = "shared" if settings.proxy_type == "dedicated" else "dedicated"
            await save_proxy_setting(session, "proxy_shop_type", new_type)
            text, settings = await proxy_settings_text(session)
        await update_or_send(callback, text, reply_markup=admin_proxy_settings_keyboard(settings))
        await callback.answer("Тип изменён")
        return True

    if data == "admin:proxy:count":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
        await update_or_send(callback, "📦 › Количество прокси\n\nСколько прокси покупать на один оплаченный заказ.", reply_markup=admin_proxy_count_keyboard(settings.count))
        await callback.answer()
        return True

    if data in {"admin:proxy:count:plus", "admin:proxy:count:minus"}:
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            delta = 1 if data.endswith("plus") else -1
            count = max(1, min(100, settings.count + delta))
            await save_proxy_setting(session, "proxy_shop_count", str(count))
        await update_or_send(callback, "📦 › Количество прокси\n\nСколько прокси покупать на один оплаченный заказ.", reply_markup=admin_proxy_count_keyboard(count))
        await callback.answer("Сохранено")
        return True

    if data == "admin:proxy:ip_version":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            value = 6 if settings.ip_version == 4 else 4
            await save_proxy_setting(session, "proxy_shop_ip_version", str(value))
            text, settings = await proxy_settings_text(session)
        await update_or_send(callback, text, reply_markup=admin_proxy_settings_keyboard(settings))
        await callback.answer(f"Выбран IPv{value}")
        return True

    if data == "admin:admins":
        async with SessionLocal() as session:
            text = await list_admin_users_text(session, ADMIN_IDS)
        await update_or_send(callback, text, reply_markup=admin_admins_keyboard())
        await callback.answer()
        return True

    if data == "admin:admins_list":
        async with SessionLocal() as session:
            text = await list_admin_users_text(session, ADMIN_IDS)
        await update_or_send(callback, text, reply_markup=admin_admins_keyboard())
        await callback.answer()
        return True

    if data == "admin:add_admin_prompt":
        if not is_admin(callback.from_user.id):
            await callback.answer("Только главный админ из ADMIN_IDS может добавлять доп.админов", show_alert=True)
            return True
        ADMIN_ADD_ADMIN_WAIT.add(callback.from_user.id)
        await update_or_send(
            callback,
            "➕ Добавление доп.админа\n\nПришлите одним сообщением Telegram ID и имя.\n\nПример:\n123456789 Иван\n\nДля отмены напишите: отмена",
            reply_markup=admin_add_admin_cancel_keyboard(),
        )
        await callback.answer("Жду ID и имя")
        return True

    if data == "admin:add_admin_cancel":
        ADMIN_ADD_ADMIN_WAIT.discard(callback.from_user.id)
        async with SessionLocal() as session:
            text = await list_admin_users_text(session, ADMIN_IDS)
        await update_or_send(callback, text, reply_markup=admin_admins_keyboard())
        await callback.answer("Отменено")
        return True

    if data == "admin:remove_admin_env_locked":
        await callback.answer("Главный админ из ADMIN_IDS удаляется только через Render Environment", show_alert=True)
        return True

    if data == "admin:remove_admin_list":
        if not is_admin(callback.from_user.id):
            await callback.answer("Только главный админ из ADMIN_IDS может выключать доп.админов", show_alert=True)
            return True
        async with SessionLocal() as session:
            rows = await get_admin_users(session, include_disabled=False)
        text = "➖ Удаление доп.админа\n\nВыберите админа кнопкой ниже.\n\nГлавных админов из ADMIN_IDS нельзя удалить кнопкой — их нужно менять в Render Environment."
        await update_or_send(callback, text, reply_markup=admin_remove_admin_keyboard(rows, ADMIN_IDS))
        await callback.answer()
        return True

    if data.startswith("admin:remove_admin:"):
        if not is_admin(callback.from_user.id):
            await callback.answer("Только главный админ из ADMIN_IDS может выключать доп.админов", show_alert=True)
            return True
        try:
            target_admin_id = int(data.split(":")[2])
        except (ValueError, IndexError):
            await callback.answer("Некорректный ID", show_alert=True)
            return True
        if target_admin_id in ADMIN_IDS:
            await callback.answer("Главный админ из ADMIN_IDS удаляется только через Render Environment", show_alert=True)
            return True
        async with SessionLocal() as session:
            ok = await remove_admin_user(session, target_admin_id)
            rows = await get_admin_users(session, include_disabled=False)
            text = await list_admin_users_text(session, ADMIN_IDS)
        prefix = "✅ Доп.админ выключен.\n\n" if ok else "⚠️ Доп.админ не найден или уже выключен.\n\n"
        await update_or_send(callback, prefix + text, reply_markup=admin_remove_admin_keyboard(rows, ADMIN_IDS))
        await callback.answer("Готово" if ok else "Не найден")
        return True

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
            text = supplier_section_text(mode, len(rows), page, max_page)

        markup = (
            supplier_section_orders_keyboard(rows, mode, page, max_page)
            if rows
            else supplier_empty_section_keyboard(mode)
        )
        await update_or_send(callback, text, reply_markup=markup)
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
            rows, max_page = await get_supplier_pending_rows(session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE)
            text = supplier_section_text("pending", len(rows), page, max_page)

        markup = (
            supplier_section_orders_keyboard(rows, "pending", page, max_page)
            if rows
            else supplier_empty_section_keyboard("pending")
        )
        await update_or_send(callback, text, reply_markup=markup)
        await callback.answer()
        return True

    if data.startswith("supplier:wait:"):
        parts = data.split(":")
        request_id = int(parts[2])
        mode = parts[3] if len(parts) > 3 else "active"
        page = int(parts[4]) if len(parts) > 4 else 0

        async with SessionLocal() as session:
            request, order = await get_supplier_request_order(session, request_id)

        if not request or not order or request.supplier_telegram_id != callback.from_user.id:
            await callback.answer("Заявка не найдена", show_alert=True)
            return True

        text = (
            "⏳ Заявка ожидает подтверждения покупателя.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name or 'не указан'}\n"
            f"Номер: {order.phone_number or 'ещё нет'}\n"
            f"Код: {order.verification_code or 'ещё нет'}\n\n"
            "Поставщику больше ничего отправлять не нужно.\n"
            "Ждём, пока покупатель нажмёт «OK, всё успешно» или сообщит о проблеме."
        )
        await update_or_send(callback, text, reply_markup=supplier_wait_confirm_keyboard(mode, page))
        await callback.answer()
        return True

    if data.startswith("supplier:reqf:"):
        parts = data.split(":")
        request_id = int(parts[2])
        mode = parts[3] if len(parts) > 3 else "active"
        page = int(parts[4]) if len(parts) > 4 else 0

        async with SessionLocal() as session:
            ok, msg, request, order = await select_supplier_request(session, callback.from_user.id, request_id)
            if mode == "pending":
                rows, max_page = await get_supplier_pending_rows(session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE)
            else:
                rows, max_page = await supplier_rows_by_filter(session, callback.from_user.id, mode, page, SUPPLIER_PAGE_SIZE)

        if not ok or not request or not order:
            await callback.answer(msg or "Заявка не найдена", show_alert=True)
            text = supplier_section_text(mode, len(rows), page, max_page)
            markup = supplier_section_orders_keyboard(rows, mode, page, max_page) if rows else supplier_empty_section_keyboard(mode)
            await update_or_send(callback, text, reply_markup=markup)
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
        await update_or_send(callback, selected_text, reply_markup=supplier_request_actions_keyboard(request.id, request.request_type))
        await callback.answer("Заявка выбрана")
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
            orders = await get_buyer_order_rows(session, user_id, username, BUYER_ORDERS_LIMIT)

        if not orders:
            text = "🧾 Мои заказы\n\nУ вас пока нет заказов."
            markup = buyer_empty_section_keyboard("buyer:panel")
        else:
            text = "🧾 Мои заказы\n\nВыберите заказ кнопкой ниже."
            markup = buyer_orders_list_keyboard(orders)

        await update_or_send(callback, text, reply_markup=markup)
        await callback.answer()
        return True

    if data.startswith("buyer:order:"):
        order_id = int(data.split(":")[2])
        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)

        if not order:
            await update_or_send(callback, "🧾 Заказ не найден.", reply_markup=buyer_empty_section_keyboard("buyer:orders"))
            await callback.answer("Заказ не найден", show_alert=True)
            return True

        allowed_by_id = order.customer_telegram_id == user_id or order.buyer_chat_id == user_id
        allowed_by_username = bool(username and order.customer_username and order.customer_username.lower().replace("@", "") == username.lower().replace("@", ""))
        if not (allowed_by_id or allowed_by_username):
            await callback.answer("Это не ваш заказ", show_alert=True)
            return True

        await update_or_send(callback, buyer_order_card_text(order), reply_markup=buyer_order_card_keyboard(order.id, order.status))
        await callback.answer()
        return True

    if data == "buyer:help":
        text = (
            "Помощь\n\n"
            "Если заказ активен — выберите сервис кнопкой или напишите название сервиса.\n"
            "После номера нажмите «Код отправлен».\n"
            "Если номер или код не работает — нажмите кнопку проблемы под сообщением.\n"
            "Если нашли баг — отправьте /bug описание проблемы."
        )
        await update_or_send(callback, text, reply_markup=buyer_back_keyboard())
        await callback.answer()
        return True

    return False


async def handle_proxy_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user:
        return False
    data = callback.data or ""
    if not data.startswith("proxy:"):
        return False
    parts = data.split(":")
    if len(parts) < 3:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return True
    action = parts[1]
    try:
        order_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный заказ", show_alert=True)
        return True

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        settings = await get_proxy_shop_settings(session)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return True
        user_id = callback.from_user.id
        username = (callback.from_user.username or "").lower().replace("@", "")
        allowed = order.customer_telegram_id == user_id or order.buyer_chat_id == user_id
        if not allowed and username and order.customer_username:
            allowed = order.customer_username.lower().replace("@", "") == username
        if not allowed:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return True
        provider = await get_product_provider(session, order.product_id)
        is_explicit_proxy = bool(provider and provider.enabled and provider.provider_type == "proxyline")
        if not is_explicit_proxy and not is_proxyline_product(order.product_name):
            await callback.answer("Этот товар не привязан к Proxyline", show_alert=True)
            return True
        if not settings.enabled:
            await callback.answer("Автовыдача прокси временно отключена", show_alert=True)
            return True

        if action == "country":
            if len(parts) < 4:
                await callback.answer("Страна не указана", show_alert=True)
                return True
            country = parts[3].lower()
            if country not in settings.countries:
                await callback.answer("Эта страна сейчас недоступна", show_alert=True)
                return True
            order.service_name = selection_dump(country=country)
            order.status = "waiting_proxy_period"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await update_or_send(
                callback,
                f"📅 › Выбор срока\n\nСтрана: {country_label(country)}\n\nВыберите срок аренды прокси.",
                reply_markup=buyer_proxy_period_keyboard(order.id, settings.periods),
            )
            await callback.answer("Страна выбрана")
            return True

        if action == "period":
            if len(parts) < 4:
                await callback.answer("Срок не указан", show_alert=True)
                return True
            try:
                period = int(parts[3])
            except ValueError:
                await callback.answer("Некорректный срок", show_alert=True)
                return True
            country, _ = selection_load(order.service_name)
            if not country:
                order.status = "waiting_proxy_country"
                await session.commit()
                await update_or_send(callback, "Сначала выберите страну.", reply_markup=buyer_proxy_country_keyboard(order.id, settings.countries, SUPPORTED_COUNTRIES))
                await callback.answer()
                return True
            if period not in settings.periods:
                await callback.answer("Этот срок сейчас недоступен", show_alert=True)
                return True
            order.service_name = selection_dump(country=country, period=period)
            order.status = "waiting_proxy_confirm"
            order.updated_at = datetime.utcnow()
            await session.commit()
            proxy_type = "выделенный" if settings.proxy_type == "dedicated" else "общий"
            text = (
                "✅ › Подтверждение прокси\n\n"
                f"Страна: {country_label(country)}\n"
                f"├ Срок — {period} дней\n"
                f"├ Тип — {proxy_type}\n"
                f"├ Количество — {settings.count}\n"
                f"└ Версия IP — IPv{settings.ip_version}\n\n"
                "После подтверждения бот купит прокси через Proxyline API и выдаст его в этом чате."
            )
            await update_or_send(callback, text, reply_markup=buyer_proxy_confirm_keyboard(order.id))
            await callback.answer("Срок выбран")
            return True

        if action == "back_country":
            order.status = "waiting_proxy_country"
            order.service_name = selection_dump()
            order.updated_at = datetime.utcnow()
            await session.commit()
            await update_or_send(callback, "🌍 › Выбор страны\n\nВыберите страну, в которой должен находиться прокси.", reply_markup=buyer_proxy_country_keyboard(order.id, settings.countries, SUPPORTED_COUNTRIES))
            await callback.answer()
            return True

        if action == "back_period":
            country, _ = selection_load(order.service_name)
            if not country:
                country = settings.countries[0]
                order.service_name = selection_dump(country=country)
            order.status = "waiting_proxy_period"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await update_or_send(callback, f"📅 › Выбор срока\n\nСтрана: {country_label(country)}\n\nВыберите срок аренды прокси.", reply_markup=buyer_proxy_period_keyboard(order.id, settings.periods))
            await callback.answer()
            return True

        if action == "confirm":
            country, period = selection_load(order.service_name)
            if not country or not period:
                await callback.answer("Сначала выберите страну и срок", show_alert=True)
                return True
            if order.status in {"proxy_processing", "code_sent_to_customer", "confirmed"}:
                await callback.answer("Заказ уже обрабатывается или выдан", show_alert=True)
                return True
            order.status = "proxy_processing"
            order.updated_at = datetime.utcnow()
            await session.commit()
            business_id = order.business_connection_id or get_callback_business_id(callback)

    await update_or_send(callback, "⏳ › Покупка прокси\n\nЗапрос отправлен в Proxyline. Не нажимайте кнопку повторно.", reply_markup=buyer_back_keyboard())
    await callback.answer("Покупаю прокси…")
    await process_proxyline_order(bot, order_id, business_id)
    return True


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

    # Админы и поставщики работают без cooldown на inline-кнопках.
    # Для покупателя защита от случайного многократного нажатия сохраняется.
    if data and not data.startswith(("admin:", "supplier:")):
        if not await check_button_cooldown(callback, data.split(":")[0]):
            return

    logger.info("HANDLED_CALLBACK from_id=%s data=%s", callback.from_user.id if callback.from_user else None, data)

    if data.startswith("proxy:"):
        handled = await handle_proxy_callback(bot, callback)
        if handled:
            return

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

    if data == "buyer:shop":
        async with SessionLocal() as session:
            await sync_products_from_orders(session)
            categories = await list_categories(session)
        admin_access = bool(callback.from_user and await is_admin_user(callback.from_user.id))
        await update_or_send(
            callback,
            customer_home_text(),
            reply_markup=customer_home_keyboard(categories, is_admin=admin_access),
        )
        await callback.answer()
        return

    if data.startswith("buyer:shopcat:"):
        try:
            category_id = int(data.split(":")[2])
        except (ValueError, IndexError):
            await callback.answer("Некорректная категория", show_alert=True)
            return
        async with SessionLocal() as session:
            categories = await list_categories(session)
            category = next((x for x in categories if x.id == category_id), None)
            products = await list_products(session, category_id)
        if not category:
            await callback.answer("Категория не найдена", show_alert=True)
            return
        await update_or_send(callback, category_text(category, len(products)), reply_markup=products_keyboard(products, category_id))
        await callback.answer()
        return

    if data.startswith("buyer:shopproduct:"):
        try:
            product_id = int(data.split(":")[2])
        except (ValueError, IndexError):
            await callback.answer("Некорректный товар", show_alert=True)
            return
        async with SessionLocal() as session:
            product = await get_shop_product(session, product_id)
            provider = await get_product_provider(session, product.admaker_product_id) if product else None
        if not product or not product.is_active:
            await callback.answer("Товар недоступен", show_alert=True)
            return
        await update_or_send(
            callback,
            product_text(product, provider.provider_type if provider else None),
            reply_markup=product_keyboard(product, SHOP_BOT_USERNAME),
        )
        await callback.answer()
        return

    if data == "buyer:partner":
        await update_or_send(callback, "👥 Партнерская программа\n\nРаздел находится в разработке.", reply_markup=buyer_back_to_panel_keyboard())
        await callback.answer()
        return

    if data == "buyer:feedback":
        await update_or_send(callback, "✉️ Обратная связь\n\nОпишите вопрос в чате поддержки или используйте /bug для сообщения об ошибке.", reply_markup=buyer_back_to_panel_keyboard())
        await callback.answer()
        return

    if data == "buyer:faq":
        await update_or_send(callback, "📕 FAQ\n\n├ Как купить — откройте категорию и карточку товара\n├ Где заказ — раздел «Мои заказы»\n└ Поддержка — раздел «Обратная связь»", reply_markup=buyer_back_to_panel_keyboard())
        await callback.answer()
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
            closed_requests_count = await close_waiting_supplier_requests_for_order(session, order.id)
            await session.commit()
            await session.refresh(order)
            thank_you_text = await get_text(session, "thank_you", "Спасибо за покупку!")

        target_chat_id = order.buyer_chat_id or order.customer_telegram_id
        target_business_id = order.business_connection_id or ADMIN_BUSINESS_CONNECTION_ID

        thanks_sent = False
        if target_chat_id:
            thanks_sent = await send_buyer_role_panel(
                bot,
                target_chat_id,
                thank_you_text,
                business_connection_id=get_callback_business_id(callback) or target_business_id,
                reply_markup=buyer_inline_menu_keyboard(),
                callback=callback,
            )

        if not thanks_sent and callback.message:
            await update_or_send(callback, thank_you_text, reply_markup=buyer_inline_menu_keyboard())

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


# ---------------- Full shop visual style patch v15 ----------------
# Единый визуал панелей под магазин: покупатель / поставщик / админ.
# Важно: это переопределения функций выше; Python использует последние def с тем же именем.

logger.info("FIX_MARKER_FULL_VISUAL_SHOP_STYLE=v15 loaded")


def admin_panel_text() -> str:
    return (
        "⚙️ › Админ-панель\n\n"
        "Здесь вы можете управлять магазином, поставщиками, заказами, сервисами и текстами.\n\n"
        "Выберите раздел"
    )


def supplier_empty_panel_text() -> str:
    return (
        "🚚 › Панель поставщика\n\n"
        "Сейчас для вас нет активных заявок.\n\n"
        "Когда появится новая заявка, бот отправит уведомление с кнопками.\n\n"
        "📌 Быстрые действия\n"
        "├ /supplier — открыть панель\n"
        "├ /pending — ожидающие заявки\n"
        "├ /work — все активные\n"
        "├ /profile — профиль\n"
        "└ /commands — команды"
    )


def supplier_commands_text() -> str:
    return (
        "📖 › Команды поставщика\n\n"
        "Раздел помогает быстро понять, как работать с заявками.\n\n"
        "🧭 Навигация\n"
        "├ /start — открыть меню\n"
        "├ /supplier — панель поставщика\n"
        "├ /pending — ожидающие заявки\n"
        "├ /work — все активные заявки\n"
        "├ /profile — профиль поставщика\n"
        "└ /commands — список команд\n\n"
        "📦 Как выдавать\n"
        "├ Откройте нужный раздел\n"
        "├ Выберите конкретную заявку кнопкой\n"
        "├ Нажмите действие: номер или код\n"
        "└ Отправьте номер/код обычным сообщением\n\n"
        "⚠️ Если заявок нет — это нормально, значит сейчас ничего не ждёт поставщика."
    )


def supplier_main_panel_text() -> str:
    return (
        "🚚 › Кабинет поставщика\n\n"
        "Здесь вы можете брать заявки в работу, выдавать номера и коды, а также смотреть свой профиль.\n\n"
        "Выберите раздел\n\n"
        "📋 Заявки\n"
        "├ ⏳ Ожидают — новые заявки\n"
        "├ 📞 Ждут номер — нужно выдать номер\n"
        "├ 🔑 Ждут код — нужно выдать код\n"
        "└ 📊 Все активные — всё, что ещё не закрыто\n\n"
        "👤 Профиль — ваша статистика\n"
        "📖 Команды — справка по работе"
    )


def supplier_requests_panel_text() -> str:
    return (
        "📋 › Заявки поставщика\n\n"
        "Выберите раздел с нужным типом заявок.\n"
        "После выбора конкретной заявки бот будет ждать номер или код обычным сообщением.\n\n"
        "Разделы\n"
        "├ ⏳ Ожидающие\n"
        "├ 📞 Ждут номер\n"
        "├ 🔑 Ждут код\n"
        "└ 📊 Все активные"
    )


def buyer_main_panel_text() -> str:
    return (
        "🛒 › Кабинет покупателя\n\n"
        "Здесь вы можете посмотреть свои заказы, открыть активный заказ, проверить профиль или получить помощь.\n\n"
        "Выберите раздел\n\n"
        "📦 Заказы\n"
        "├ Активный заказ — текущий заказ и действия\n"
        "└ Мои заказы — история последних покупок\n\n"
        "👤 Профиль — информация о вашем аккаунте\n"
        "🆘 Помощь — что делать на каждом этапе"
    )


def format_buyer_active_order_text(order) -> str:
    if not order:
        return (
            "📦 › Активный заказ\n\n"
            "Сейчас активного заказа нет.\n\n"
            "Если вы уже оплатили заказ, отправьте /start или дождитесь обновления данных от shop-бота."
        )

    status_labels = {
        "waiting_service": "⏳ ожидает выбора сервиса",
        "waiting_supplier_number": "📞 поставщик готовит номер",
        "number_sent_to_customer": "📩 номер отправлен, ждём код",
        "waiting_supplier_code": "🔑 поставщик готовит код",
        "code_sent_to_customer": "🔐 код отправлен, ждём подтверждение",
        "confirmed": "✅ заказ закрыт успешно",
        "problem": "⚠️ есть проблема",
        "cancelled": "❌ заказ отменён",
    }
    return (
        "📦 › Активный заказ\n\n"
        f"Заказ — #{order.operation_id}\n"
        f"Статус — {status_labels.get(order.status, order.status)}\n\n"
        "Детали\n"
        f"├ Товар — {order.product_name or 'не указан'}\n"
        f"├ Сервис — {order.service_name or 'ещё не выбран'}\n"
        f"├ Номер — {order.phone_number or 'ещё нет'}\n"
        f"└ Код — {order.verification_code or 'ещё нет'}\n\n"
        "Доступные действия показаны кнопками ниже."
    )
# --------------------------------------------------
