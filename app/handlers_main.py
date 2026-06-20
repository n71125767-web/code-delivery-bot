import asyncio
from decimal import Decimal
import logging
import re
from datetime import datetime

import aiohttp
from sqlalchemy import select, func

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import (
    ADMIN_IDS,
    AUTO_DELETE_MESSAGES,
    AUTO_DELETE_DELAY_SECONDS,
    AUTO_DELETE_UNKNOWN_BUYERS,
    IGNORE_NON_BUYERS,
    NOTIFY_UNKNOWN_BUYERS,
    ADMIN_ALERT_CHAT_ID,
    ADMIN_ALERT_CHAT_IDS,
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
    GA_IDS,
    WALLET_PAYMENT_ENABLED,
)
from app.database import SessionLocal
from app.keyboards import (
    confirm_keyboard,
    number_keyboard,
    service_keyboard_from_services,
    service_confirm_keyboard,
    admin_panel_keyboard,
    admin_hidden_keyboard,
    supplier_request_actions_keyboard,
    supplier_reply_keyboard,
    supplier_orders_keyboard,
    supplier_commands_keyboard,
    buyer_inline_menu_keyboard,
    supplier_inline_menu_keyboard,
    supplier_new_order_keyboard,
    buyer_back_keyboard,
    buyer_active_order_keyboard,
    supplier_requests_menu_keyboard,
    supplier_section_orders_keyboard,
    supplier_empty_section_keyboard,
    supplier_wait_confirm_keyboard,
    buyer_empty_section_keyboard,
    buyer_order_card_keyboard,
    admin_text_keys_keyboard,
    admin_back_keyboard,
    admin_suppliers_keyboard,
    admin_suppliers_cancel_keyboard,
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
    admin_currency_keyboard,
    admin_category_select_keyboard,
    confirm_delete_product_keyboard,
    confirm_delete_category_keyboard,
    supplier_selected_request_keyboard,
    admin_main_reply_keyboard,
)
from app.parsers import extract_purchase_data, extract_phone, extract_code
from app.proxyline_products import (
    resolve_proxyline_product,
    is_proxyline_product,
    ProxylineProduct,
)
from app.proxyline import ProxylineService, ProxylineError, format_proxyline_result
from app.proxy_settings import (
    get_proxy_shop_settings,
    save_proxy_setting,
    SUPPORTED_COUNTRIES,
    SUPPORTED_PERIODS,
    country_label,
    selection_dump,
    selection_load,
)
from app.senders import safe_send_message, answer_message
from app.text_utils import plain_text
from app.repositories.product_providers import (
    get_product_provider,
    bind_product_provider,
    unbind_product_provider,
    list_product_providers,
    list_recent_internal_products,
)

from app.models import (
    ShopCategory,
    ShopProduct,
    BugReport,
    ProductStockItem,
    BroadcastJob,
    MarketplaceApplication,
    BotUser,
    ProductProvider,
)

from app.shop_admin_v20 import (
    customer_home_text,
    customer_home_keyboard,
    admin_shop_keyboard,
    all_categories,
    all_products,
    category_counts,
    admin_categories_text,
    admin_categories_keyboard,
    admin_category_text,
    admin_category_keyboard,
    admin_products_text,
    admin_products_keyboard,
    product_admin_text,
    admin_product_keyboard,
    toggle_category,
    move_category,
    delete_category,
    delete_product,
)
from app.shop import (
    list_categories,
    get_product as get_shop_product,
    category_text,
    product_text,
    products_keyboard,
    product_keyboard,
    process_admin_shop_command,
    list_proxy_products,
    list_number_products,
    special_catalog_text,
    special_products_keyboard,
    list_general_products,
    proxy_main_text,
    proxy_main_keyboard,
    proxy_categories_text,
    proxy_categories_keyboard,
    proxy_category_title,
    list_proxy_products_by_category,
)

from app.catalog_v25 import (
    admin_catalog_overview,
    admin_catalog_text,
    admin_catalog_keyboard,
    product_type_keyboard,
    currency_keyboard as catalog_currency_keyboard,
    price_back_keyboard,
    content_back_keyboard,
    product_card_text as v25_product_card_text,
    product_card_keyboard as v25_product_card_keyboard,
    advanced_keyboard,
    fulfillment_keyboard,
    delete_confirm_keyboard as v25_delete_confirm_keyboard,
    category_card_text,
    category_card_keyboard,
    view_settings_text,
    view_settings_keyboard,
    sort_keyboard,
    get_display_settings,
    stock_count as v25_stock_count,
    add_text_stock,
    next_stock_item,
)

from app.cryptopay_service import (
    PaymentConfigurationError,
    PaymentValidationError,
    check_purchase_payment,
    create_purchase_invoice,
)
from app.payment_keyboards import invoice_keyboard, payment_result_keyboard
from app.extended_v37 import (
    process_extended_command,
    handle_marketplace_callback,
    get_cooldown_seconds,
    wallet_payment_keyboard,
)
from app.wallet_service import create_wallet_payment
from app.cart_v40 import (
    add_to_cart,
    cart_keyboard,
    cart_text,
    clear_cart,
    get_cart_rows,
    set_cart_quantity,
)
from app.proxy_catalog_v36 import (
    PROXY_PERIODS,
    available_proxyline_countries,
    build_provider_key,
    countries_keyboard,
    filter_countries,
    periods_keyboard,
)
from app.proxy_pricing_v39 import (
    apply_proxy_markup,
    get_proxy_markup_multiplier,
    multiplier_label,
)
from app.country_ru import country_display
from app.v50_features import (
    get_main_page_text,
    get_faq_page_text,
    main_settings_text,
    set_main_page_text,
    set_faq_text,
    number_services_text,
    add_number_service,
    remove_number_service,
    wallet_topup_amounts_keyboard,
    wallet_topup_invoice_keyboard,
    create_wallet_topup_invoice,
    check_wallet_topup,
    supplier_products_text,
    set_supplier_product_price,
    parse_money,
)

from app.v51_features import (
    admin_capabilities_keyboard,
    admin_capabilities_text,
    admin_capability_user_keyboard,
    admin_capability_user_text,
    admin_settings_visual_keyboard,
    admin_settings_visual_text,
    admin_statistics_visual_text,
    buyer_orders_page,
    find_user_id_by_username_or_id,
    hard_delete_product,
    has_admin_capability,
    simple_back_keyboard,
)

from app.admin_reference_v28 import (
    broadcast_preview_keyboard,
    payment_methods_keyboard,
    payment_methods_text,
    payments_keyboard,
    payments_text,
    store_settings_keyboard,
)

from app.visual_ui_v32 import category_asset, category_caption, product_caption
from app.commerce_v34 import validate_product_for_sale, write_audit
from app.catalog_runtime_v29 import (
    search_visible_products,
    sort_products,
)
from app.user_registry import touch_user
from app.fulfillment_service import sync_purchase_from_order
from app.market_wallet_v49 import (
    notify_new_user,
    notify_purchase_and_credit_supplier,
    get_wallet_text,
    wallet_keyboard,
    supplier_orders_text,
    create_withdrawal_request,
    admin_withdrawals_text,
    mark_withdrawal_done,
)
from app.services import (
    create_or_update_order_from_purchase,
    find_active_order_for_customer,
    find_waiting_service_order_for_customer,
    create_supplier_request,
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
    supplier_rows_by_filter,
    buyer_orders_text,
    buyer_order_card_text,
    supplier_section_text,
    select_supplier_request,
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
logger.info("FIX_MARKER_MAIN_SECTIONS_COLORED_NAV=v20.4 loaded")
logger.info("FIX_MARKER_PROXY_CATEGORIES=v20.5 loaded")
logger.info("FIX_MARKER_STABILIZED_RELEASE=v21 loaded")
logger.info("FIX_MARKER_PRODUCT_WIZARD_PROXY_CATALOG=v22 loaded")
logger.info("FIX_MARKER_UI_SELFCHECK_FIX=v22.1 loaded")
logger.info("FIX_MARKER_CATEGORY_SYNC_FIX=v22.2 loaded")
logger.info("FIX_MARKER_MCS_SHOP_UI=v22.3 loaded")
logger.info("FIX_MARKER_BUTTON_COLORS_NAV_ONLY=v22.4 loaded")
logger.info("FIX_MARKER_CONVENIENCE_RELEASE=v23 loaded")
logger.info("FIX_MARKER_REFERENCE_STYLE_UI=v24 loaded")
logger.info("FIX_MARKER_REFERENCE_STYLE_UI_FIX=v24.1 loaded")
logger.info("FIX_MARKER_ADMIN_PRODUCT_SYSTEM=v25 loaded")
logger.info("FIX_MARKER_CRYPTOPAY_STABLE=v26 loaded")
logger.info("FIX_MARKER_STANDALONE_STORE=v27 loaded")
logger.info("FIX_MARKER_MCS_REFERENCE=v28 loaded")
logger.info("FIX_MARKER_MCS_STABLE=v29 loaded")
logger.info("FIX_MARKER_MCS_HARDENED=v31 loaded")
logger.info("FIX_MARKER_MCS_UI_ROUTING=v31.1 loaded")
logger.info("FIX_MARKER_MCS_VISUAL=v32 loaded")
logger.info("FIX_MARKER_V51_UI_PERMS_ORDERS loaded")


def validate_runtime_ui() -> None:
    """
    Проверяет актуальный интерфейс V22.

    Inline-панель пользователя:
    - Товары
    - Обратная связь
    - FAQ
    - Админ меню только при is_admin=True

    Reply-клавиатура:
    - Товар
    - Прокси
    - Номера
    """
    buyer_inline = buyer_inline_menu_keyboard(is_admin=False)
    admin_inline = buyer_inline_menu_keyboard(is_admin=True)

    buyer_inline_callbacks = {
        button.callback_data
        for row in buyer_inline.inline_keyboard
        for button in row
        if button.callback_data
    }
    admin_inline_callbacks = {
        button.callback_data
        for row in admin_inline.inline_keyboard
        for button in row
        if button.callback_data
    }

    required_buyer_callbacks = {
        "buyer:shop",
        "buyer:feedback",
        "buyer:faq",
        "buyer:orders",
    }

    missing = required_buyer_callbacks - buyer_inline_callbacks
    if missing:
        raise RuntimeError(
            f"UI self-check failed: missing buyer callbacks: {sorted(missing)}"
        )

    if "admin:panel" in buyer_inline_callbacks:
        raise RuntimeError(
            "UI self-check failed: admin callback leaked to buyer inline menu"
        )

    if "admin:panel" not in admin_inline_callbacks:
        raise RuntimeError(
            "UI self-check failed: admin callback missing in admin inline menu"
        )

    buyer_reply = buyer_main_reply_keyboard(is_admin=False)
    admin_reply = buyer_main_reply_keyboard(is_admin=True)

    buyer_reply_texts = {button.text for row in buyer_reply.keyboard for button in row}
    admin_reply_texts = {button.text for row in admin_reply.keyboard for button in row}

    required_reply_buttons = {
        "🛍 Каталог",
        "📱 Номера",
        "🛒 Корзина",
    }

    # Совместимость со старыми сообщениями: обработчик принимает старые кнопки
    # «🛒 Товар/Товары», но актуальная клавиатура показывает «🛍 Каталог».
    missing_reply = {button for button in required_reply_buttons if button not in buyer_reply_texts}
    if missing_reply:
        raise RuntimeError(
            f"UI self-check failed: missing reply buttons: {sorted(missing_reply)}"
        )

    if {"⚙️ Админ меню", "🛠 Админ"} & buyer_reply_texts:
        raise RuntimeError("UI self-check failed: admin reply button leaked to buyer")

    if not ({"⚙️ Админ меню", "🛠 Админ"} & admin_reply_texts):
        raise RuntimeError("UI self-check failed: admin reply button missing for admin")

    proxy_markup = proxy_categories_keyboard()
    proxy_callbacks = {
        button.callback_data
        for row in proxy_markup.inline_keyboard
        for button in row
        if button.callback_data
    }

    required_proxy_callbacks = {
        "buyer:proxycat:mtproxy",
        "buyer:proxycat:premium",
        "buyer:proxycat:standard",
        "buyer:proxycat:residential",
    }

    missing_proxy = required_proxy_callbacks - proxy_callbacks
    if missing_proxy:
        raise RuntimeError(
            f"UI self-check failed: missing proxy callbacks: {sorted(missing_proxy)}"
        )

    logger.info(
        "UI_SELF_CHECK_OK "
        "buyer_inline=%s admin_inline=%s buyer_reply=%s admin_reply=%s proxy=%s",
        len(buyer_inline_callbacks),
        len(admin_inline_callbacks),
        len(buyer_reply_texts),
        len(admin_reply_texts),
        len(proxy_callbacks),
    )


validate_runtime_ui()

SHOP_ADMIN_WAIT: dict[int, dict] = {}
CATALOG_V25_STATE: dict[int, dict] = {}
ADMIN_BROADCAST_V28: dict[int, dict] = {}
BUYER_CATALOG_SEARCH_WAIT: set[int] = set()
PROXY_COUNTRY_SEARCH_WAIT: dict[int, str] = {}
CART_QUANTITY_WAIT: dict[int, int] = {}
PARTNER_APPLICATION_WAIT: set[int] = set()
BUYER_FEEDBACK_WAIT: set[int] = set()
WALLET_TOPUP_WAIT: set[int] = set()
ADMIN_TEXT_EDIT_WAIT: dict[int, str] = {}
ADMIN_KEYBOARD_SENT: set[int] = set()
SUPPLIER_PRICE_WAIT: dict[int, bool] = {}
ADMIN_ADD_ADMIN_WAIT: set[int] = set()
ADMIN_SUPPLIER_WAIT: dict[int, dict] = {}

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

    text = plain_text(text)
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
    text = plain_text(text)
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
        logger.info(
            "ROLE_PANEL_EDIT_TYPEERROR chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )
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

        logger.info(
            "ROLE_PANEL_EDIT_FAILED chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )
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
    text = plain_text(text)
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
    return bool(user_id and (user_id in ADMIN_IDS or user_id in GA_IDS))


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


async def buyer_inline_keyboard_for_user(user_id: int | None) -> object:
    return buyer_inline_menu_keyboard(
        is_admin=await is_admin_user(user_id),
        is_supplier=bool(user_id and await is_supplier_user(user_id)),
    )


async def buyer_reply_keyboard_for_user(user_id: int | None) -> object:
    return buyer_main_reply_keyboard(
        is_admin=await is_admin_user(user_id),
        is_supplier=bool(user_id and await is_supplier_user(user_id)),
    )


async def user_is_root_admin(user_id: int | None) -> bool:
    return bool(user_id and (user_id in ADMIN_IDS or user_id in GA_IDS))


def required_admin_capability(callback_data: str) -> str | None:
    if callback_data.startswith(("v25:", "admin:shop:")):
        return "catalog"
    if callback_data.startswith("admin:payments"):
        return "payments"
    if callback_data.startswith(("admin:main_settings", "admin:edit_faq", "admin:edit_main_page", "admin:number_settings")):
        return "settings"
    if callback_data.startswith("admin:broadcast") or callback_data.startswith("v28:broadcast"):
        return "broadcast"
    if callback_data.startswith("admin:proxy"):
        return "proxy"
    if callback_data.startswith("admin:status"):
        return "stats"
    if callback_data.startswith(("admin:admins", "admin:caps", "admin:add_admin", "admin:remove_admin")):
        return "admins"
    if callback_data.startswith(("admin:partners", "admin:suppliers", "admin:add_supplier", "admin:remove_supplier", "admin:bind_supplier", "admin:unbind_supplier")):
        return "suppliers"
    if callback_data.startswith("admin:hidden"):
        return "hidden"
    return None


def callback_user_owns_order(order, callback: CallbackQuery) -> bool:
    if not order or not callback.from_user:
        return False
    user_id = callback.from_user.id
    username = (callback.from_user.username or "").replace("@", "").lower()
    if order.customer_telegram_id == user_id or order.buyer_chat_id == user_id:
        return True
    order_username = (order.customer_username or "").replace("@", "").lower()
    return bool(username and order_username and username == order_username)


async def guard_order_owner(callback: CallbackQuery, order) -> bool:
    if callback_user_owns_order(order, callback):
        return True
    await callback.answer("Это не ваш заказ.", show_alert=True)
    return False


def get_business_id(message: Message | None, fallback: str | None = None) -> str | None:
    if message is None:
        return fallback or ADMIN_BUSINESS_CONNECTION_ID

    return (
        getattr(message, "business_connection_id", None)
        or fallback
        or ADMIN_BUSINESS_CONNECTION_ID
    )


def remember_business_context(
    chat_id: int | None, business_connection_id: str | None
) -> None:
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


async def update_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    text = plain_text(text)
    """
    Как у админа: callback редактирует текущее inline-сообщение.
    Важно: если Telegram отвечает "message is not modified", НЕ отправляем новое сообщение.
    """
    if not callback.message:
        logger.warning(
            "UPDATE_OR_SEND_NO_MESSAGE data=%s has_keyboard=%s",
            callback.data,
            reply_markup is not None,
        )
        return

    data = callback.data or ""
    chat_id = callback.message.chat.id

    if data.startswith("supplier:"):
        business_id = get_callback_business_id(callback)
        await send_supplier_role_panel(
            callback.bot,
            chat_id,
            text,
            reply_markup=reply_markup,
            business_connection_id=business_id,
            callback=callback,
        )
        return

    if data.startswith("buyer:"):
        business_id = get_callback_business_id(callback)
        await send_buyer_role_panel(
            callback.bot,
            chat_id,
            text,
            reply_markup=reply_markup,
            business_connection_id=business_id,
            callback=callback,
        )
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
            logger.info(
                "UPDATE_OR_SEND_NOT_MODIFIED chat_id=%s data=%s",
                callback.message.chat.id,
                data,
            )
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
            logger.exception(
                "UPDATE_OR_SEND_NEW_FAILED chat_id=%s data=%s error=%s",
                callback.message.chat.id,
                data,
                send_exc,
            )




async def show_visual_card(
    callback: CallbackQuery,
    caption: str,
    reply_markup=None,
    photo=None,
    video_file_id: str | None = None,
) -> None:
    """Показывает экран как в референсе: медиа-карточка + inline-кнопки."""
    caption = plain_text(caption)
    if not callback.message:
        return
    chat_id = callback.message.chat.id
    business_id = get_callback_business_id(callback)
    try:
        if video_file_id:
            sent = await callback.bot.send_video(
                chat_id=chat_id,
                video=video_file_id,
                caption=caption,
                reply_markup=reply_markup,
                business_connection_id=business_id,
            )
        elif photo:
            sent = await callback.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=reply_markup,
                business_connection_id=business_id,
            )
        else:
            await update_or_send(callback, caption, reply_markup=reply_markup)
            return
        try:
            if sent.message_id != callback.message.message_id:
                await callback.message.delete()
        except Exception:
            pass
    except Exception:
        logger.exception(
            "VISUAL_CARD_SEND_FAILED chat_id=%s data=%s",
            chat_id,
            callback.data,
        )
        await update_or_send(callback, caption, reply_markup=reply_markup)


async def delete_later(
    bot: Bot, chat_id: int, message_id: int, delay: int | None = None
) -> None:
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
            logger.info(
                "AUTO_DELETE_SKIPPED_NOT_FOUND chat_id=%s message_id=%s",
                chat_id,
                message_id,
            )
            return
        logger.warning(
            "AUTO_DELETE_FAILED chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
        )


async def maybe_delete_message(
    bot: Bot, message: Message, delay: int | None = None
) -> None:
    if not AUTO_DELETE_MESSAGES:
        return

    try:
        asyncio.create_task(
            delete_later(bot, message.chat.id, message.message_id, delay)
        )
    except Exception:
        logger.exception("Failed to schedule incoming delete")


async def maybe_delete_sent(bot: Bot, sent_message, delay: int | None = None) -> None:
    if not AUTO_DELETE_MESSAGES:
        return

    if (
        not sent_message
        or not hasattr(sent_message, "chat")
        or not hasattr(sent_message, "message_id")
    ):
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
        asyncio.create_task(
            delete_later(bot, sent_message.chat.id, sent_message.message_id, delay)
        )
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
    sent = await answer_message(
        bot, message, text, business_connection_id, reply_markup=reply_markup
    )
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
    admin_access = await is_admin_user(chat_id)
    return await send_buyer_role_panel(
        bot,
        chat_id,
        text,
        reply_markup=await buyer_inline_keyboard_for_user(user_id),
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
    recipients = ADMIN_ALERT_CHAT_IDS or (
        [ADMIN_ALERT_CHAT_ID] if ADMIN_ALERT_CHAT_ID else []
    )
    for recipient_id in recipients:
        await safe_send_message(bot, recipient_id, text)


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
            closed_text = await get_text(
                session, "order_closed", "Заказ уже закрыт или уже в обработке."
            )
            await answer_message(bot, message, closed_text, business_connection_id)
            return
        services, max_page = await get_services_page(session, page, SERVICE_PAGE_SIZE)
        text = await get_text(
            session,
            "service_select",
            "Выберите сервис кнопкой ниже или напишите название из списка.",
        )

    if not services:
        await answer_message(
            bot,
            message,
            "Сервисы не настроены. Админ должен добавить /add_service Название",
            business_connection_id,
        )
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


async def process_bug_report_command(
    bot: Bot, message: Message, business_connection_id: str | None
) -> bool:
    if not message.from_user:
        return False

    text = (message.text or "").strip()
    if not (text == "/bug" or text.startswith("/bug ") or text.startswith("/report ")):
        return False

    payload = (
        text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
    )
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
        len(text),
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


async def process_admin_pending_input(
    bot: Bot, message: Message, business_connection_id: str | None
) -> bool:
    if not message.from_user or not await is_admin_user(message.from_user.id):
        return False

    admin_id = message.from_user.id
    text = (message.text or "").strip()

    if admin_id in ADMIN_ADD_ADMIN_WAIT:
        if text.lower() in {"отмена", "cancel", "/cancel"}:
            ADMIN_ADD_ADMIN_WAIT.discard(admin_id)
            await temp_answer(
                bot,
                message,
                "Добавление админа отменено.",
                business_connection_id,
                reply_markup=admin_admins_keyboard(),
            )
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

        name = (
            parts[1].strip()
            if len(parts) > 1 and parts[1].strip()
            else f"admin_{new_admin_id}"
        )
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
        await safe_send_message(
            bot,
            new_admin_id,
            "✅ Вы назначены администратором.\n\nОткройте бота и нажмите «🛠 Админ»."
        )
        return True

    supplier_state = ADMIN_SUPPLIER_WAIT.get(admin_id)
    if supplier_state:
        if text.lower() in {"отмена", "cancel", "/cancel"}:
            ADMIN_SUPPLIER_WAIT.pop(admin_id, None)
            await temp_answer(
                bot,
                message,
                "Действие с поставщиком отменено.",
                business_connection_id,
                reply_markup=admin_suppliers_keyboard(),
            )
            return True

        action = supplier_state.get("action")

        if action == "add":
            parts = text.split(maxsplit=1)
            if not parts or not parts[0].isdigit():
                await temp_answer(
                    bot,
                    message,
                    "Пришлите Telegram ID и имя через пробел.\n\n"
                    "Пример: 123456789 Иван",
                    business_connection_id,
                )
                return True

            supplier_id = int(parts[0])
            supplier_name = (
                parts[1].strip()
                if len(parts) > 1 and parts[1].strip()
                else f"supplier_{supplier_id}"
            )
            async with SessionLocal() as session:
                supplier = await add_supplier(
                    session,
                    supplier_id,
                    supplier_name,
                )
                suppliers_text = await list_suppliers_text(session)

            ADMIN_SUPPLIER_WAIT.pop(admin_id, None)
            await safe_send_message(
                bot,
                supplier_id,
                "✅ Вы назначены партнёром/поставщиком магазина.\n\n"
                "Откройте бота и нажмите «🚚 Я поставщик».",
                reply_markup=supplier_inline_menu_keyboard(),
            )
            await temp_answer(
                bot,
                message,
                "✅ Поставщик добавлен.\n\n"
                f"Telegram ID: {supplier.telegram_id}\n"
                f"Имя: {supplier.name}\n\n"
                f"{suppliers_text}",
                business_connection_id,
                reply_markup=admin_suppliers_keyboard(),
            )
            return True

        if action == "remove":
            if not text.isdigit():
                await temp_answer(
                    bot,
                    message,
                    "Пришлите числовой Telegram ID поставщика.",
                    business_connection_id,
                )
                return True

            supplier_id = int(text)
            async with SessionLocal() as session:
                removed = await remove_supplier(session, supplier_id)
                suppliers_text = await list_suppliers_text(session)

            ADMIN_SUPPLIER_WAIT.pop(admin_id, None)
            await temp_answer(
                bot,
                message,
                (
                    "✅ Поставщик отключён."
                    if removed
                    else "Поставщик с таким ID не найден."
                )
                + "\n\n"
                + suppliers_text,
                business_connection_id,
                reply_markup=admin_suppliers_keyboard(),
            )
            return True

        if action in {"bind", "bind_category"}:
            parts = text.split(maxsplit=1)
            if len(parts) != 2 or not parts[0].isdigit():
                await temp_answer(
                    bot,
                    message,
                    "Пришлите Telegram ID партнёра и ID товара/категории.\n\n"
                    "Пример для товара: 123456789 25\n"
                    "Пример для категории: 123456789 7",
                    business_connection_id,
                )
                return True

            supplier_id = int(parts[0])
            raw_key = parts[1].strip()
            product_key = f"cat:{raw_key}" if action == "bind_category" and raw_key.isdigit() else raw_key
            async with SessionLocal() as session:
                result = await bind_supplier_to_product(
                    session,
                    supplier_id,
                    product_key,
                )

            ADMIN_SUPPLIER_WAIT.pop(admin_id, None)
            await temp_answer(
                bot,
                message,
                result,
                business_connection_id,
                reply_markup=admin_suppliers_keyboard(),
            )
            return True

        if action == "unbind":
            parts = text.split(maxsplit=1)
            if len(parts) != 2 or not parts[0].isdigit():
                await temp_answer(
                    bot,
                    message,
                    "Пришлите Telegram ID поставщика и ID товара.\n\n"
                    "Пример: 123456789 25",
                    business_connection_id,
                )
                return True

            supplier_id = int(parts[0])
            product_key = parts[1].strip()
            async with SessionLocal() as session:
                result = await unbind_supplier_from_product(
                    session,
                    supplier_id,
                    product_key,
                )

            ADMIN_SUPPLIER_WAIT.pop(admin_id, None)
            await temp_answer(
                bot,
                message,
                result,
                business_connection_id,
                reply_markup=admin_suppliers_keyboard(),
            )
            return True

        ADMIN_SUPPLIER_WAIT.pop(admin_id, None)

    key = ADMIN_TEXT_EDIT_WAIT.get(admin_id)
    if not key:
        return False

    if not text:
        await temp_answer(
            bot, message, "Пришлите новый текст сообщением.", business_connection_id
        )
        return True

    if text.lower() in {"отмена", "cancel", "/cancel"}:
        ADMIN_TEXT_EDIT_WAIT.pop(admin_id, None)
        await temp_answer(
            bot, message, "Редактирование отменено.", business_connection_id
        )
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


def normalize_admin_state(storage: dict, user_id: int, state) -> dict | None:
    """Convert old tuple states to dict and safely remove invalid values."""
    if state is None:
        return None
    if isinstance(state, dict):
        state.setdefault("data", {})
        return state
    if isinstance(state, tuple):
        normalized = {
            "action": state[0] if len(state) > 0 else None,
            "object_id": state[1] if len(state) > 1 else None,
            "step": None,
            "data": {},
        }
        storage[user_id] = normalized
        logger.warning(
            "LEGACY_ADMIN_STATE_CONVERTED user_id=%s old_state=%r",
            user_id,
            state,
        )
        return normalized
    logger.error(
        "INVALID_ADMIN_STATE_REMOVED user_id=%s state_type=%s state=%r",
        user_id,
        type(state).__name__,
        state,
    )
    storage.pop(user_id, None)
    return None


async def run_broadcast_v29(
    bot: Bot,
    admin_id: int,
    recipients: list[int],
    text: str,
    job_id: int,
    media_type: str | None = None,
    media_file_id: str | None = None,
) -> None:
    sent = 0
    failed = 0
    async with SessionLocal() as session:
        job = await session.get(BroadcastJob, job_id)
        if job:
            job.status = "running"
            job.started_at = datetime.utcnow()
            await session.commit()

    try:
        for recipient_id in recipients:
            try:
                if media_type == "photo" and media_file_id:
                    await bot.send_photo(recipient_id, media_file_id, caption=text or None)
                elif media_type == "video" and media_file_id:
                    await bot.send_video(recipient_id, media_file_id, caption=text or None)
                elif media_type == "document" and media_file_id:
                    await bot.send_document(recipient_id, media_file_id, caption=text or None)
                else:
                    await bot.send_message(recipient_id, text)
                sent += 1
            except TelegramRetryAfter as exc:
                await asyncio.sleep(float(exc.retry_after) + 0.5)
                try:
                    if media_type == "photo" and media_file_id:
                        await bot.send_photo(recipient_id, media_file_id, caption=text or None)
                    elif media_type == "video" and media_file_id:
                        await bot.send_video(recipient_id, media_file_id, caption=text or None)
                    elif media_type == "document" and media_file_id:
                        await bot.send_document(recipient_id, media_file_id, caption=text or None)
                    else:
                        await bot.send_message(recipient_id, text)
                    sent += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1

            async with SessionLocal() as session:
                job = await session.get(BroadcastJob, job_id)
                if job:
                    job.sent_count = sent
                    job.failed_count = failed
                    job.last_user_id = recipient_id
                    await session.commit()
            await asyncio.sleep(0.05)

        async with SessionLocal() as session:
            job = await session.get(BroadcastJob, job_id)
            if job:
                job.status = "finished"
                job.sent_count = sent
                job.failed_count = failed
                job.finished_at = datetime.utcnow()
                await session.commit()
    except asyncio.CancelledError:
        async with SessionLocal() as session:
            job = await session.get(BroadcastJob, job_id)
            if job:
                job.status = "interrupted"
                job.error_text = "Broadcast task interrupted by process shutdown/SIGTERM"
                job.finished_at = datetime.utcnow()
                await session.commit()
        logger.warning("BROADCAST_JOB_INTERRUPTED job_id=%s", job_id)
        raise
    except Exception as exc:
        async with SessionLocal() as session:
            job = await session.get(BroadcastJob, job_id)
            if job:
                job.status = "failed"
                job.error_text = str(exc)[:2000]
                job.finished_at = datetime.utcnow()
                await session.commit()
        logger.exception("BROADCAST_JOB_FAILED job_id=%s", job_id)

    try:
        await bot.send_message(
            admin_id,
            "📢 Рассылка завершена\n\n"
            f"Задача: #{job_id}\n"
            f"Получателей: {len(recipients)}\n"
            f"Отправлено: {sent}\n"
            f"Ошибок: {failed}",
        )
    except Exception:
        logger.exception("BROADCAST_RESULT_SEND_FAILED admin_id=%s", admin_id)


async def process_buyer_catalog_search(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    if not message.from_user:
        return False

    user_id = message.from_user.id
    if user_id not in BUYER_CATALOG_SEARCH_WAIT:
        return False

    BUYER_CATALOG_SEARCH_WAIT.discard(user_id)
    query = (message.text or "").strip()
    if not query:
        await answer_message(
            bot,
            message,
            "Поисковый запрос пуст.",
            business_connection_id,
        )
        return True

    async with SessionLocal() as session:
        settings = await get_display_settings(session)
        products = await search_visible_products(session, query)
        products = sort_products(products, settings.sort_mode)

    kb = InlineKeyboardBuilder()
    for product in products:
        kb.button(
            text=f"📦 {product.name} — {product.price} {product.currency}",
            callback_data=f"buyer:shopproduct:{product.id}",
        )
    kb.button(text="⬅️ К магазину", callback_data="buyer:shop", style="danger")
    kb.adjust(max(1, min(int(settings.columns_count or 1), 3)))

    await answer_message(
        bot,
        message,
        (
            f"🔍 Результаты поиска: {query}\\n\\n"
            + (
                f"Найдено товаров: {len(products)}"
                if products
                else "Ничего не найдено."
            )
        ),
        business_connection_id,
        reply_markup=kb.as_markup(),
    )
    return True


async def process_proxy_country_search(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    if not message.from_user:
        return False

    user_id = message.from_user.id
    category_key = PROXY_COUNTRY_SEARCH_WAIT.pop(user_id, None)
    if not category_key:
        return False

    query = (message.text or "").strip()
    countries = await available_proxyline_countries()
    results = filter_countries(countries, query)
    title = proxy_category_title(category_key)
    if not results:
        await answer_message(
            bot,
            message,
            f"🔎 <b>Поиск страны</b>\n\nПо запросу «{query}» ничего не найдено. "
            "Попробуйте написать название иначе: Россия, США, Германия, NL, TR.",
            business_connection_id,
            reply_markup=countries_keyboard(category_key, countries, page=0),
        )
        return True

    await answer_message(
        bot,
        message,
        f"{title}\n\n🔎 Результаты поиска: <b>{query}</b>\n"
        f"Найдено стран: {len(results)}\n\nВыберите страну прокси:",
        business_connection_id,
        reply_markup=countries_keyboard(category_key, results, page=0, page_size=50),
    )
    return True




async def process_cart_quantity_input(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    if not message.from_user:
        return False
    item_id = CART_QUANTITY_WAIT.get(message.from_user.id)
    if not item_id:
        return False
    text = (message.text or "").strip().lower()
    if text in {"отмена", "cancel", "/cancel"}:
        CART_QUANTITY_WAIT.pop(message.from_user.id, None)
        async with SessionLocal() as session:
            rows = await get_cart_rows(session, message.from_user.id)
        await answer_message(bot, message, cart_text(rows), business_connection_id, reply_markup=cart_keyboard(rows))
        return True
    try:
        qty = int(text)
    except ValueError:
        await answer_message(bot, message, "Введите число от 1 до 99 или «отмена».", business_connection_id)
        return True
    if qty < 0 or qty > 99:
        await answer_message(bot, message, "Количество должно быть от 1 до 99.", business_connection_id)
        return True
    async with SessionLocal() as session:
        await set_cart_quantity(session, message.from_user.id, item_id, qty)
        rows = await get_cart_rows(session, message.from_user.id)
    CART_QUANTITY_WAIT.pop(message.from_user.id, None)
    await answer_message(bot, message, cart_text(rows), business_connection_id, reply_markup=cart_keyboard(rows))
    return True


async def process_partner_application_input(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    if not message.from_user or message.from_user.id not in PARTNER_APPLICATION_WAIT:
        return False
    text = (message.text or message.caption or "").strip()
    if text.lower() in {"отмена", "cancel", "/cancel"}:
        PARTNER_APPLICATION_WAIT.discard(message.from_user.id)
        await answer_message(bot, message, "Заявка партнёра отменена.", business_connection_id, reply_markup=buyer_inline_menu_keyboard(is_admin=await is_admin_user(message.from_user.id)))
        return True
    if len(text) < 20:
        await answer_message(
            bot,
            message,
            "Опишите услугу подробнее: название, цена, формат выдачи и контакты внутри Telegram. Для отмены: отмена",
            business_connection_id,
        )
        return True
    username = (message.from_user.username or "").replace("@", "")
    title = text.splitlines()[0][:255]
    async with SessionLocal() as session:
        app = MarketplaceApplication(
            applicant_telegram_id=message.from_user.id,
            applicant_username=username or None,
            seller_name=username or str(message.from_user.id),
            title=title,
            description=text,
            price=None,
            currency="RUB",
            category_name="Партнёры",
            content_preview=text[:1000],
            status="pending",
        )
        session.add(app)
        await session.commit()
        await session.refresh(app)
    PARTNER_APPLICATION_WAIT.discard(message.from_user.id)
    from app.extended_v37 import marketplace_moderation_keyboard
    moderator_chat_ids = ADMIN_ALERT_CHAT_IDS or ADMIN_IDS
    for admin_chat_id in moderator_chat_ids:
        await safe_send_message(
            bot,
            admin_chat_id,
            "🤝 Новая партнёрская заявка\n\n"
            f"ID: {app.id}\n"
            f"Пользователь: {message.from_user.id} @{username or 'нет'}\n\n"
            f"{text}",
            reply_markup=marketplace_moderation_keyboard(app.id),
        )
    await answer_message(
        bot,
        message,
        f"✅ Заявка #{app.id} отправлена на модерацию. Администратор примет или отклонит её.",
        business_connection_id,
        reply_markup=buyer_inline_menu_keyboard(is_admin=await is_admin_user(message.from_user.id)),
    )
    return True


async def process_broadcast_v28_input(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    if not message.from_user:
        return False
    state = ADMIN_BROADCAST_V28.get(message.from_user.id)
    if not state:
        return False

    text = (message.text or message.caption or "").strip()
    media_type = None
    media_file_id = None
    if message.photo:
        media_type = "photo"
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_file_id = message.video.file_id
    elif message.document:
        media_type = "document"
        media_file_id = message.document.file_id

    if not text and not media_file_id:
        await answer_message(
            bot,
            message,
            "Отправьте текст, фото с подписью, видео или документ для рассылки.",
            business_connection_id,
        )
        return True

    state["text"] = text
    state["media_type"] = media_type
    state["media_file_id"] = media_file_id
    state["step"] = "confirm"

    # Предпросмотр без служебной шапки: получатель увидит именно это.
    if media_type == "photo" and media_file_id:
        await bot.send_photo(
            message.chat.id,
            media_file_id,
            caption=text or None,
            reply_markup=broadcast_preview_keyboard(),
            business_connection_id=business_connection_id,
        )
    elif media_type == "video" and media_file_id:
        await bot.send_video(
            message.chat.id,
            media_file_id,
            caption=text or None,
            reply_markup=broadcast_preview_keyboard(),
            business_connection_id=business_connection_id,
        )
    elif media_type == "document" and media_file_id:
        await bot.send_document(
            message.chat.id,
            media_file_id,
            caption=text or None,
            reply_markup=broadcast_preview_keyboard(),
            business_connection_id=business_connection_id,
        )
    else:
        await answer_message(
            bot,
            message,
            text,
            business_connection_id,
            reply_markup=broadcast_preview_keyboard(),
        )
    return True


async def process_catalog_v25_input(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    if not message.from_user:
        return False
    admin_id = message.from_user.id
    state = normalize_admin_state(
        CATALOG_V25_STATE,
        admin_id,
        CATALOG_V25_STATE.get(admin_id),
    )
    if not state:
        return False

    action = state.get("action")
    step = state.get("step")
    data = state.setdefault("data", {})
    text = (message.text or message.caption or "").strip()
    if text.lower() in {"отмена", "cancel", "/cancel", "❌ отмена"}:
        CATALOG_V25_STATE.pop(admin_id, None)
        await answer_message(
            bot,
            message,
            "✅ Создание товара отменено. Можно открыть админку заново.",
            business_connection_id,
            reply_markup=admin_shop_keyboard(),
        )
        return True

    try:
        if action == "product_create":
            if step == "name":
                if not text or len(text) > 64:
                    await answer_message(
                        bot,
                        message,
                        "Название должно быть от 1 до 64 символов.",
                        business_connection_id,
                    )
                    return True
                data["name"] = text
                state["step"] = "type"
                await answer_message(
                    bot,
                    message,
                    f"📝 Название: {text}\n\n"
                    "Выберите тип товара:\n\n"
                    "♾️ Статический товар\n"
                    "Всем покупателям выдается один и тот же контент.\n\n"
                    "📦 Количественный товар\n"
                    "Каждому покупателю выдается уникальная позиция по очереди.\n\n"
                    "Выберите тип 👇",
                    business_connection_id,
                    reply_markup=product_type_keyboard(),
                )
                return True

            if step == "price":
                try:
                    price = Decimal(text.replace(",", "."))
                except Exception:
                    await answer_message(
                        bot,
                        message,
                        "Введите цену числом. Например: 0.1",
                        business_connection_id,
                        reply_markup=price_back_keyboard(),
                    )
                    return True
                if price < Decimal("0.1"):
                    await answer_message(
                        bot,
                        message,
                        f"Минимальная цена: 0.1 {data['currency']}",
                        business_connection_id,
                        reply_markup=price_back_keyboard(),
                    )
                    return True
                data["price"] = str(price)
                state["step"] = "content"
                prompt = (
                    f"📦 Название: {data['name']}\n"
                    f"💰 Цена: {price} {data['currency']}\n\n"
                )
                if data["product_type"] == "static":
                    prompt += (
                        "Отправьте контент для покупателя\n\n"
                        "Это то, что получит клиент после оплаты:\n"
                        "• Текст или ссылка\n"
                        "• Фото или видео\n"
                        "• Документ или архив\n\n"
                        "💡 Отправьте контент в чат с ботом 👇"
                    )
                else:
                    prompt += (
                        "Отправьте позиции товара, каждую с новой строки.\n\n"
                        "Пример:\nKEY-001\nKEY-002\nKEY-003"
                    )
                await answer_message(
                    bot,
                    message,
                    prompt,
                    business_connection_id,
                    reply_markup=content_back_keyboard(),
                )
                return True

            if step == "content":
                content_type = None
                content_text = None
                content_file_id = None
                stock_lines = []

                if data["product_type"] == "quantity":
                    if not text:
                        await answer_message(
                            bot,
                            message,
                            "Для количественного товара отправьте позиции текстом, каждую с новой строки.",
                            business_connection_id,
                        )
                        return True
                    stock_lines = [
                        line.strip() for line in text.splitlines() if line.strip()
                    ]
                    if not stock_lines:
                        return True
                else:
                    if message.photo:
                        content_type = "photo"
                        content_file_id = message.photo[-1].file_id
                        content_text = message.caption
                    elif message.video:
                        content_type = "video"
                        content_file_id = message.video.file_id
                        content_text = message.caption
                    elif message.document:
                        content_type = "document"
                        content_file_id = message.document.file_id
                        content_text = message.caption
                    elif text:
                        content_type = "text"
                        content_text = text
                    else:
                        await answer_message(
                            bot,
                            message,
                            "Отправьте текст, ссылку, фото, видео или документ.",
                            business_connection_id,
                        )
                        return True

                internal_product_key = int(datetime.utcnow().timestamp() * 1000000)
                async with SessionLocal() as session:
                    product = ShopProduct(
                        internal_key=internal_product_key,
                        name=data["name"],
                        category_id=data.get("category_id"),
                        product_type=data["product_type"],
                        fulfillment_type=(
                            "stock" if data["product_type"] == "quantity" else "digital"
                        ),
                        price=Decimal(data["price"]),
                        currency=data["currency"],
                        content_type=content_type,
                        content_text=content_text,
                        content_file_id=content_file_id,
                        is_active=False,
                        payment_enabled=True,
                    )
                    session.add(product)
                    await session.flush()
                    if stock_lines:
                        for line in stock_lines:
                            session.add(
                                ProductStockItem(
                                    product_id=product.id,
                                    content_type="text",
                                    content_text=line,
                                    status="available",
                                )
                            )
                    await session.commit()
                    await session.refresh(product)
                    count = await v25_stock_count(session, product.id)

                CATALOG_V25_STATE.pop(admin_id, None)
                await answer_message(
                    bot,
                    message,
                    v25_product_card_text(product, count),
                    business_connection_id,
                    reply_markup=v25_product_card_keyboard(product),
                )
                return True

        if action == "category_create":
            if step == "name":
                if not text or len(text) > 64:
                    await answer_message(
                        bot,
                        message,
                        "Название категории должно быть до 64 символов.",
                        business_connection_id,
                    )
                    return True
                data["name"] = text
                state["step"] = "description"
                await answer_message(
                    bot,
                    message,
                    f"📁 Название: {text}\n\nОтправьте описание категории или слово «пропустить».",
                    business_connection_id,
                )
                return True
            if step == "description":
                description = None if text.lower() == "пропустить" else text
                async with SessionLocal() as session:
                    category = ShopCategory(
                        name=data["name"],
                        emoji="",
                        description=description,
                        is_active=True,
                    )
                    session.add(category)
                    await session.commit()
                    await session.refresh(category)
                CATALOG_V25_STATE.pop(admin_id, None)
                await answer_message(
                    bot,
                    message,
                    category_card_text(category, 0),
                    business_connection_id,
                    reply_markup=category_card_keyboard(
                        category.id, category.is_active
                    ),
                )
                return True

        object_id = state.get("object_id")
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, object_id) if object_id else None
            category = await session.get(ShopCategory, object_id) if object_id else None

            if action == "edit_product_name" and product:
                product.name = text[:64]
            elif action == "edit_product_price" and product:
                product.price = Decimal(text.replace(",", "."))
            elif action == "edit_product_description" and product:
                product.description = text
            elif action == "edit_product_note" and product:
                product.note = text
            elif action == "edit_product_old_price" and product:
                product.old_price = Decimal(text.replace(",", "."))
            elif action == "edit_product_position" and product:
                product.sort_order = int(text)
            elif action == "edit_payment_systems" and product:
                product.payment_systems = text
            elif action == "edit_payment_description" and product:
                product.payment_description = text
            elif action == "edit_product_content" and product:
                if message.photo:
                    product.content_type = "photo"
                    product.content_file_id = message.photo[-1].file_id
                    product.content_text = message.caption
                elif message.video:
                    product.content_type = "video"
                    product.content_file_id = message.video.file_id
                    product.content_text = message.caption
                elif message.document:
                    product.content_type = "document"
                    product.content_file_id = message.document.file_id
                    product.content_text = message.caption
                else:
                    product.content_type = "text"
                    product.content_text = text
            elif action == "edit_product_photo" and product and message.photo:
                product.photo_file_id = message.photo[-1].file_id
            elif action == "edit_product_video" and product and message.video:
                product.video_file_id = message.video.file_id
            elif action == "add_stock" and product:
                count_added = await add_text_stock(session, product.id, text)
                if count_added:
                    product.payment_enabled = True
            elif action == "category_name" and category:
                category.name = text[:64]
            elif action == "category_description" and category:
                category.description = text
            elif action == "category_photo" and category and message.photo:
                category.photo_file_id = message.photo[-1].file_id
            elif action == "give_product" and product:
                target_id, target_error = await find_user_id_by_username_or_id(session, text)
                if target_id is None:
                    await answer_message(
                        bot,
                        message,
                        target_error or "Пользователь не найден.",
                        business_connection_id,
                    )
                    return True
                if product.product_type == "quantity":
                    stock = await next_stock_item(session, product.id)
                    if not stock:
                        product.payment_enabled = False
                        await session.commit()
                        await answer_message(
                            bot,
                            message,
                            "Нет доступных позиций. Оплата товара приостановлена.",
                            business_connection_id,
                        )
                        return True
                    ok = await safe_send_message(
                        bot,
                        target_id,
                        stock.content_text or "Товар",
                        allow_normal_fallback=True,
                    )
                    if ok:
                        stock.status = "delivered"
                        stock.delivered_to = target_id
                        stock.delivered_at = datetime.utcnow()
                        product.sales_count += 1
                        remaining = await v25_stock_count(session, product.id)
                        if remaining <= 0:
                            product.payment_enabled = False
                else:
                    if product.content_type == "text":
                        ok = await safe_send_message(
                            bot,
                            target_id,
                            product.content_text or "Товар",
                            allow_normal_fallback=True,
                        )
                    elif product.content_type == "photo":
                        ok = await bot.send_photo(
                            target_id,
                            product.content_file_id,
                            caption=product.content_text,
                        )
                    elif product.content_type == "video":
                        ok = await bot.send_video(
                            target_id,
                            product.content_file_id,
                            caption=product.content_text,
                        )
                    elif product.content_type == "document":
                        ok = await bot.send_document(
                            target_id,
                            product.content_file_id,
                            caption=product.content_text,
                        )
                    else:
                        ok = False
                    if ok:
                        product.sales_count += 1
                await session.commit()
                CATALOG_V25_STATE.pop(admin_id, None)
                await answer_message(
                    bot, message, "✅ Товар выдан пользователю.", business_connection_id
                )
                return True
            else:
                return False

            await session.commit()
            if product:
                await session.refresh(product)
                count = await v25_stock_count(session, product.id)
                CATALOG_V25_STATE.pop(admin_id, None)
                await answer_message(
                    bot,
                    message,
                    v25_product_card_text(product, count),
                    business_connection_id,
                    reply_markup=v25_product_card_keyboard(product),
                )
                return True
            if category:
                await session.refresh(category)
                product_count = int(
                    await session.scalar(
                        select(func.count(ShopProduct.id)).where(
                            ShopProduct.category_id == category.id
                        )
                    )
                    or 0
                )
                CATALOG_V25_STATE.pop(admin_id, None)
                await answer_message(
                    bot,
                    message,
                    category_card_text(category, product_count),
                    business_connection_id,
                    reply_markup=category_card_keyboard(
                        category.id, category.is_active
                    ),
                )
                return True
    except Exception as exc:
        logger.exception(
            "CATALOG_V25_INPUT_FAILED admin_id=%s action=%s step=%s",
            admin_id,
            action,
            step,
        )
        await answer_message(
            bot,
            message,
            f"❌ Не удалось сохранить: {exc}\n\nПовторите ввод или откройте меню заново.",
            business_connection_id,
        )
        return True

    return False


async def process_shop_admin_pending_input(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    if not message.from_user:
        return False
    admin_id = message.from_user.id
    state = normalize_admin_state(
        SHOP_ADMIN_WAIT,
        admin_id,
        SHOP_ADMIN_WAIT.get(admin_id),
    )
    if not state:
        return False
    text = (message.text or "").strip()
    if text.lower() in {"отмена", "/cancel", "cancel"}:
        SHOP_ADMIN_WAIT.pop(admin_id, None)
        await answer_message(
            bot,
            message,
            "Действие отменено.",
            business_connection_id,
            reply_markup=admin_shop_keyboard(),
        )
        return True

    action = state.get("action")
    step = state.get("step")
    data = state.setdefault("data", {})
    try:
        if action == "category_wizard":
            if step == "name":
                async with SessionLocal() as session:
                    row = ShopCategory(name=text[:120], emoji="", is_active=True)
                    session.add(row)
                    await session.commit()
                SHOP_ADMIN_WAIT.pop(admin_id, None)
                await answer_message(
                    bot,
                    message,
                    "✅ Категория создана.",
                    business_connection_id,
                    reply_markup=admin_shop_keyboard(),
                )
                return True

        if action == "product_wizard":
            if step == "name":
                data["name"] = text[:255]
                state["step"] = "price"
                await answer_message(
                    bot,
                    message,
                    "📦 Создание товара\n\nШаг 2 из 5. Отправьте цену.\nНапример: 3.10",
                    business_connection_id,
                )
                return True
            if step == "price":
                data["price"] = str(Decimal(text.replace(",", ".")))
                state["step"] = "currency"
                await answer_message(
                    bot,
                    message,
                    "📦 Создание товара\n\nШаг 3 из 5. Выберите валюту.",
                    business_connection_id,
                    reply_markup=admin_currency_keyboard(),
                )
                return True
            if step == "legacy_external_id_disabled":
                data["internal_key"] = int(text)
                state["step"] = "category"
                async with SessionLocal() as session:
                    categories = await all_categories(session)
                await answer_message(
                    bot,
                    message,
                    "📦 Создание товара\n\nШаг 5 из 5. Выберите категорию.",
                    business_connection_id,
                    reply_markup=admin_category_select_keyboard(categories),
                )
                return True

        object_id = state.get("object_id")
        async with SessionLocal() as session:
            if action == "category_name":
                row = await session.get(ShopCategory, object_id)
                row.name = text[:120]
                await session.commit()
                result = "✅ Название обновлено."
            elif action == "product_name":
                row = await session.get(ShopProduct, object_id)
                row.name = text[:255]
                await session.commit()
                result = "✅ Название обновлено."
            elif action == "product_desc":
                row = await session.get(ShopProduct, object_id)
                row.description = text
                await session.commit()
                result = "✅ Описание обновлено."
            elif action == "product_price":
                row = await session.get(ShopProduct, object_id)
                parts = text.split()
                row.price = Decimal(parts[0].replace(",", "."))
                if len(parts) > 1:
                    row.currency = parts[1].upper()
                await session.commit()
                result = "✅ Цена обновлена."
            elif action == "product_supplier":
                row = await session.get(ShopProduct, object_id)
                supplier_id = int(text)
                await bind_product_provider(
                    session, row.internal_key, "supplier", str(supplier_id), row.name
                )
                result = "✅ Поставщик назначен."
            else:
                return False
        SHOP_ADMIN_WAIT.pop(admin_id, None)
        await answer_message(
            bot,
            message,
            result,
            business_connection_id,
            reply_markup=admin_shop_keyboard(),
        )
        return True
    except Exception as exc:
        await answer_message(
            bot,
            message,
            f"❌ Ошибка: {exc}\n\nПовторите ввод или отправьте «Отмена».",
            business_connection_id,
        )
        return True


async def process_admin_command(
    bot: Bot, message: Message, business_connection_id: str | None
) -> bool:
    if not message.from_user or not await is_admin_user(message.from_user.id):
        return False

    user_id = message.from_user.id
    text = (message.text or "").strip()
    parts = text.split()

    if text in {"/admin", "/panel", "/menu"}:
        await answer_message(
            bot,
            message,
            "🛠 Админ-панель открыта.",
            business_connection_id,
            reply_markup=admin_main_reply_keyboard(),
        )
        await answer_message(
            bot,
            message,
            admin_panel_text(),
            business_connection_id,
            reply_markup=admin_panel_keyboard(),
        )
        return True

    if text == "/main_settings":
        await answer_message(bot, message, await main_settings_text(), business_connection_id, reply_markup=admin_hidden_keyboard())
        return True
    if text.startswith("/main_set"):
        await answer_message(bot, message, await set_main_page_text(text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""), business_connection_id, reply_markup=admin_hidden_keyboard())
        return True
    if text.startswith("/faq_set"):
        await answer_message(bot, message, await set_faq_text(text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""), business_connection_id, reply_markup=admin_hidden_keyboard())
        return True
    if text == "/number_services":
        await answer_message(bot, message, await number_services_text(), business_connection_id, reply_markup=admin_hidden_keyboard())
        return True
    if text.startswith("/number_service_add"):
        await answer_message(bot, message, await add_number_service(text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""), business_connection_id, reply_markup=admin_hidden_keyboard())
        return True
    if text.startswith("/number_service_remove"):
        await answer_message(bot, message, await remove_number_service(text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""), business_connection_id, reply_markup=admin_hidden_keyboard())
        return True

    if text == "/admins":
        async with SessionLocal() as session:
            result = await list_admin_users_text(session, ADMIN_IDS)
        await answer_message(
            bot,
            message,
            result,
            business_connection_id,
            reply_markup=admin_admins_keyboard(),
        )
        return True

    if text.startswith("/add_admin"):
        if not is_admin(message.from_user.id):
            await answer_message(
                bot,
                message,
                "Только главный админ из ADMIN_IDS может добавлять доп.админов.",
                business_connection_id,
            )
            return True
        if len(parts) < 2:
            await answer_message(
                bot,
                message,
                "Формат:\n/add_admin TELEGRAM_ID Имя",
                business_connection_id,
            )
            return True
        try:
            admin_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id
            )
            return True
        name = " ".join(parts[2:]).strip() or f"admin_{admin_id}"
        async with SessionLocal() as session:
            admin = await add_admin_user(
                session, admin_id, name, added_by=message.from_user.id
            )
        await answer_message(
            bot,
            message,
            f"OK. Доп.админ добавлен.\nID: {admin.telegram_id}\nИмя: {admin.name}",
            business_connection_id,
        )
        await safe_send_message(
            bot, admin_id, "Вы назначены дополнительным админом. Откройте /admin"
        )
        return True

    if text.startswith("/remove_admin"):
        if not is_admin(message.from_user.id):
            await answer_message(
                bot,
                message,
                "Только главный админ из ADMIN_IDS может выключать доп.админов.",
                business_connection_id,
            )
            return True
        if len(parts) != 2:
            await answer_message(
                bot,
                message,
                "Формат:\n/remove_admin TELEGRAM_ID",
                business_connection_id,
            )
            return True
        try:
            admin_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id
            )
            return True
        async with SessionLocal() as session:
            ok = await remove_admin_user(session, admin_id)
        await answer_message(
            bot,
            message,
            "OK. Доп.админ выключен." if ok else "Доп.админ не найден.",
            business_connection_id,
        )
        return True

    if text == "/withdrawals":
        await answer_message(bot, message, await admin_withdrawals_text(), business_connection_id)
        return True

    if text.startswith("/withdraw_done"):
        result = await mark_withdrawal_done(bot, user_id, text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else "")
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/retry_purchase"):
        if len(parts) != 2:
            await answer_message(
                bot,
                message,
                "Формат:\n/retry_purchase ID_ПОКУПКИ\n\nИспользуйте после пополнения баланса или исправления поставщика.",
                business_connection_id,
            )
            return True
        try:
            purchase_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "ID покупки должен быть числом.", business_connection_id)
            return True
        async with SessionLocal() as session:
            from app.models import DigitalPurchase

            purchase = await session.get(DigitalPurchase, purchase_id)
            if purchase is None:
                await answer_message(bot, message, "Покупка не найдена.", business_connection_id)
                return True
            if purchase.status == "delivered":
                await answer_message(bot, message, "Эта покупка уже выдана.", business_connection_id)
                return True
            purchase.status = "paid"
            purchase.delivery_error = None
            purchase.delivery_started_at = None
            purchase.active_key = None
            purchase.updated_at = datetime.utcnow()
            await session.commit()
        from app.cryptopay_service import deliver_purchase

        ok = await deliver_purchase(bot, purchase_id)
        await answer_message(
            bot,
            message,
            (
                f"✅ Повторная выдача покупки #{purchase_id} выполнена."
                if ok
                else f"⚠️ Повторная выдача покупки #{purchase_id} не выполнена. Смотрите лог/уведомление админа."
            ),
            business_connection_id,
        )
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
                lines.append(
                    f"{state} {row.internal_key} — {row.product_name or 'Товар'} — {row.provider_type}:{row.provider_key or '-'}"
                )
            result = "\n".join(lines)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text == "/products":
        async with SessionLocal() as session:
            rows = await list_recent_internal_products(session)
        result = "📦 Собственные товары\n\n" + (
            "\n".join(f"{pid} — {name}" for pid, name in rows)
            if rows
            else "Товары пока не созданы."
        )
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/bind_proxyline"):
        if len(parts) != 2:
            await answer_message(
                bot,
                message,
                "Формат: /bind_proxyline PRODUCT_ID",
                business_connection_id,
            )
            return True
        try:
            product_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "PRODUCT_ID должен быть числом.", business_connection_id
            )
            return True
        async with SessionLocal() as session:
            recent = dict(await list_recent_internal_products(session, 100))
            row = await bind_product_provider(
                session, product_id, "proxyline", "proxyline", recent.get(product_id)
            )
        await answer_message(
            bot,
            message,
            f"✅ Товар {row.internal_key} привязан к автопрокси.",
            business_connection_id,
        )
        return True

    if text.startswith("/bind_product_supplier"):
        if len(parts) != 3:
            await answer_message(
                bot,
                message,
                "Формат: /bind_product_supplier PRODUCT_ID SUPPLIER_TELEGRAM_ID",
                business_connection_id,
            )
            return True
        try:
            product_id, supplier_id = int(parts[1]), int(parts[2])
        except ValueError:
            await answer_message(
                bot, message, "ID должны быть числами.", business_connection_id
            )
            return True
        async with SessionLocal() as session:
            recent = dict(await list_recent_internal_products(session, 100))
            row = await bind_product_provider(
                session,
                product_id,
                "supplier",
                str(supplier_id),
                recent.get(product_id),
            )
        await answer_message(
            bot,
            message,
            f"✅ Товар {row.internal_key} привязан к поставщику {supplier_id}.",
            business_connection_id,
        )
        return True

    if text.startswith("/unbind_product"):
        if len(parts) != 2:
            await answer_message(
                bot,
                message,
                "Формат: /unbind_product PRODUCT_ID",
                business_connection_id,
            )
            return True
        try:
            product_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "PRODUCT_ID должен быть числом.", business_connection_id
            )
            return True
        async with SessionLocal() as session:
            ok = await unbind_product_provider(session, product_id)
        await answer_message(
            bot,
            message,
            "✅ Привязка отключена." if ok else "Привязка не найдена.",
            business_connection_id,
        )
        return True

    if text.startswith("/restore_product "):
        if not await is_admin_user(user_id):
            await answer_message(bot, message, "Нет доступа.", business_connection_id)
            return True
        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].isdigit():
            await answer_message(
                bot, message, "Формат: /restore_product PRODUCT_ID",
                business_connection_id,
            )
            return True
        product_id = int(parts[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            if not product:
                await answer_message(bot, message, "Товар не найден.", business_connection_id)
                return True
            product.is_deleted = False
            product.deleted_at = None
            product.deleted_by = None
            product.updated_at = datetime.utcnow()
            await session.commit()
        await write_audit(user_id, "product_restored", "product", product_id)
        await answer_message(bot, message, "✅ Товар восстановлен как скрытый.", business_connection_id)
        return True

    if text == "/archived_products":
        if not await is_admin_user(user_id):
            await answer_message(bot, message, "Нет доступа.", business_connection_id)
            return True
        async with SessionLocal() as session:
            rows = list((await session.scalars(
                select(ShopProduct)
                .where(ShopProduct.is_deleted.is_(True))
                .order_by(ShopProduct.deleted_at.desc(), ShopProduct.id.desc())
                .limit(100)
            )).all())
        result = "🗄 Архив товаров\n\n" + (
            "\n".join(f"#{row.id} — {row.name}" for row in rows)
            if rows else "Архив пуст."
        )
        result += "\n\nВосстановление: /restore_product ID"
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/set_provider_key "):
        if not await is_admin_user(user_id):
            await answer_message(bot, message, "Нет доступа.", business_connection_id)
            return True
        parts = text.split(maxsplit=2)
        if len(parts) != 3 or not parts[1].isdigit():
            await answer_message(
                bot, message,
                "Формат: /set_provider_key PRODUCT_ID JSON_ИЛИ_TELEGRAM_ID",
                business_connection_id,
            )
            return True
        product_id = int(parts[1])
        provider_key = parts[2].strip()
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            if not product:
                await answer_message(bot, message, "Товар не найден.", business_connection_id)
                return True
            product.provider_key = provider_key
            product.updated_at = datetime.utcnow()
            await session.commit()
        await write_audit(
            user_id, "product_provider_key_changed", "product", product_id,
            {"provider_key": provider_key},
        )
        await answer_message(bot, message, "✅ provider_key сохранён.", business_connection_id)
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
            await answer_message(
                bot,
                message,
                "Формат:\n/add_list Название\n\nПример:\n/add_list numbers",
                business_connection_id,
            )
            return True
        async with SessionLocal() as session:
            result = await add_service_list(session, name)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/list_add_service"):
        payload = text.replace("/list_add_service", "", 1).strip()
        if "|" not in payload:
            await answer_message(
                bot,
                message,
                "Формат:\n/list_add_service Лист | Сервис",
                business_connection_id,
            )
            return True
        list_name, service_name = [x.strip() for x in payload.split("|", 1)]
        async with SessionLocal() as session:
            result = await add_service_to_list(session, list_name, service_name)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/add_service"):
        name = text.replace("/add_service", "", 1).strip()
        if not name:
            await answer_message(
                bot,
                message,
                "Формат:\n/add_service Название\n\nПример:\n/add_service Telegram",
                business_connection_id,
            )
            return True

        async with SessionLocal() as session:
            result = await add_service(session, name)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/remove_service"):
        name = text.replace("/remove_service", "", 1).strip()
        if not name:
            await answer_message(
                bot,
                message,
                "Формат:\n/remove_service Название",
                business_connection_id,
            )
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
            await answer_message(
                bot,
                message,
                "Добавляйте поставщика через:\nАдмин меню → Поставщики → Добавить поставщика\n\nКомандный формат также поддерживается:\n/add_supplier TELEGRAM_ID Имя",
                business_connection_id,
            )
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id
            )
            return True

        name = " ".join(parts[2:]).strip()

        async with SessionLocal() as session:
            supplier = await add_supplier(session, supplier_id, name)
        await safe_send_message(
            bot,
            supplier_id,
            "Вы добавлены как поставщик. Откройте панель кнопкой ниже.",
            reply_markup=supplier_inline_menu_keyboard(),
        )

        await answer_message(
            bot,
            message,
            f"OK. Поставщик добавлен.\nID: {supplier.telegram_id}\nИмя: {supplier.name}",
            business_connection_id,
        )
        return True

    if text.startswith("/remove_supplier"):
        if len(parts) != 2:
            await answer_message(
                bot,
                message,
                "Формат:\n/remove_supplier TELEGRAM_ID",
                business_connection_id,
            )
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id
            )
            return True

        async with SessionLocal() as session:
            ok = await remove_supplier(session, supplier_id)

        await answer_message(
            bot,
            message,
            "OK. Поставщик выключен." if ok else "Поставщик не найден.",
            business_connection_id,
        )
        return True

    if text.startswith("/bind_supplier"):
        if len(parts) < 3:
            await answer_message(
                bot,
                message,
                "Формат:\n/bind_supplier TELEGRAM_ID товар_или_ключ",
                business_connection_id,
            )
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id
            )
            return True

        product_key = " ".join(parts[2:]).strip()
        async with SessionLocal() as session:
            result = await bind_supplier_to_product(session, supplier_id, product_key)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/unbind_supplier"):
        if len(parts) < 3:
            await answer_message(
                bot,
                message,
                "Формат:\n/unbind_supplier TELEGRAM_ID товар_или_ключ",
                business_connection_id,
            )
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(
                bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id
            )
            return True

        product_key = " ".join(parts[2:]).strip()
        async with SessionLocal() as session:
            result = await unbind_supplier_from_product(
                session, supplier_id, product_key
            )

        await answer_message(bot, message, result, business_connection_id)
        return True

    return False


async def is_supplier_user(user_id: int) -> bool:
    async with SessionLocal() as session:
        from app.models import Supplier
        from sqlalchemy import select

        result = await session.execute(
            select(Supplier).where(
                Supplier.telegram_id == user_id, Supplier.is_active.is_(True)
            )
        )
        return result.scalars().first() is not None


async def send_supplier_reply_buttons(bot: Bot, supplier_id: int) -> None:
    await safe_send_message(
        bot,
        supplier_id,
        "Кнопки поставщика включены ниже.",
        reply_markup=supplier_reply_keyboard(),
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


async def send_supplier_pending_panel(
    bot: Bot, message: Message, business_connection_id: str | None
) -> None:
    supplier_id = message.from_user.id
    async with SessionLocal() as session:
        pending_text, max_page = await supplier_pending_text(
            session, supplier_id, 0, SUPPLIER_PAGE_SIZE
        )
        rows, max_page = await get_supplier_pending_rows(
            session, supplier_id, 0, SUPPLIER_PAGE_SIZE
        )

    if rows:
        text = (
            pending_text
            + "\n\nВыберите заявку кнопкой ниже, потом отправьте номер или код сообщением."
        )
        markup = supplier_orders_keyboard(rows, 0, max_page)
    else:
        text = supplier_empty_panel_text()
        markup = supplier_inline_menu_keyboard()

    await send_supplier_role_panel(
        bot,
        message.chat.id,
        text,
        reply_markup=markup,
        business_connection_id=business_connection_id,
    )


async def process_supplier_command(
    bot: Bot, message: Message, business_connection_id: str | None
) -> bool:
    if not message.from_user:
        return False
    if not await is_supplier_user(message.from_user.id):
        return False

    text = (message.text or "").strip()

    if text in {"/commands", "📖 Команды"}:
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            supplier_commands_text(),
            reply_markup=supplier_commands_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text in {"/start", "/supplier"} or text == "🚚 Панель поставщика":
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            supplier_main_panel_text(),
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text in {"/work", "/pending"} or text in SUPPLIER_PANEL_TEXT_BUTTONS:
        await send_supplier_pending_panel(bot, message, business_connection_id)
        return True

    if text in {"🛍 Мои товары", "/supplier_products"}:
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            await supplier_products_text(message.from_user.id),
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text.startswith("/supplier_price"):
        raw = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            await set_supplier_product_price(message.from_user.id, raw),
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text in {"💼 Баланс", "/wallet"}:
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            await get_wallet_text(message.from_user.id),
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text in {"↗️ Вывод", "/withdraw_help"}:
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            "↗️ Вывод средств\n\nКомиссия вывода: 2.5 USDT.\nФормат: /withdraw СУММА USDT_АДРЕС\nПример: /withdraw 10 UQ...",
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text.startswith("/withdraw") and not text.startswith("/withdraw_done"):
        result = await create_withdrawal_request(message.from_user.id, text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else "")
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            result,
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text in {"📖 Помощь", "/supplier_help"}:
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            "🚚 Панель поставщика\n\n• Мои заказы — покупки ваших товаров.\n• Мои товары — список и цена.\n• Цена товара: /supplier_price ID ЦЕНА [ВАЛЮТА].\n• Вывод: /withdraw СУММА АДРЕС.",
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    if text == "/profile" or text == "👤 Мой профиль":
        async with SessionLocal() as session:
            profile_text = await supplier_profile_text(
                session, message.from_user.id, message.from_user.username
            )
        await send_supplier_role_panel(
            bot,
            message.chat.id,
            profile_text,
            reply_markup=supplier_inline_menu_keyboard(),
            business_connection_id=business_connection_id,
        )
        return True

    # ВАЖНО: неизвестные команды поставщика не должны попадать в обработчик номера/кода.
    # Иначе бот может отвечать «Не смог найти номер» или «Ожидающих заявок нет» на любую команду.
    if is_supplier_command_like_text(text):
        await send_supplier_unknown_command(bot, message, business_connection_id, text)
        return True

    return False


async def standalone_buyer_orders_text(user_id: int) -> str:
    from app.models import DigitalPurchase

    async with SessionLocal() as session:
        rows = list(
            (
                await session.scalars(
                    select(DigitalPurchase)
                    .where(DigitalPurchase.buyer_id == user_id)
                    .order_by(DigitalPurchase.id.desc())
                    .limit(20)
                )
            ).all()
        )
        if not rows:
            return (
                "🧾 <b>Мои заказы</b>\n\n"
                "Заказов пока нет. Откройте каталог, добавьте товар в корзину или купите сразу."
            )

        product_ids = {row.product_id for row in rows}
        products = list(
            (
                await session.scalars(
                    select(ShopProduct).where(ShopProduct.id.in_(product_ids))
                )
            ).all()
        )
        product_map = {row.id: row for row in products}

    labels = {
        "new": "🆕 создан",
        "creating_invoice": "⏳ создаётся счёт",
        "pending_payment": "💳 ожидает оплату",
        "paid": "✅ оплачен",
        "delivering": "📦 выдаётся",
        "delivered": "🎁 выдан",
        "delivery_failed": "⚠️ ошибка выдачи",
        "invoice_failed": "❌ ошибка счёта",
        "delivery_review_required": "🕵️ проверка выдачи",
        "awaiting_supplier": "👤 у поставщика",
        "fulfillment_problem": "⚠️ проблема выдачи",
    }
    lines = ["🧾 <b>Мои заказы</b>", "", "Последние покупки:", ""]
    for row in rows:
        product = product_map.get(row.product_id)
        name = product.name if product else f"Товар #{row.product_id}"
        created = row.created_at.strftime("%d.%m.%Y %H:%M") if row.created_at else "—"
        qty = int(getattr(row, "quantity", 1) or 1)
        lines.extend(
            [
                f"<b>#{row.id}</b> · {labels.get(row.status, row.status)}",
                f"├ 🛍 {name}",
                f"├ 🔢 Кол-во: {qty} шт.",
                f"├ 💰 {row.amount} {row.currency}",
                f"└ 🕒 {created}",
                "",
            ]
        )
    lines.append("Если заказ завис или не пришла выдача — напишите в поддержку из главного меню.")
    return "\n".join(lines).strip()


async def process_main_reply_button(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
) -> bool:
    """Главные кнопки магазина, администратора и поставщика."""
    if not message.from_user:
        return False

    text = (message.text or "").strip()
    user_id = message.from_user.id
    admin_access = await is_admin_user(user_id)
    supplier_access = await is_supplier_user(user_id)
    is_business_context = bool(business_connection_id)

    if admin_access and text in {"🤝 Партнёры", "Партнёры", "🚚 Поставщики"}:
        await answer_message(bot, message, "🤝 Партнёры и поставщики\n\nУправляйте доступом партнёров к товарам и категориям.", business_connection_id, reply_markup=admin_suppliers_keyboard())
        return True

    if admin_access and text in {"👥 Админы", "Админы", "👥 Админы и права"}:
        async with SessionLocal() as session:
            text_value = await list_admin_users_text(session, ADMIN_IDS)
        await answer_message(bot, message, text_value, business_connection_id, reply_markup=admin_admins_keyboard())
        return True

    if admin_access and text in {"📦 Управление товарами", "💰 Управление товарами", "Управление товарами"}:
        async with SessionLocal() as session:
            categories, products = await admin_catalog_overview(session)
        await answer_message(bot, message, admin_catalog_text(categories, products), business_connection_id, reply_markup=admin_catalog_keyboard(categories, products))
        return True

    if admin_access and text in {"💳 Способы оплаты", "💳 Оплата", "Способы оплаты", "Оплата"}:
        async with SessionLocal() as session:
            text_value = await payments_text(session)
        await answer_message(bot, message, text_value, business_connection_id, reply_markup=payments_keyboard())
        return True

    if admin_access and text in {"⚙️ Настройки", "Настройки", "⚙️ Админ меню"}:
        await answer_message(bot, message, await admin_settings_visual_text(), business_connection_id, reply_markup=admin_settings_visual_keyboard())
        return True

    if admin_access and text in {"📊 Статистика", "Статистика"}:
        async with SessionLocal() as session:
            text_value = await admin_statistics_visual_text(session)
        await answer_message(bot, message, text_value, business_connection_id, reply_markup=admin_hidden_keyboard())
        return True

    if admin_access and text in {"👁 Скрытые", "Скрытые"}:
        await answer_message(bot, message, "👁 Скрытые действия\n\nСлужебные настройки, заявки, выводы и права.", business_connection_id, reply_markup=admin_hidden_keyboard())
        return True

    if admin_access and text in {"🧩 Прокси", "Прокси"}:
        async with SessionLocal() as session:
            text_value, settings = await proxy_settings_text(session)
        await answer_message(bot, message, text_value, business_connection_id, reply_markup=admin_proxy_settings_keyboard(settings))
        return True

    if text in {"🚚 Я поставщик", "🚚 Панель поставщика"}:
        ADMIN_BROADCAST_V28.pop(user_id, None)
        if not supplier_access:
            await answer_message(
                bot,
                message,
                "Панель поставщика доступна только одобренным поставщикам. Чтобы подать заявку, нажмите «Стать партнёром».",
                business_connection_id,
                reply_markup=(await buyer_reply_keyboard_for_user(user_id) if not is_business_context else await buyer_inline_keyboard_for_user(user_id)),
            )
            return True
        await answer_message(bot, message, supplier_main_panel_text(), business_connection_id, reply_markup=supplier_reply_keyboard())
        await answer_message(bot, message, supplier_main_panel_text(), business_connection_id, reply_markup=supplier_inline_menu_keyboard())
        return True

    if text in {"📦 Мои заказы", "🛍 Мои товары", "💼 Баланс", "↗️ Вывод", "💵 Изменить цену", "📖 Помощь"} and supplier_access:
        ADMIN_BROADCAST_V28.pop(user_id, None)
        return await process_supplier_command(bot, message, business_connection_id)

    if text in {"🏠 Главное меню", "Главное меню", "🏠 Режим покупателя", "Режим покупателя"}:
        ADMIN_KEYBOARD_SENT.discard(user_id)
        await answer_message(
            bot,
            message,
            await get_main_page_text(),
            business_connection_id,
            reply_markup=(await buyer_inline_keyboard_for_user(user_id) if is_business_context else await buyer_reply_keyboard_for_user(user_id)),
        )
        return True

    if text in {"🛒 Товар", "🛒 Товары", "🛍 Каталог"}:
        async with SessionLocal() as session:
            categories = await list_categories(session)
            display_settings = await get_display_settings(session)
        await answer_message(bot, message, customer_home_text(), business_connection_id, reply_markup=customer_home_keyboard(categories, is_admin=admin_access, columns_count=display_settings.columns_count, search_enabled=display_settings.search_enabled))
        return True

    if text == "📱 Номера":
        async with SessionLocal() as session:
            products = await list_number_products(session)
        await answer_message(bot, message, "📱 Номера", business_connection_id, reply_markup=special_products_keyboard(products, back_callback="buyer:panel"))
        return True

    if text == "🛒 Корзина":
        async with SessionLocal() as session:
            rows = await get_cart_rows(session, user_id)
        await answer_message(bot, message, cart_text(rows), business_connection_id, reply_markup=cart_keyboard(rows))
        return True

    if text == "🧾 Мои заказы":
        orders_text, orders_markup = await buyer_orders_page(user_id, message.from_user.username, 0)
        await answer_message(bot, message, orders_text, business_connection_id, reply_markup=orders_markup)
        return True

    if text == "🤝 Стать партнёром":
        PARTNER_APPLICATION_WAIT.add(user_id)
        await answer_message(bot, message, "🤝 Стать партнёром\n\nОпишите, какие услуги хотите разместить в маркете.\nУкажите: название, цену, формат выдачи, сроки и условия.\n\nАдмины увидят заявку и смогут принять или отклонить её.\nДля отмены: отмена", business_connection_id, reply_markup=buyer_back_to_panel_keyboard())
        return True

    if text == "✉️ Обратная связь":
        BUYER_FEEDBACK_WAIT.add(user_id)
        await answer_message(bot, message, "✉️ Обратная связь\n\nОтправьте следующим сообщением ваш вопрос или описание проблемы.", business_connection_id, reply_markup=(await buyer_inline_keyboard_for_user(user_id) if is_business_context else await buyer_reply_keyboard_for_user(user_id)))
        return True

    if text == "📕 FAQ":
        await answer_message(bot, message, await get_faq_page_text(), business_connection_id, reply_markup=(await buyer_inline_keyboard_for_user(user_id) if is_business_context else await buyer_reply_keyboard_for_user(user_id)))
        return True

    if text == "📢 Рассылка":
        if not admin_access:
            await answer_message(bot, message, "У вас нет доступа.", business_connection_id)
            return True
        ADMIN_BROADCAST_V28[user_id] = {"step": "content"}
        await answer_message(bot, message, "📢 Создание рассылки\n\nОтправьте текст, фото, видео или документ. После этого откроется предпросмотр.", business_connection_id)
        return True

    if text in {"⚙️ Админ меню", "🛠 Админ"}:
        if not admin_access:
            await answer_message(bot, message, "У вас нет доступа к админ-панели.", business_connection_id, reply_markup=(await buyer_inline_keyboard_for_user(user_id) if is_business_context else await buyer_reply_keyboard_for_user(user_id)))
            return True
        ADMIN_KEYBOARD_SENT.add(user_id)
        await answer_message(bot, message, admin_panel_text(), business_connection_id, reply_markup=admin_main_reply_keyboard() if not is_business_context else admin_panel_keyboard())
        return True

    return False


async def process_command_message(
    bot: Bot, message: Message, business_connection_id: str | None
) -> None:
    if not message.from_user:
        return

    text = (message.text or "").strip()
    user_id = message.from_user.id
    username = message.from_user.username

    if await process_bug_report_command(bot, message, business_connection_id):
        return

    admin_access = await is_admin_user(user_id)
    if await process_extended_command(
        bot,
        message,
        business_connection_id,
        is_admin=admin_access,
        is_super_admin=is_admin(user_id),
    ):
        return

    if await process_admin_command(bot, message, business_connection_id):
        return

    if await process_supplier_command(bot, message, business_connection_id):
        return

    if text == "/shop":
        async with SessionLocal() as session:
            categories = await list_categories(session)
            display_settings = await get_display_settings(session)
        admin_access = await is_admin_user(user_id)
        await answer_message(
            bot,
            message,
            customer_home_text(),
            business_connection_id,
            reply_markup=customer_home_keyboard(
                categories,
                is_admin=admin_access,
                columns_count=display_settings.columns_count,
                search_enabled=display_settings.search_enabled,
            ),
        )
        return

    if text.startswith(
        (
            "/shop_sync",
            "/shop_categories",
            "/shop_add_category",
            "/shop_set_product",
            "/shop_set_price",
            "/shop_toggle",
        )
    ):
        if not await is_admin_user(user_id):
            await answer_message(
                bot, message, "Команда только для админа.", business_connection_id
            )
            return
        async with SessionLocal() as session:
            result = await process_admin_shop_command(session, text)
        await answer_message(
            bot,
            message,
            result or "Неизвестная команда магазина.",
            business_connection_id,
        )
        return

    if text.startswith("/start product_"):
        try:
            product_id = int(text.split("product_", 1)[1].split()[0])
        except (ValueError, IndexError):
            await answer_message(
                bot,
                message,
                "Некорректная ссылка на товар.",
                business_connection_id,
            )
            return

        async with SessionLocal() as session:
            product = await get_shop_product(session, product_id)

        if not product or not product.is_active:
            await answer_message(
                bot,
                message,
                "Товар не найден или скрыт.",
                business_connection_id,
            )
            return

        await answer_message(
            bot,
            message,
            product_text(product, None),
            business_connection_id,
            reply_markup=product_keyboard(product, ""),
        )
        return

    if text == "/start":
        async with SessionLocal() as session:
            order = await find_active_order_for_customer(session, user_id, username)

        if order and order.status == "waiting_service":
            await send_service_keyboard(
                bot, message, order.id, business_connection_id, page=0
            )
            return

        if await is_supplier_user(user_id):
            await send_supplier_pending_panel(bot, message, business_connection_id)
            return

        admin_access = await is_admin_user(user_id)

        # ReplyKeyboardMarkup не поддерживается для сообщений от имени
        # Telegram Business. Поэтому normal bot и Business используют
        # разные, явно разделённые интерфейсы.
        if business_connection_id:
            await send_buyer_role_panel(
                bot,
                message.chat.id,
                await get_main_page_text(),
                reply_markup=await buyer_inline_keyboard_for_user(user_id),
                business_connection_id=business_connection_id,
            )
        else:
            await answer_message(
                bot,
                message,
                await get_main_page_text(),
                business_connection_id=None,
                reply_markup=await buyer_reply_keyboard_for_user(user_id),
            )
        return

    if text == "👤 Мой профиль" or text == "/profile":
        if await is_admin_user(user_id):
            async with SessionLocal() as session:
                profile_text = await admin_profile_text(session, user_id, username)
            await answer_message(
                bot,
                message,
                profile_text,
                business_connection_id,
                reply_markup=admin_profile_keyboard(),
            )
            return

        if await is_supplier_user(user_id):
            async with SessionLocal() as session:
                profile_text = await supplier_profile_text(session, user_id, username)
            await send_supplier_role_panel(
                bot,
                message.chat.id,
                profile_text,
                reply_markup=supplier_inline_menu_keyboard(),
                business_connection_id=business_connection_id,
            )
            return

        async with SessionLocal() as session:
            profile_text = await buyer_profile_text(session, user_id, username)
        await send_buyer_role_panel(
            bot,
            message.chat.id,
            profile_text,
            reply_markup=await buyer_inline_keyboard_for_user(user_id),
            business_connection_id=business_connection_id,
        )
        return

    if text == "📦 Мои заказы" or text == "/orders":
        orders_text, orders_markup = await buyer_orders_page(user_id, username, 0)
        await send_buyer_role_panel(
            bot,
            message.chat.id,
            orders_text,
            reply_markup=orders_markup,
            business_connection_id=business_connection_id,
        )
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
            await answer_message(
                bot, message, "Команда только для админа.", business_connection_id
            )
            return
        async with SessionLocal() as session:
            status_text = await get_status_text(session)
        await answer_message(bot, message, status_text, business_connection_id)
        return

    if text == "/last_orders":
        if not await is_admin_user(user_id):
            await answer_message(
                bot, message, "Команда только для админа.", business_connection_id
            )
            return
        async with SessionLocal() as session:
            last_orders = await get_last_orders_text(session)
        await answer_message(bot, message, last_orders, business_connection_id)
        return

    if text.startswith("/set_customer"):
        if not await is_admin_user(user_id):
            await answer_message(
                bot, message, "Команда только для админа.", business_connection_id
            )
            return
        parts = text.split()
        if len(parts) != 3:
            await answer_message(
                bot,
                message,
                "Формат: /set_customer ID_ЗАКАЗА TELEGRAM_ID",
                business_connection_id,
            )
            return
        try:
            order_id = int(parts[1])
            telegram_id = int(parts[2])
        except ValueError:
            await answer_message(
                bot, message, "ID должны быть числами.", business_connection_id
            )
            return
        async with SessionLocal() as session:
            result_text = await set_customer_by_order_id(session, order_id, telegram_id)
        await answer_message(bot, message, result_text, business_connection_id)
        return

    await answer_message(
        bot,
        message,
        "Неизвестная команда. Напишите /ping или /admin",
        business_connection_id,
    )


async def proxy_settings_text(session) -> tuple[str, object]:
    settings = await get_proxy_shop_settings(session)
    markup = await get_proxy_markup_multiplier(session)
    countries = ", ".join(country_label(x) for x in settings.countries)
    periods = ", ".join(f"{x} дней" for x in settings.periods)
    proxy_type = "Выделенные" if settings.proxy_type == "dedicated" else "Общие"
    text = (
        "🌐 Прокси\n\n"
        "Управление автовыдачей, странами, сроками и ценой.\n"
        "Покупателю показывается финальная цена: база × наценка.\n\n"
        f"Автовыдача: {'🟢 включена' if settings.enabled else '🔴 выключена'}\n"
        f"├ Страны — {countries}\n"
        f"├ Сроки — {periods}\n"
        f"├ Тип — {proxy_type}\n"
        f"├ Количество — {settings.count}\n"
        f"├ IP — IPv{settings.ip_version}\n"
        f"└ Наценка — {multiplier_label(markup)}\n\n"
        "Базовую цену меняйте через /proxy_price, коэффициент — через /proxy_markup."
    )
    return text, settings


async def show_proxy_country_selection(
    bot: Bot, order_id: int, business_connection_id: str | None = None
) -> bool:
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
        reply_markup=buyer_proxy_country_keyboard(
            order_id, settings.countries, SUPPORTED_COUNTRIES
        ),
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
            await update_or_send(
                callback,
                "Сначала выберите страну.",
                reply_markup=buyer_proxy_country_keyboard(
                    order_id, settings.countries, SUPPORTED_COUNTRIES
                ),
            )
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


async def process_proxyline_order(
    bot: Bot, order_id: int, business_connection_id: str | None = None
) -> bool:
    """
    Автоматическая выдача Proxyline без поставщика.

    Поток:
    Legacy Order -> Proxyline flow. New store purchases use Crypto Pay fulfillment.
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
        if (
            selected_country not in settings.countries
            or selected_period not in settings.periods
        ):
            order.status = "problem"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await notify_admins(
                bot,
                f"Proxyline: выбранные параметры больше недоступны для заказа #{order.operation_id}.",
            )
            return False
        product_cfg = ProxylineProduct(
            country=selected_country,
            period=selected_period,
            count=settings.count,
            ip_version=settings.ip_version,
            proxy_type=settings.proxy_type,
            coupon=base_cfg.coupon,
        )

        if order.verification_code and order.status in {
            "code_sent_to_customer",
            "confirmed",
        }:
            logger.info(
                "PROXYLINE_SKIP_ALREADY_DELIVERED order_id=%s status=%s",
                order.id,
                order.status,
            )
            return True

        if not order.customer_telegram_id and not order.buyer_chat_id:
            order.status = "problem"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await notify_admins(
                bot,
                f"Proxyline: нет buyer_chat_id/customer_telegram_id для заказа #{order.operation_id}.",
            )
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
            "API автопрокси не настроен. Проверь ключ и включение в Render Environment.\n\n"
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
            "Ошибка автоматической покупки прокси.\n\n"
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
            "✅ Прокси-заказ выдан автоматически.\n\n"
            f"Заказ: #{order_operation_id}\n"
            f"Товар: {order_product_name}\n"
            f"Покупатель: {target_chat_id}",
        )
        logger.info(
            "PROXYLINE_DELIVERY_OK order_id=%s operation_id=%s",
            order_id,
            order_operation_id,
        )
        return True

    await notify_admins(
        bot,
        "Прокси куплен, но не удалось отправить покупателю.\n\n"
        f"Заказ: #{order_operation_id}\n"
        f"Товар: {order_product_name}\n"
        f"Покупатель: {target_chat_id}\n"
        f"Business ID: {target_business_id}\n\n"
        f"Прокси:\n{proxy_text}",
    )
    return False


async def process_legacy_external_shop_message_disabled(
    bot: Bot, message: Message
) -> None:
    text = message.text or ""
    data = extract_purchase_data(text)

    if not data:
        await notify_admins(
            bot,
            f"Shop-бот прислал сообщение, но покупку распарсить не удалось.\n\nТекст:\n{text}",
        )
        return

    current_business_id = get_business_id(message)

    async with SessionLocal() as session:
        order = await create_or_update_order_from_purchase(session, data)
        if current_business_id and not order.business_connection_id:
            order.business_connection_id = current_business_id
            await session.commit()
            await session.refresh(order)

    async with SessionLocal() as session:
        shop_product = await session.scalar(
            select(ShopProduct).where(ShopProduct.internal_key == order.product_id)
        )
        if shop_product and shop_product.price is not None:
            paid_amount = Decimal(str(order.amount or 0))
            expected_amount = Decimal(str(shop_product.price))
            paid_currency = (order.currency or "").upper()
            expected_currency = (shop_product.currency or "").upper()
            if paid_amount != expected_amount or paid_currency != expected_currency:
                db_order = await get_order_by_id(session, order.id)
                if db_order:
                    db_order.status = "problem"
                    db_order.updated_at = datetime.utcnow()
                    await session.commit()
                await notify_admins(
                    bot,
                    "⚠️ Цена или валюта заказа не совпадает с каталогом.\n\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"Товар: {order.product_name}\n"
                    f"Оплачено: {paid_amount} {paid_currency}\n"
                    f"Ожидалось: {expected_amount} {expected_currency}\n\n"
                    "Автовыдача остановлена.",
                )
                return

        explicit_provider = await get_product_provider(session, order.product_id)
        settings = await get_proxy_shop_settings(session)

    # Legacy route by internal product key.
    # Legacy-проверка по названию оставлена временно для обратной совместимости.
    route_to_proxyline = bool(
        explicit_provider
        and explicit_provider.enabled
        and explicit_provider.provider_type == "proxyline"
    )
    legacy_proxyline = explicit_provider is None and is_proxyline_product(
        order.product_name
    )

    if PROXYLINE_ENABLED and (route_to_proxyline or legacy_proxyline):
        async with SessionLocal() as session:
            db_order = await get_order_by_id(session, order.id)
            settings = await get_proxy_shop_settings(session)
            if db_order:
                db_order.status = (
                    "waiting_proxy_country" if settings.enabled else "problem"
                )
                db_order.service_name = selection_dump()
                # Proxyline flow is strictly in the normal bot chat.
                db_order.buyer_chat_id = (
                    db_order.customer_telegram_id or db_order.buyer_chat_id
                )
                db_order.business_connection_id = None
                db_order.updated_at = datetime.utcnow()
                await session.commit()
        await notify_admins(
            bot,
            (
                "OK. Покупка прокси обработана. Покупателю предложен выбор страны и срока.\n\n"
                if settings.enabled
                else "Раздел автопрокси отключён в админ-панели. Заказ переведён в problem.\n\n"
            )
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
                    "⚠️ Не удалось открыть выбор прокси в обычном боте.\n\n"
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


async def send_supplier_request_for_order(
    bot: Bot, order, business_connection_id: str | None
) -> bool:
    order_id_value = getattr(order, "id", order)
    actual_business_id = business_connection_id or getattr(
        order, "business_connection_id", None
    )

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
        await notify_admins(
            bot,
            f"Не смог отправить заявку поставщику {supplier.telegram_id} по заказу #{order.operation_id}",
        )
        return False

    async with SessionLocal() as session:
        supplier_request = await create_supplier_request(
            session, order_id_value, supplier.telegram_id, "number"
        )

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
            await set_supplier_request_message_id(
                session, supplier_request.id, sent_with_buttons.message_id
            )

    return True


async def accept_service_for_order(
    bot: Bot,
    message: Message | None,
    order_id: int,
    service_name: str,
    business_connection_id: str | None,
) -> None:
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
                await answer_message(
                    bot, message, "Заказ не найден.", business_connection_id
                )
            return

        if order.status != "waiting_service":
            closed_text = await get_text(
                session, "order_closed", "Заказ уже закрыт или уже в обработке."
            )
            if message:
                await answer_message(
                    bot,
                    message,
                    closed_text,
                    business_connection_id or order.business_connection_id,
                )
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
        service_accepted_text = await get_text(
            session, "service_accepted", "OK. Сервис принят. Ожидайте номер."
        )

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
            await answer_message(
                bot, message, "Заказ не найден после обновления.", actual_business_id
            )
        return

    ok = await send_supplier_request_for_order(bot, fresh_order, actual_business_id)

    if message:
        if ok:
            await answer_message(
                bot, message, service_accepted_text, actual_business_id
            )
        else:
            await answer_message(
                bot,
                message,
                "Сервис принят, но поставщик для этого товара не найден или недоступен. Админ уведомлён.",
                actual_business_id,
            )


async def handle_buyer_message(
    bot: Bot, message: Message, business_connection_id: str | None
) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    username = message.from_user.username
    text = (message.text or "").strip()

    async with SessionLocal() as session:
        contact_forbidden_text = await get_text(
            session,
            "contact_forbidden",
            "Нельзя отправлять контакты, username, ссылки или номера для связи.",
        )

    if not text:
        await temp_answer(
            bot,
            message,
            "Пришлите только название сервиса текстом или выберите кнопку. Фото/файлы поставщику не отправляются.",
            business_connection_id,
        )
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
        await send_buyer_role_panel(
            bot,
            message.chat.id,
            "🌍 › Выбор страны\n\nВыберите страну, в которой должен находиться прокси.",
            business_connection_id=business_connection_id,
            reply_markup=buyer_proxy_country_keyboard(
                order_id, settings.countries, SUPPORTED_COUNTRIES
            ),
        )
        return
    if order_id and status == "waiting_proxy_period":
        await send_buyer_role_panel(
            bot,
            message.chat.id,
            f"📅 › Выбор срока\n\nСтрана: {country_label(country or settings.countries[0])}\n\nВыберите срок аренды прокси.",
            business_connection_id=business_connection_id,
            reply_markup=buyer_proxy_period_keyboard(order_id, settings.periods),
        )
        return
    if order_id and status == "waiting_proxy_confirm":
        await send_buyer_role_panel(
            bot,
            message.chat.id,
            f"✅ › Подтверждение прокси\n\nСтрана: {country_label(country or '')}\nСрок: {period or '?'} дней",
            business_connection_id=business_connection_id,
            reply_markup=buyer_proxy_confirm_keyboard(order_id),
        )
        return

    async with SessionLocal() as session:
        order = await find_waiting_service_order_for_customer(
            session, user_id, username
        )

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
        await send_service_keyboard(
            bot,
            message,
            order.id,
            business_connection_id or order.business_connection_id,
            page=0,
        )
        await maybe_delete_message(bot, message)
        return

    await accept_service_for_order(
        bot,
        message,
        order.id,
        service.name,
        business_connection_id or order.business_connection_id,
    )
    await maybe_delete_message(bot, message)


async def handle_supplier_message(
    bot: Bot, message: Message, business_connection_id: str | None
) -> None:
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
            else None
        )

        if number_request:
            phone = extract_phone(text)
            if not phone:
                await answer_message(
                    bot,
                    message,
                    "Не смог найти номер. Пример: +79990000000",
                    business_connection_id,
                )
                return

            order = await get_order_by_id(session, number_request.order_id)
            if not order:
                await answer_message(
                    bot, message, "Заказ не найден.", business_connection_id
                )
                return

            if order.status == "confirmed":
                await answer_message(
                    bot, message, "Заказ уже закрыт.", business_connection_id
                )
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
                ok = bool(
                    await safe_send_message(
                        bot,
                        target_chat_id,
                        phone,
                        business_connection_id=target_business_id,
                        reply_markup=number_keyboard(order.id),
                        allow_normal_fallback=False,
                    )
                )

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
                    bot,
                    message,
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
                    order.id,
                    order.buyer_chat_id,
                    order.customer_telegram_id,
                    target_business_id,
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
                order.id,
                target_chat_id,
            )

            sent = await send_supplier_role_panel(
                bot,
                message.chat.id,
                "OK. Номер отправлен покупателю.",
                reply_markup=supplier_inline_menu_keyboard(),
                business_connection_id=business_connection_id,
            )
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
            else None
        )

        if code_request:
            code = extract_code(text)
            if not code:
                await answer_message(
                    bot,
                    message,
                    "Не смог найти код. Пример: 123456",
                    business_connection_id,
                )
                return

            order = await get_order_by_id(session, code_request.order_id)
            if not order:
                await answer_message(
                    bot, message, "Заказ не найден.", business_connection_id
                )
                return

            if order.status == "confirmed":
                await answer_message(
                    bot, message, "Заказ уже закрыт.", business_connection_id
                )
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
                ok = bool(
                    await send_buyer_role_panel(
                        bot,
                        target_chat_id,
                        delivery_text,
                        business_connection_id=target_business_id,
                        reply_markup=confirm_keyboard(order.id),
                    )
                )

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
                    order.id,
                    order.buyer_chat_id,
                    order.customer_telegram_id,
                    target_business_id,
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
                order.id,
                target_chat_id,
                not bool(target_business_id),
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
        await answer_message(
            bot,
            message,
            "Нет активного запроса для вас. Панель: /supplier",
            business_connection_id,
        )


async def route_message(bot: Bot, message: Message, is_business: bool) -> None:
    if not message.from_user:
        return

    me = await bot.me()
    sender = message.from_user
    user_id = sender.id
    username = (sender.username or "").replace("@", "").lower()
    text = (message.text or "").strip()
    business_connection_id = get_business_id(message) if is_business else None

    is_new_user = await touch_user(user_id, username or None)
    if is_new_user:
        full_name = " ".join(x for x in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if x) or None
        await notify_new_user(bot, user_id, username or None, full_name)

    logger.info(
        "HANDLED_TEXT is_business=%s from_id=%s username=%s is_bot=%s chat_id=%s business_id=%s text_len=%s",
        is_business,
        user_id,
        username,
        sender.is_bot,
        message.chat.id,
        business_connection_id,
        text[:200],
    )

    if is_business and business_connection_id:
        remember_business_context(message.chat.id, business_connection_id)

    if user_id == me.id:
        logger.info("IGNORED: own bot message")
        return

    if text in {"🚚 Я поставщик", "/supplier"}:
        if await is_supplier_user(user_id):
            await answer_message(bot, message, "🚚 Панель поставщика", business_connection_id, reply_markup=supplier_reply_keyboard())
            await send_supplier_menu(bot, message.chat.id, supplier_main_panel_text(), business_connection_id)
        else:
            await answer_message(bot, message, "Вы пока не поставщик. Нажмите «🤝 Стать партнёром» и отправьте заявку на модерацию.", business_connection_id, reply_markup=buyer_inline_menu_keyboard(is_admin=await is_admin_user(user_id)))
        return

    if text in {"💼 Кошелёк", "/wallet"}:
        await answer_message(bot, message, await get_wallet_text(user_id), business_connection_id, reply_markup=wallet_keyboard(is_supplier=await is_supplier_user(user_id)))
        return

    if text.lower().startswith(("@send ", "/send ", "/topup ")):
        parts = text.split()
        if len(parts) < 2:
            await answer_message(bot, message, "Формат: @send 10 или /topup 10 USDT", business_connection_id)
            return
        try:
            amount = parse_money(parts[1])
            currency = parts[2].upper() if len(parts) > 2 else "USDT"
            topup = await create_wallet_topup_invoice(user_id, username, amount, currency)
            await answer_message(
                bot,
                message,
                f"💼 Пополнение баланса\n\nСумма: {amount} {currency}\nПосле оплаты нажмите «Проверить пополнение».",
                business_connection_id,
                reply_markup=wallet_topup_invoice_keyboard(topup.invoice_url, topup.id),
            )
        except Exception as exc:
            logger.exception("WALLET_TOPUP_CREATE_FAILED user_id=%s", user_id)
            await answer_message(bot, message, f"Не удалось создать счёт: {exc}", business_connection_id)
        return

    if user_id in WALLET_TOPUP_WAIT and not text.startswith("/"):
        WALLET_TOPUP_WAIT.discard(user_id)
        if text.lower() in {"отмена", "cancel"}:
            await answer_message(bot, message, "Пополнение отменено.", business_connection_id, reply_markup=wallet_keyboard(is_supplier=await is_supplier_user(user_id)))
            return
        parts = text.split()
        try:
            amount = parse_money(parts[0])
            currency = parts[1].upper() if len(parts) > 1 else "USDT"
            topup = await create_wallet_topup_invoice(user_id, username, amount, currency)
            await answer_message(
                bot,
                message,
                f"💼 Пополнение баланса\n\nСумма: {amount} {currency}\nПосле оплаты нажмите «Проверить пополнение».",
                business_connection_id,
                reply_markup=wallet_topup_invoice_keyboard(topup.invoice_url, topup.id),
            )
        except Exception as exc:
            logger.exception("WALLET_TOPUP_CREATE_FAILED user_id=%s", user_id)
            await answer_message(bot, message, f"Не удалось создать счёт: {exc}", business_connection_id, reply_markup=wallet_keyboard(is_supplier=await is_supplier_user(user_id)))
        return

    if text.startswith("/withdraw") and not text.startswith("/withdraw_done"):
        if not await is_supplier_user(user_id):
            await answer_message(bot, message, "Вывод доступен только поставщикам.", business_connection_id)
            return
        result = await create_withdrawal_request(user_id, text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else "")
        await answer_message(bot, message, result, business_connection_id, reply_markup=wallet_keyboard(is_supplier=True))
        return

    if user_id in BUYER_CATALOG_SEARCH_WAIT and not text.startswith("/"):
        if await process_buyer_catalog_search(bot, message, business_connection_id):
            return

    if user_id in PROXY_COUNTRY_SEARCH_WAIT and not text.startswith("/"):
        if await process_proxy_country_search(bot, message, business_connection_id):
            return

    if user_id in CART_QUANTITY_WAIT and not text.startswith("/"):
        if await process_cart_quantity_input(bot, message, business_connection_id):
            return

    if user_id in PARTNER_APPLICATION_WAIT and not text.startswith("/"):
        if await process_partner_application_input(bot, message, business_connection_id):
            return

    if user_id in BUYER_FEEDBACK_WAIT and not text.startswith("/"):
        BUYER_FEEDBACK_WAIT.discard(user_id)
        async with SessionLocal() as session:
            report = BugReport(
                reporter_id=user_id,
                reporter_username=username,
                role=await get_user_role(user_id),
                text=text,
                status="new",
            )
            session.add(report)
            await session.commit()
            await session.refresh(report)
        await notify_admins(
            bot,
            "✉️ Новое обращение\n\n"
            f"ID: {report.id}\n"
            f"Пользователь: {user_id}\n"
            f"Username: @{username or 'нет'}\n\n"
            f"{text}",
        )
        await answer_message(
            bot,
            message,
            f"✅ Обращение #{report.id} отправлено. Администратор увидит его.",
            business_connection_id,
            reply_markup=(
                await buyer_reply_keyboard_for_user(user_id)
                if not business_connection_id
                else await buyer_inline_keyboard_for_user(user_id)
            ),
        )
        return


    if text.lower() in {"отмена", "cancel", "❌ отмена"}:
        had_state = False
        for store in (SHOP_ADMIN_WAIT, CATALOG_V25_STATE, ADMIN_BROADCAST_V28, ADMIN_TEXT_EDIT_WAIT, ADMIN_SUPPLIER_WAIT, CART_QUANTITY_WAIT, PROXY_COUNTRY_SEARCH_WAIT):
            if user_id in store:
                store.pop(user_id, None)
                had_state = True
        if user_id in PARTNER_APPLICATION_WAIT:
            PARTNER_APPLICATION_WAIT.discard(user_id)
            had_state = True
        if user_id in BUYER_FEEDBACK_WAIT:
            BUYER_FEEDBACK_WAIT.discard(user_id)
            had_state = True
        if user_id in WALLET_TOPUP_WAIT:
            WALLET_TOPUP_WAIT.discard(user_id)
            had_state = True
        if user_id in SUPPLIER_PRICE_WAIT:
            SUPPLIER_PRICE_WAIT.pop(user_id, None)
            had_state = True
        if had_state:
            target_markup = admin_main_reply_keyboard() if await is_admin_user(user_id) else (supplier_reply_keyboard() if await is_supplier_user(user_id) else await buyer_reply_keyboard_for_user(user_id))
            await answer_message(bot, message, "✅ Действие отменено.", business_connection_id, reply_markup=target_markup)
            return

    if user_id in SUPPLIER_PRICE_WAIT and not text.startswith("/"):
        SUPPLIER_PRICE_WAIT.pop(user_id, None)
        result = await set_supplier_product_price(user_id, text)
        await answer_message(bot, message, result, business_connection_id, reply_markup=supplier_reply_keyboard())
        await send_supplier_menu(bot, message.chat.id, supplier_main_panel_text(), business_connection_id)
        return

    main_reply_buttons = {
        "🛒 Товар",
        "🛒 Товары",
        "🛍 Каталог",
        "📱 Номера",
        "🛒 Корзина",
        "🧾 Мои заказы",
        "🤝 Стать партнёром",
        "✉️ Обратная связь",
        "📕 FAQ",
        "📦 Управление товарами",
        "🤝 Партнёры",
        "👥 Админы",
        "💰 Управление товарами",
        "💳 Оплата",
        "💳 Способы оплаты",
        "⚙️ Настройки",
        "📢 Рассылка",
        "👁 Скрытые",
        "🏠 Главное меню",
        "⚙️ Админ меню",
        "🛠 Админ",
        "🚚 Я поставщик",
        "🚚 Панель поставщика",
        "🛍 Мои товары",
        "💼 Баланс",
        "↗️ Вывод",
        "💵 Изменить цену",
        "📖 Помощь",
        "📊 Статистика",
        "🧩 Прокси",
    }
    if text in main_reply_buttons:
        # Нажатие главной кнопки отменяет незавершённый ввод старого мастера.
        CATALOG_V25_STATE.pop(user_id, None)
        SHOP_ADMIN_WAIT.pop(user_id, None)
        ADMIN_TEXT_EDIT_WAIT.pop(user_id, None)
        ADMIN_ADD_ADMIN_WAIT.discard(user_id)
        ADMIN_SUPPLIER_WAIT.pop(user_id, None)
        BUYER_CATALOG_SEARCH_WAIT.discard(user_id)
        PROXY_COUNTRY_SEARCH_WAIT.pop(user_id, None)
        CART_QUANTITY_WAIT.pop(user_id, None)
        PARTNER_APPLICATION_WAIT.discard(user_id)
        ADMIN_BROADCAST_V28.pop(user_id, None)
        if await process_main_reply_button(bot, message, business_connection_id):
            return

    if await is_admin_user(user_id) and not text.startswith("/"):
        # Сначала обрабатываем ввод, который ожидает админка:
        # ID нового администратора, цену, название товара и т.д.
        if await process_broadcast_v28_input(bot, message, business_connection_id):
            return
        if await process_catalog_v25_input(bot, message, business_connection_id):
            return
        if await process_shop_admin_pending_input(bot, message, business_connection_id):
            return
        if await process_admin_pending_input(bot, message, business_connection_id):
            return

        # После этого — обычные кнопки главного меню.
        if await process_main_reply_button(bot, message, business_connection_id):
            return

        logger.info("IGNORED: admin non-command message to avoid self-cycle")
        return

    if IGNORE_OTHER_BOTS and sender.is_bot:
        logger.info("IGNORED: other bot username=%s", username)
        return

    if text.startswith("/"):
        await process_command_message(bot, message, business_connection_id)
        return

    if await process_main_reply_button(bot, message, business_connection_id):
        return

    async with SessionLocal() as session:
        from app.models import Supplier
        from sqlalchemy import select

        result = await session.execute(
            select(Supplier).where(
                Supplier.telegram_id == user_id, Supplier.is_active.is_(True)
            )
        )
        supplier = result.scalars().first()

    if supplier:
        await handle_supplier_message(bot, message, business_connection_id)
        return

    await handle_buyer_message(bot, message, business_connection_id)


async def resend_problem_to_supplier(bot: Bot, order, problem_type: str) -> None:
    async with SessionLocal() as session:
        supplier = await find_supplier_for_order(session, order)

    if not supplier:
        await notify_admins(
            bot, f"Проблема по заказу #{order.operation_id}, но поставщик не найден."
        )
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
        problem_request = await create_supplier_request(
            session, order.id, supplier.telegram_id, request_type
        )

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
            await set_supplier_request_message_id(
                session, problem_request.id, ok.message_id
            )


async def handle_admin_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user or not await is_admin_user(callback.from_user.id):
        return False

    data = callback.data or ""

    required_cap = required_admin_capability(data)
    if required_cap and not await has_admin_capability(callback.from_user.id, required_cap, is_owner=await user_is_root_admin(callback.from_user.id)):
        await callback.answer("У вас нет доступа к этому разделу. Попросите ГА выдать право.", show_alert=True)
        return True

    if data == "admin:panel":
        await update_or_send(callback, admin_panel_text(), reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:main_settings":
        await update_or_send(callback, await admin_settings_visual_text(), reply_markup=admin_settings_visual_keyboard())
        await callback.answer()
        return True

    if data == "admin:edit_faq":
        ADMIN_TEXT_EDIT_WAIT[callback.from_user.id] = "faq_text"
        await update_or_send(callback, "📕 Изменение FAQ\n\nОтправьте новый текст FAQ одним сообщением.\nДля отмены напишите: отмена", reply_markup=simple_back_keyboard("admin:main_settings"))
        await callback.answer("Жду новый FAQ")
        return True

    if data == "admin:edit_main_page":
        ADMIN_TEXT_EDIT_WAIT[callback.from_user.id] = "main_page_text"
        await update_or_send(callback, "🏠 Изменение главной страницы\n\nОтправьте новый текст главной одним сообщением.\nДля отмены напишите: отмена", reply_markup=simple_back_keyboard("admin:main_settings"))
        await callback.answer("Жду текст главной")
        return True

    if data == "admin:status":
        async with SessionLocal() as session:
            text_value = await admin_statistics_visual_text(session)
        await update_or_send(callback, text_value, reply_markup=admin_hidden_keyboard())
        await callback.answer()
        return True

    if data == "admin:caps":
        if not await user_is_root_admin(callback.from_user.id):
            await callback.answer("Права админов может менять только ГА.", show_alert=True)
            return True
        async with SessionLocal() as session:
            from app.models import AdminUser
            admins = list((await session.scalars(select(AdminUser).where(AdminUser.is_active.is_(True)).order_by(AdminUser.created_at.desc()))).all())
            text_value = await admin_capabilities_text(session)
        await update_or_send(callback, text_value, reply_markup=admin_capabilities_keyboard(admins))
        await callback.answer()
        return True

    if data.startswith("admin:caps:user:"):
        if not await user_is_root_admin(callback.from_user.id):
            await callback.answer("Только ГА.", show_alert=True)
            return True
        admin_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            text_value = await admin_capability_user_text(session, admin_id)
            markup = await admin_capability_user_keyboard(session, admin_id)
        await update_or_send(callback, text_value, reply_markup=markup)
        await callback.answer()
        return True

    if data.startswith("admin:caps:toggle:"):
        if not await user_is_root_admin(callback.from_user.id):
            await callback.answer("Только ГА.", show_alert=True)
            return True
        _, _, _, admin_id_raw, cap = data.split(":", 4)
        admin_id = int(admin_id_raw)
        async with SessionLocal() as session:
            from app.v51_features import get_admin_caps, set_admin_caps
            caps = await get_admin_caps(session, admin_id)
            if cap in caps:
                caps.remove(cap)
            else:
                caps.add(cap)
            await set_admin_caps(session, admin_id, caps)
            text_value = await admin_capability_user_text(session, admin_id)
            markup = await admin_capability_user_keyboard(session, admin_id)
        await update_or_send(callback, text_value, reply_markup=markup)
        await callback.answer("Права обновлены")
        return True

    if data.startswith("admin:proxy:countries"):
        try:
            page = int(data.rsplit(":", 1)[1]) if data.count(":") >= 3 else 0
        except Exception:
            page = 0
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
        await update_or_send(callback, "🌍 Страны прокси\n\nВыберите страны, которые будут доступны покупателям.", reply_markup=admin_proxy_countries_keyboard(settings, SUPPORTED_COUNTRIES, page=page))
        await callback.answer()
        return True

    if data.startswith("admin:proxy:country:"):
        parts = data.split(":")
        code = parts[3] if len(parts) > 3 else ""
        page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
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
        await update_or_send(callback, "🌍 Страны прокси\n\nВыберите страны, которые будут доступны покупателям.", reply_markup=admin_proxy_countries_keyboard(settings, SUPPORTED_COUNTRIES, page=page))
        await callback.answer("Сохранено")
        return True

    if data == "admin:noop":
        await callback.answer()
        return True

    if data == "v25:catalog":
        async with SessionLocal() as session:
            categories, products = await admin_catalog_overview(session)
        await update_or_send(
            callback,
            admin_catalog_text(categories, products),
            reply_markup=admin_catalog_keyboard(categories, products),
        )
        await callback.answer()
        return True

    if data == "v25:add_product":
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "product_create",
            "step": "name",
            "data": {},
        }
        await update_or_send(
            callback,
            "📦 Создание товара\n\n"
            "Напишите название в чат с ботом (до 64 символов)\n\n"
            "💡 Рекомендация:\n"
            "• Делайте короче — название показывается на кнопке покупателю\n"
            "• Emoji отображаются ✅, форматирование текста — нет ❌",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data == "v25:add_category":
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "category_create",
            "step": "name",
            "data": {},
        }
        await update_or_send(
            callback,
            "📁 Создание категории\n\n"
            "Напишите название категории в чат с ботом (до 64 символов).",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:type:"):
        state = normalize_admin_state(
            CATALOG_V25_STATE,
            callback.from_user.id,
            CATALOG_V25_STATE.get(callback.from_user.id),
        )
        if not state or state.get("action") != "product_create":
            await callback.answer("Мастер устарел. Начните заново.", show_alert=True)
            return True
        product_type = data.rsplit(":", 1)[1]
        state["data"]["product_type"] = product_type
        state["step"] = "currency"
        await update_or_send(
            callback,
            f"📦 Название товара: {state['data']['name']}\n\n" "💰 Выберите валюту 👇",
            reply_markup=catalog_currency_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:currency:"):
        state = normalize_admin_state(
            CATALOG_V25_STATE,
            callback.from_user.id,
            CATALOG_V25_STATE.get(callback.from_user.id),
        )
        if not state:
            await callback.answer("Мастер устарел.", show_alert=True)
            return True
        currency = data.rsplit(":", 1)[1]
        if state.get("action") == "product_create":
            state["data"]["currency"] = currency
            state["step"] = "price"
            await update_or_send(
                callback,
                f"📦 Название: {state['data']['name']}\n"
                f"💰 Валюта: {currency}\n\n"
                "Напишите цену товара в чат с ботом\n\n"
                f"💡 Минимальная цена: 0.1 {currency}\n"
                "🔙 Кнопка «Назад» вернет к выбору валюты",
                reply_markup=price_back_keyboard(),
            )
        elif state.get("action") == "edit_currency":
            async with SessionLocal() as session:
                product = await session.get(ShopProduct, state["object_id"])
                product.currency = currency
                await session.commit()
                await session.refresh(product)
                count = await v25_stock_count(session, product.id)
            CATALOG_V25_STATE.pop(callback.from_user.id, None)
            await update_or_send(
                callback,
                v25_product_card_text(product, count),
                reply_markup=v25_product_card_keyboard(product),
            )
        await callback.answer()
        return True

    if data == "v25:wizard:back_name":
        state = normalize_admin_state(
            CATALOG_V25_STATE,
            callback.from_user.id,
            CATALOG_V25_STATE.get(callback.from_user.id),
        )
        if state:
            state["step"] = "name"
        await update_or_send(
            callback,
            "📦 Создание товара\n\n"
            "Напишите название в чат с ботом (до 64 символов).",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data == "v25:wizard:back_type":
        state = normalize_admin_state(
            CATALOG_V25_STATE,
            callback.from_user.id,
            CATALOG_V25_STATE.get(callback.from_user.id),
        )
        if state:
            state["step"] = "type"
            await update_or_send(
                callback,
                f"📝 Название: {state['data'].get('name','')}\n\nВыберите тип товара:",
                reply_markup=product_type_keyboard(),
            )
        await callback.answer()
        return True

    if data == "v25:wizard:back_currency":
        state = normalize_admin_state(
            CATALOG_V25_STATE,
            callback.from_user.id,
            CATALOG_V25_STATE.get(callback.from_user.id),
        )
        if state:
            state["step"] = "currency"
            await update_or_send(
                callback,
                "💰 Выберите валюту 👇",
                reply_markup=catalog_currency_keyboard(),
            )
        await callback.answer()
        return True

    if data == "v25:wizard:back_price":
        state = normalize_admin_state(
            CATALOG_V25_STATE,
            callback.from_user.id,
            CATALOG_V25_STATE.get(callback.from_user.id),
        )
        if state:
            if state.get("action") == "category_create":
                CATALOG_V25_STATE.pop(callback.from_user.id, None)
                await update_or_send(callback, "Создание категории отменено.", reply_markup=admin_panel_keyboard())
            else:
                state["step"] = "price"
                await update_or_send(
                    callback,
                    "Напишите цену товара в чат с ботом.",
                    reply_markup=price_back_keyboard(),
                )
        await callback.answer()
        return True

    if data == "v25:wizard:cancel":
        CATALOG_V25_STATE.pop(callback.from_user.id, None)
        SHOP_ADMIN_WAIT.pop(callback.from_user.id, None)
        await update_or_send(callback, "Действие отменено.", reply_markup=admin_panel_keyboard())
        await callback.answer("Отменено")
        return True

    if data.startswith("v25:product:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            if not product:
                await callback.answer("Товар не найден.", show_alert=True)
                return True
            count = await v25_stock_count(session, product.id)
        await update_or_send(
            callback,
            v25_product_card_text(product, count),
            reply_markup=v25_product_card_keyboard(product),
        )
        await callback.answer()
        return True

    if data.startswith("v25:give:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "give_product",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "🎁 Выдача товара пользователю\n\n"
            "Отправьте в чат с ботом Telegram ID или @username пользователя.\n\n"
            "💡 Для количественного товара будет выдана одна позиция из списка.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_content:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_content",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте новый контент: текст, ссылку, фото, видео или документ.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_name:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_name",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте новое название товара.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_price:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_price",
            "object_id": product_id,
        }
        await update_or_send(
            callback, "Отправьте новую цену.", reply_markup=content_back_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_description:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_description",
            "object_id": product_id,
        }
        await update_or_send(
            callback, "Отправьте описание товара.", reply_markup=content_back_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_note:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_note",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте примечание товара.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_photo:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_photo",
            "object_id": product_id,
        }
        await update_or_send(
            callback, "Отправьте фото товара.", reply_markup=content_back_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_video:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_video",
            "object_id": product_id,
        }
        await update_or_send(
            callback, "Отправьте видео товара.", reply_markup=content_back_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_currency:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_currency",
            "object_id": product_id,
        }
        await update_or_send(
            callback, "Выберите валюту.", reply_markup=catalog_currency_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("v25:edit_category:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            categories = list(
                (
                    await session.scalars(
                        select(ShopCategory).order_by(
                            ShopCategory.sort_order, ShopCategory.id
                        )
                    )
                ).all()
            )
        kb = InlineKeyboardBuilder()
        for category in categories:
            kb.button(
                text=f"{category.name}",
                callback_data=f"v25:set_category:{product_id}:{category.id}",
            )
        kb.button(
            text="📁 Без категории", callback_data=f"v25:set_category:{product_id}:0"
        )
        kb.button(
            text="⬅️ Назад", callback_data=f"v25:product:{product_id}", style="danger"
        )
        kb.adjust(1)
        await update_or_send(
            callback, "Выберите категорию товара.", reply_markup=kb.as_markup()
        )
        await callback.answer()
        return True

    if data.startswith("v25:set_category:"):
        _, _, product_id_raw, category_id_raw = data.split(":")
        product_id = int(product_id_raw)
        category_id = int(category_id_raw)
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            if not product:
                await callback.answer("Товар не найден", show_alert=True)
                return True
            product.category_id = category_id or None
            await session.commit()
            await session.refresh(product)
            count = await v25_stock_count(session, product.id)
        await update_or_send(
            callback,
            v25_product_card_text(product, count),
            reply_markup=v25_product_card_keyboard(product),
        )
        await callback.answer("Категория сохранена")
        return True

    if data.startswith("v25:stock:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "add_stock",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте новые позиции, каждую с новой строки.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:toggle_payment:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            if not product.payment_enabled and product.product_type == "quantity":
                available = await v25_stock_count(session, product.id)
                if available <= 0:
                    await callback.answer(
                        "Сначала добавьте позиции товара.", show_alert=True
                    )
                    return True
            target_enabled = not product.payment_enabled
            if target_enabled:
                errors = await validate_product_for_sale(product)
                if errors:
                    await callback.answer(
                        "Нельзя включить оплату:\n• " + "\n• ".join(errors),
                        show_alert=True,
                    )
                    return True
            product.payment_enabled = target_enabled
            product.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(product)
            count = await v25_stock_count(session, product.id)
        await update_or_send(
            callback,
            v25_product_card_text(product, count),
            reply_markup=v25_product_card_keyboard(product),
        )
        await callback.answer("Настройка оплаты изменена")
        return True

    if data.startswith("v25:toggle_visible:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            target_visible = not product.is_active
            if target_visible:
                errors = await validate_product_for_sale(product)
                if errors:
                    await callback.answer(
                        "Нельзя показать товар:\n• " + "\n• ".join(errors),
                        show_alert=True,
                    )
                    return True
            product.is_active = target_visible
            product.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(product)
            count = await v25_stock_count(session, product.id)
        await update_or_send(
            callback,
            v25_product_card_text(product, count),
            reply_markup=v25_product_card_keyboard(product),
        )
        await callback.answer("Статус товара изменен")
        return True

    if data.startswith("v34:fulfillment_menu:"):
        product_id = int(data.rsplit(":", 1)[1])
        await update_or_send(
            callback,
            "⚙️ Выберите способ выдачи товара.",
            reply_markup=fulfillment_keyboard(product_id),
        )
        await callback.answer()
        return True

    if data.startswith("v34:fulfillment:"):
        _, _, product_id_raw, fulfillment_type = data.split(":")
        product_id = int(product_id_raw)
        if fulfillment_type not in {"digital", "stock", "proxyline", "supplier", "number"}:
            await callback.answer("Неизвестный способ выдачи.", show_alert=True)
            return True
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            if not product:
                await callback.answer("Товар не найден.", show_alert=True)
                return True
            product.fulfillment_type = fulfillment_type
            product.product_type = "quantity" if fulfillment_type == "stock" else "static"
            product.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(product)
        await write_audit(
            callback.from_user.id,
            "product_fulfillment_changed",
            "product",
            product_id,
            {"fulfillment_type": fulfillment_type},
        )
        await update_or_send(
            callback,
            "✅ Способ выдачи сохранён.\n\n"
            "Для автопрокси задайте provider_key JSON через команду:\n"
            f"/set_provider_key {product_id} {{JSON}}\n\n"
            "Для поставщика или номера provider_key должен содержать Telegram ID поставщика.",
            reply_markup=advanced_keyboard(product_id),
        )
        await callback.answer("Сохранено")
        return True

    if data.startswith("v25:advanced:"):
        product_id = int(data.rsplit(":", 1)[1])
        await update_or_send(
            callback,
            "⚙️ Расширенные настройки",
            reply_markup=advanced_keyboard(product_id),
        )
        await callback.answer()
        return True

    if data.startswith("v25:payment_systems:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_payment_systems",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте платежные системы через запятую.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:payment_description:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_payment_description",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте описание платежа.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:old_price:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_old_price",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте старую цену числом.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:position:"):
        product_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "edit_product_position",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "Отправьте позицию товара числом.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:stats:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            count = await v25_stock_count(session, product.id)
        await update_or_send(
            callback,
            f"📊 Статистика товара\n\n"
            f"Просмотров: {product.views_count}\n"
            f"Продаж: {product.sales_count}\n"
            f"Выручка: {product.revenue_total} {product.currency}\n"
            f"Остаток: {count}",
            reply_markup=advanced_keyboard(product_id),
        )
        await callback.answer()
        return True

    if data.startswith("v25:delete_prompt:"):
        product_id = int(data.rsplit(":", 1)[1])
        await update_or_send(
            callback,
            "Удалить товар без возможности восстановления?",
            reply_markup=v25_delete_confirm_keyboard(product_id),
        )
        await callback.answer()
        return True

    if data.startswith("v25:delete_confirm:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            ok = await hard_delete_product(session, product_id)
        await write_audit(callback.from_user.id, "product_deleted", "product", product_id)
        async with SessionLocal() as session:
            categories, products = await admin_catalog_overview(session)
        await update_or_send(callback, "✅ Товар полностью удалён." if ok else "Товар не найден.", reply_markup=admin_catalog_keyboard(categories, products))
        await callback.answer("Товар удалён" if ok else "Не найден")
        return True

    if data.startswith("v25:category:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            category = await session.get(ShopCategory, category_id)
            products_in_category = list((await session.scalars(select(ShopProduct).where(ShopProduct.category_id == category_id, ShopProduct.is_deleted.is_(False)).order_by(ShopProduct.sort_order, ShopProduct.id))).all())
            count = len(products_in_category)
        text_value = category_card_text(category, count)
        if products_in_category:
            text_value += "\n\nТовары:\n" + "\n".join(f"• #{p.id} — {p.name} — {p.price} {p.currency}" for p in products_in_category[:25])
        await update_or_send(
            callback,
            text_value,
            reply_markup=category_card_keyboard(category.id, category.is_active),
        )
        await callback.answer()
        return True

    if data.startswith("v25:category_name:"):
        category_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "category_name",
            "object_id": category_id,
        }
        await update_or_send(
            callback,
            "Отправьте новое название категории.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:category_description:"):
        category_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "category_description",
            "object_id": category_id,
        }
        await update_or_send(
            callback,
            "Отправьте описание категории.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:category_photo:"):
        category_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "category_photo",
            "object_id": category_id,
        }
        await update_or_send(
            callback, "Отправьте фото категории.", reply_markup=content_back_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("v25:category_toggle:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            category = await session.get(ShopCategory, category_id)
            category.is_active = not category.is_active
            await session.commit()
            count = int(
                await session.scalar(
                    select(func.count(ShopProduct.id)).where(
                        ShopProduct.category_id == category_id
                    )
                )
                or 0
            )
        await update_or_send(
            callback,
            category_card_text(category, count),
            reply_markup=category_card_keyboard(category.id, category.is_active),
        )
        await callback.answer("Статус категории изменен")
        return True

    if data.startswith("v25:category_delete_prompt:"):
        category_id = int(data.rsplit(":", 1)[1])
        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ Удалить",
            callback_data=f"v25:category_delete_confirm:{category_id}",
            style="danger",
        )
        kb.button(
            text="⬅️ Отмена",
            callback_data=f"v25:category:{category_id}",
            style="danger",
        )
        kb.adjust(1)
        await update_or_send(
            callback,
            "Удалить категорию?\n\nТовары будут перемещены в «Без категории».",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return True

    if data.startswith("v25:category_delete_confirm:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            products = list(
                (
                    await session.scalars(
                        select(ShopProduct).where(
                            ShopProduct.category_id == category_id
                        )
                    )
                ).all()
            )
            for product in products:
                product.category_id = None
            category = await session.get(ShopCategory, category_id)
            if category:
                await session.delete(category)
            await session.commit()
            categories, products = await admin_catalog_overview(session)
        await update_or_send(
            callback,
            admin_catalog_text(categories, products),
            reply_markup=admin_catalog_keyboard(categories, products),
        )
        await callback.answer("Категория удалена")
        return True

    if data.startswith("v25:category_add_product:"):
        category_id = int(data.rsplit(":", 1)[1])
        CATALOG_V25_STATE[callback.from_user.id] = {
            "action": "product_create",
            "step": "name",
            "data": {"category_id": category_id},
        }
        await update_or_send(
            callback,
            "📦 Создание товара\n\nНапишите название товара.",
            reply_markup=content_back_keyboard(),
        )
        await callback.answer()
        return True

    if data == "v25:view_settings":
        async with SessionLocal() as session:
            settings = await get_display_settings(session)
        await update_or_send(
            callback,
            view_settings_text(settings),
            reply_markup=view_settings_keyboard(settings),
        )
        await callback.answer()
        return True

    if data.startswith("v25:columns:"):
        count = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            settings = await get_display_settings(session)
            settings.columns_count = count
            await session.commit()
        await update_or_send(
            callback,
            view_settings_text(settings),
            reply_markup=view_settings_keyboard(settings),
        )
        await callback.answer("Сохранено")
        return True

    if data == "v25:search_toggle":
        async with SessionLocal() as session:
            settings = await get_display_settings(session)
            settings.search_enabled = not settings.search_enabled
            await session.commit()
        await update_or_send(
            callback,
            view_settings_text(settings),
            reply_markup=view_settings_keyboard(settings),
        )
        await callback.answer("Сохранено")
        return True

    if data == "v25:sort":
        await update_or_send(
            callback, "Выберите порядок сортировки.", reply_markup=sort_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("v25:sort_set:"):
        mode = data.rsplit(":", 1)[1]
        async with SessionLocal() as session:
            settings = await get_display_settings(session)
            settings.sort_mode = mode
            await session.commit()
        await update_or_send(
            callback,
            view_settings_text(settings),
            reply_markup=view_settings_keyboard(settings),
        )
        await callback.answer("Сортировка сохранена")
        return True

    if data == "admin:shop:wizard_cancel":
        SHOP_ADMIN_WAIT.pop(callback.from_user.id, None)
        await update_or_send(
            callback, "Действие отменено.", reply_markup=admin_shop_keyboard()
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:wizard_currency:"):
        currency = data.rsplit(":", 1)[1].upper()
        state = normalize_admin_state(
            SHOP_ADMIN_WAIT,
            callback.from_user.id,
            SHOP_ADMIN_WAIT.get(callback.from_user.id),
        )
        if not state or state.get("action") != "product_wizard":
            await callback.answer("Мастер устарел", show_alert=True)
            return True
        state.setdefault("data", {})["currency"] = currency
        state["data"]["internal_key"] = int(datetime.utcnow().timestamp() * 1000000)
        state["step"] = "category"
        async with SessionLocal() as session:
            categories = await all_categories(session)
        await update_or_send(
            callback,
            "📦 Создание товара\n\nВыберите категорию.",
            reply_markup=admin_category_select_keyboard(categories),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:wizard_category:"):
        category_id = int(data.rsplit(":", 1)[1])
        state = normalize_admin_state(
            SHOP_ADMIN_WAIT,
            callback.from_user.id,
            SHOP_ADMIN_WAIT.get(callback.from_user.id),
        )
        if not state or state.get("action") != "product_wizard":
            await callback.answer("Мастер устарел", show_alert=True)
            return True
        values = state["data"]
        async with SessionLocal() as session:
            row = await session.scalar(
                select(ShopProduct).where(
                    ShopProduct.internal_key == values["internal_key"]
                )
            )
            if row is None:
                row = ShopProduct(
                    internal_key=values["internal_key"],
                    category_id=(category_id or None),
                    name=values["name"],
                    price=Decimal(values["price"]),
                    currency=values["currency"],
                    is_active=False,
                )
                session.add(row)
            else:
                row.category_id = category_id or None
                row.name = values["name"]
                row.price = Decimal(values["price"])
                row.currency = values["currency"]
                row.is_active = False
            await session.commit()
            await session.refresh(row)
        SHOP_ADMIN_WAIT.pop(callback.from_user.id, None)
        await update_or_send(
            callback,
            "✅ Черновик товара создан. Назначьте способ выдачи и нажмите «Показать».",
            reply_markup=admin_product_keyboard(row),
        )
        await callback.answer()
        return True

    if data == "admin:shop":
        async with SessionLocal() as session:
            categories, products = await admin_catalog_overview(session)
        await update_or_send(
            callback,
            admin_catalog_text(categories, products),
            reply_markup=admin_catalog_keyboard(categories, products),
        )
        await callback.answer()
        return True

    if data == "admin:shop:categories":
        async with SessionLocal() as session:
            rows = await all_categories(session)
        await update_or_send(
            callback,
            admin_categories_text(rows),
            reply_markup=admin_categories_keyboard(rows),
        )
        await callback.answer()
        return True

    if data == "admin:shop:products":
        async with SessionLocal() as session:
            rows = await all_products(session)
        await update_or_send(
            callback,
            admin_products_text(rows),
            reply_markup=admin_products_keyboard(rows),
        )
        await callback.answer()
        return True

    if data == "admin:shop:add_category":
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "category_wizard",
            "step": "name",
            "data": {},
        }
        await callback.answer()
        await update_or_send(
            callback,
            "➕ Категория\\n\\nОтправьте название. Можно вместе с эмодзи:\\n📱 Номера\\n\\nДля отмены: Отмена",
            reply_markup=admin_shop_keyboard(),
        )
        return True

    if data == "admin:shop:add_product":
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "product_wizard",
            "step": "name",
            "data": {},
        }
        await callback.answer()
        await update_or_send(
            callback,
            "➕ Товар\\n\\nФормат:\\nINTERNAL_ID | Название | Цена | Валюта\\n\\nПример:\\n613092 | Прокси IPv4 | 500 | RUB",
            reply_markup=admin_shop_keyboard(),
        )
        return True

    if data.startswith("admin:shop:add_product_to:"):
        category_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "add_product_to",
            "object_id": category_id,
            "step": None,
            "data": {},
        }
        await callback.answer()
        await update_or_send(
            callback,
            "➕ Товар в категорию\\n\\nФормат:\\nINTERNAL_ID | Название | Цена | Валюта",
            reply_markup=admin_shop_keyboard(),
        )
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
        await update_or_send(
            callback,
            admin_category_text(category, count),
            reply_markup=admin_category_keyboard(category, products),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:category_toggle:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            category = await toggle_category(session, category_id)
            products = await all_products(session, category_id)
            count, _ = await category_counts(session, category_id)
        await update_or_send(
            callback,
            admin_category_text(category, count),
            reply_markup=admin_category_keyboard(category, products),
        )
        await callback.answer("Статус категории изменён")
        return True

    if data.startswith("admin:shop:category_up:") or data.startswith(
        "admin:shop:category_down:"
    ):
        category_id = int(data.rsplit(":", 1)[1])
        delta = -10 if "category_up" in data else 10
        async with SessionLocal() as session:
            category = await move_category(session, category_id, delta)
            products = await all_products(session, category_id)
            count, _ = await category_counts(session, category_id)
        await update_or_send(
            callback,
            admin_category_text(category, count),
            reply_markup=admin_category_keyboard(category, products),
        )
        await callback.answer("Позиция изменена")
        return True

    if data.startswith("admin:shop:category_delete_prompt:"):
        category_id = int(data.rsplit(":", 1)[1])
        await update_or_send(
            callback,
            "Удалить категорию? Действие нельзя отменить.",
            reply_markup=confirm_delete_category_keyboard(category_id),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:category_delete_confirm:"):
        category_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            ok, result = await delete_category(session, category_id)
            rows = await all_categories(session)
        await callback.answer(result, show_alert=not ok)
        await update_or_send(
            callback,
            admin_categories_text(rows),
            reply_markup=admin_categories_keyboard(rows),
        )
        return True

    if data.startswith("admin:shop:category_name:"):
        category_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "category_name",
            "object_id": category_id,
        }
        await update_or_send(
            callback,
            "📝 Отправьте новое название категории.",
            reply_markup=admin_shop_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:category_desc:"):
        await callback.answer(
            "Описание категории будет добавлено после миграции базы.", show_alert=True
        )
        return True

    if data.startswith("admin:shop:product:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            text = (
                await product_admin_text(session, product)
                if product
                else "Товар не найден."
            )
        if not product:
            await callback.answer("Товар не найден", show_alert=True)
            return True
        await update_or_send(
            callback, text, reply_markup=admin_product_keyboard(product)
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_toggle:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            if not product:
                await callback.answer("Товар не найден", show_alert=True)
                return True
            if not product.is_active:
                missing = []
                if not product.name:
                    missing.append("название")
                if product.price is None:
                    missing.append("цена")
                if not product.currency:
                    missing.append("валюта")
                if missing:
                    await callback.answer(
                        "Нельзя опубликовать. Не настроено: " + ", ".join(missing),
                        show_alert=True,
                    )
                    return True
            product.is_active = not product.is_active
            await session.commit()
            await session.refresh(product)
            text = await product_admin_text(session, product)
        await update_or_send(
            callback, text, reply_markup=admin_product_keyboard(product)
        )
        await callback.answer(
            "Товар опубликован" if product.is_active else "Товар скрыт"
        )
        return True

    if data.startswith("admin:shop:product_name:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "product_name",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "📝 Отправьте новое название товара.",
            reply_markup=admin_shop_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_desc:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "product_desc",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "📝 Отправьте новое описание товара.",
            reply_markup=admin_shop_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_price:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "product_price",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "💵 Отправьте цену и валюту:\\n500 RUB",
            reply_markup=admin_shop_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_proxy:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            await bind_product_provider(
                session, product.internal_key, "proxyline", "proxyline", product.name
            )
            text = await product_admin_text(session, product)
        await update_or_send(
            callback, text, reply_markup=admin_product_keyboard(product)
        )
        await callback.answer("Автовыдача прокси назначена")
        return True

    if data.startswith("admin:shop:product_supplier:"):
        product_id = int(data.rsplit(":", 1)[1])
        SHOP_ADMIN_WAIT[callback.from_user.id] = {
            "action": "product_supplier",
            "object_id": product_id,
        }
        await update_or_send(
            callback,
            "🚚 Отправьте Telegram ID поставщика.",
            reply_markup=admin_shop_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_unbind:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            await unbind_product_provider(session, product.internal_key)
            text = await product_admin_text(session, product)
        await update_or_send(
            callback, text, reply_markup=admin_product_keyboard(product)
        )
        await callback.answer("Привязка удалена")
        return True

    if data.startswith("admin:shop:product_delete_prompt:"):
        product_id = int(data.rsplit(":", 1)[1])
        await update_or_send(
            callback,
            "Удалить товар? Действие нельзя отменить.",
            reply_markup=confirm_delete_product_keyboard(product_id),
        )
        await callback.answer()
        return True

    if data.startswith("admin:shop:product_delete_confirm:"):
        product_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            await hard_delete_product(session, product_id)
            rows = await all_products(session)
        await update_or_send(
            callback,
            admin_products_text(rows),
            reply_markup=admin_products_keyboard(rows),
        )
        await callback.answer("Товар удалён")
        return True

    if data == "admin:proxy":
        async with SessionLocal() as session:
            text, settings = await proxy_settings_text(session)
        await update_or_send(
            callback, text, reply_markup=admin_proxy_settings_keyboard(settings)
        )
        await callback.answer()
        return True

    if data == "admin:proxy:products":
        async with SessionLocal() as session:
            rows = await list_product_providers(session)
        if rows:
            text = "🔗 › Привязки товаров\n\n" + "\n".join(
                f"{'✅' if row.enabled else '⛔'} {row.internal_key} — {row.product_name or 'Товар'}"
                for row in rows
            )
        else:
            text = "🔗 › Привязки товаров\n\nПривязок пока нет. Создайте товар и назначьте способ выдачи."
        await update_or_send(
            callback, text, reply_markup=admin_proxy_products_keyboard()
        )
        await callback.answer()
        return True

    if data == "admin:proxy:products_help":
        text = (
            "🔗 › Привязка товара\n\n"
            "1. Выполните /products\n"
            "2. Скопируйте Product ID\n"
            "3. Для автопрокси: /bind_proxyline PRODUCT_ID\n"
            "4. Для поставщика: /bind_product_supplier PRODUCT_ID TELEGRAM_ID\n"
            "5. Отвязать: /unbind_product PRODUCT_ID"
        )
        await update_or_send(
            callback, text, reply_markup=admin_proxy_products_keyboard()
        )
        await callback.answer()
        return True

    if data == "admin:proxy:markup_help":
        async with SessionLocal() as session:
            markup = await get_proxy_markup_multiplier(session)
            settings = await get_proxy_shop_settings(session)
        text = (
            "💹 Наценка прокси\n\n"
            "Финальная цена для покупателя считается так:\n"
            "базовая цена товара × коэффициент наценки.\n\n"
            f"Сейчас: {multiplier_label(markup)}\n\n"
            "Команды:\n"
            "├ /proxy_markup 1.77 — изменить коэффициент\n"
            "├ /proxy_price 100 RUB — изменить базовую цену прокси-товаров\n"
            "└ /proxy_autofix 100 RUB — создать/обновить прокси-товары"
        )
        await update_or_send(callback, text, reply_markup=admin_proxy_settings_keyboard(settings))
        await callback.answer()
        return True

    if data == "admin:proxy:toggle":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            await save_proxy_setting(
                session, "proxy_shop_enabled", "0" if settings.enabled else "1"
            )
            text, settings = await proxy_settings_text(session)
        await update_or_send(
            callback, text, reply_markup=admin_proxy_settings_keyboard(settings)
        )
        await callback.answer("Настройка обновлена")
        return True

    if data == "admin:proxy:countries":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
        await update_or_send(
            callback,
            "🌍 › Доступные страны\n\nОтметьте страны, которые сможет выбирать покупатель.",
            reply_markup=admin_proxy_countries_keyboard(settings, SUPPORTED_COUNTRIES),
        )
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
                    await callback.answer(
                        "Нужно оставить хотя бы одну страну", show_alert=True
                    )
                    return True
                countries.remove(code)
            else:
                countries.append(code)
            await save_proxy_setting(
                session, "proxy_shop_countries", ",".join(countries)
            )
            settings = await get_proxy_shop_settings(session)
        await update_or_send(
            callback,
            "🌍 › Доступные страны\n\nОтметьте страны, которые сможет выбирать покупатель.",
            reply_markup=admin_proxy_countries_keyboard(settings, SUPPORTED_COUNTRIES),
        )
        await callback.answer("Сохранено")
        return True

    if data == "admin:proxy:periods":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
        await update_or_send(
            callback,
            "📅 › Доступные сроки\n\nОтметьте сроки аренды, доступные покупателю.",
            reply_markup=admin_proxy_periods_keyboard(settings, SUPPORTED_PERIODS),
        )
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
                    await callback.answer(
                        "Нужно оставить хотя бы один срок", show_alert=True
                    )
                    return True
                periods.remove(period)
            else:
                periods.append(period)
                periods.sort()
            await save_proxy_setting(
                session, "proxy_shop_periods", ",".join(map(str, periods))
            )
            settings = await get_proxy_shop_settings(session)
        await update_or_send(
            callback,
            "📅 › Доступные сроки\n\nОтметьте сроки аренды, доступные покупателю.",
            reply_markup=admin_proxy_periods_keyboard(settings, SUPPORTED_PERIODS),
        )
        await callback.answer("Сохранено")
        return True

    if data == "admin:proxy:type":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            new_type = "shared" if settings.proxy_type == "dedicated" else "dedicated"
            await save_proxy_setting(session, "proxy_shop_type", new_type)
            text, settings = await proxy_settings_text(session)
        await update_or_send(
            callback, text, reply_markup=admin_proxy_settings_keyboard(settings)
        )
        await callback.answer("Тип изменён")
        return True

    if data == "admin:proxy:count":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
        await update_or_send(
            callback,
            "📦 › Количество прокси\n\nСколько прокси покупать на один оплаченный заказ.",
            reply_markup=admin_proxy_count_keyboard(settings.count),
        )
        await callback.answer()
        return True

    if data in {"admin:proxy:count:plus", "admin:proxy:count:minus"}:
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            delta = 1 if data.endswith("plus") else -1
            count = max(1, min(100, settings.count + delta))
            await save_proxy_setting(session, "proxy_shop_count", str(count))
        await update_or_send(
            callback,
            "📦 › Количество прокси\n\nСколько прокси покупать на один оплаченный заказ.",
            reply_markup=admin_proxy_count_keyboard(count),
        )
        await callback.answer("Сохранено")
        return True

    if data == "admin:proxy:ip_version":
        async with SessionLocal() as session:
            settings = await get_proxy_shop_settings(session)
            value = 6 if settings.ip_version == 4 else 4
            await save_proxy_setting(session, "proxy_shop_ip_version", str(value))
            text, settings = await proxy_settings_text(session)
        await update_or_send(
            callback, text, reply_markup=admin_proxy_settings_keyboard(settings)
        )
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
            await callback.answer(
                "Только главный админ из ADMIN_IDS может добавлять доп.админов",
                show_alert=True,
            )
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
        await callback.answer(
            "Главный админ из ADMIN_IDS удаляется только через Render Environment",
            show_alert=True,
        )
        return True

    if data == "admin:remove_admin_list":
        if not is_admin(callback.from_user.id):
            await callback.answer(
                "Только главный админ из ADMIN_IDS может выключать доп.админов",
                show_alert=True,
            )
            return True
        async with SessionLocal() as session:
            rows = await get_admin_users(session, include_disabled=False)
        text = "➖ Удаление доп.админа\n\nВыберите админа кнопкой ниже.\n\nГлавных админов из ADMIN_IDS нельзя удалить кнопкой — их нужно менять в Render Environment."
        await update_or_send(
            callback, text, reply_markup=admin_remove_admin_keyboard(rows, ADMIN_IDS)
        )
        await callback.answer()
        return True

    if data.startswith("admin:remove_admin:"):
        if not is_admin(callback.from_user.id):
            await callback.answer(
                "Только главный админ из ADMIN_IDS может выключать доп.админов",
                show_alert=True,
            )
            return True
        try:
            target_admin_id = int(data.split(":")[2])
        except (ValueError, IndexError):
            await callback.answer("Некорректный ID", show_alert=True)
            return True
        if target_admin_id in ADMIN_IDS:
            await callback.answer(
                "Главный админ из ADMIN_IDS удаляется только через Render Environment",
                show_alert=True,
            )
            return True
        async with SessionLocal() as session:
            ok = await remove_admin_user(session, target_admin_id)
            rows = await get_admin_users(session, include_disabled=False)
            text = await list_admin_users_text(session, ADMIN_IDS)
        prefix = (
            "✅ Доп.админ выключен.\n\n"
            if ok
            else "⚠️ Доп.админ не найден или уже выключен.\n\n"
        )
        await update_or_send(
            callback,
            prefix + text,
            reply_markup=admin_remove_admin_keyboard(rows, ADMIN_IDS),
        )
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
            await update_or_send(
                callback,
                "⚠️ Проблемные заказы\n\nПроблемных заказов сейчас нет.",
                reply_markup=admin_back_keyboard(),
            )
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
            await update_or_send(
                callback,
                "🧾 Заказы\n\nЗаказов пока нет.",
                reply_markup=admin_back_keyboard(),
            )
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

        await update_or_send(
            callback,
            order_card_text(order),
            reply_markup=admin_order_card_keyboard(order.id),
        )
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

        await update_or_send(
            callback,
            result + "\n\n" + order_card_text(order),
            reply_markup=admin_order_card_keyboard(order.id),
        )
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
            ok, result, order, supplier = await admin_create_supplier_request_for_order(
                session, order_id, request_type
            )

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

        sent = await safe_send_message(
            bot, supplier.telegram_id, supplier_text, order.business_connection_id
        )
        if not sent:
            sent = await safe_send_message(bot, supplier.telegram_id, supplier_text)

        text = (
            f"{result}\n\n"
            f"Поставщик: {supplier.telegram_id}\n"
            f"Запрос: {'код' if request_type == 'code' else 'номер'}\n"
            f"Отправка поставщику: {'OK' if sent else 'не удалось'}\n\n"
            + order_card_text(order)
        )
        await update_or_send(
            callback, text, reply_markup=admin_order_card_keyboard(order.id)
        )
        await callback.answer("Повторный запрос создан")
        return True

    # Clean section navigation.
    if data == "admin:panel":
        if callback.from_user and callback.from_user.id not in ADMIN_KEYBOARD_SENT:
            try:
                await bot.send_message(callback.message.chat.id, "🛠 Панель администратора", reply_markup=admin_main_reply_keyboard())
                ADMIN_KEYBOARD_SENT.add(callback.from_user.id)
            except Exception:
                pass
        await update_or_send(
            callback, admin_panel_text(), reply_markup=admin_panel_keyboard()
        )
        await callback.answer()
        return True

    if data == "admin:withdrawals":
        await update_or_send(callback, await admin_withdrawals_text(), reply_markup=admin_hidden_keyboard())
        await callback.answer()
        return True

    if data == "admin:hidden":
        text = (
            "👁 Скрытые разделы\n\n"
            "Здесь собраны служебные действия, которые не нужны на главной панели:\n"
            "• заявки партнёров;\n"
            "• выводы поставщиков;\n"
            "• прокси-настройки;\n"
            "• номера и права админов;\n"
            "• зеркала бота.\n\n"
            "Все действия открываются кнопками ниже."
        )
        await update_or_send(callback, text, reply_markup=admin_hidden_keyboard())
        await callback.answer()
        return True

    if data == "admin:mirrors":
        await update_or_send(
            callback,
            "🤖 Зеркала бота\n\n"
            "Telegram не разрешает боту самому создавать нового бота — токен выдаётся только через BotFather.\n\n"
            "Как сделать зеркало:\n"
            "1. Создайте нового бота в BotFather.\n"
            "2. Создайте второй Render-сервис из этого же GitHub-репозитория.\n"
            "3. Укажите новый BOT_TOKEN и ту же DATABASE_URL.\n"
            "4. Запустите только один инстанс на каждый токен.\n\n"
            "Так зеркало будет работать с тем же магазином и базой.",
            reply_markup=admin_hidden_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:payment_methods":
        await update_or_send(
            callback,
            payment_methods_text(),
            reply_markup=payment_methods_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:payments":
        async with SessionLocal() as session:
            text_value = await payments_text(session)
        await update_or_send(
            callback,
            text_value,
            reply_markup=payments_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:store_settings":
        await update_or_send(
            callback,
            "⚙️ Настройки магазина\n\nВыберите нужный раздел.",
            reply_markup=store_settings_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:main_settings":
        await update_or_send(callback, await main_settings_text(), reply_markup=admin_hidden_keyboard())
        await callback.answer()
        return True

    if data == "admin:number_settings":
        await update_or_send(callback, await number_services_text(), reply_markup=admin_hidden_keyboard())
        await callback.answer()
        return True

    if data == "admin:broadcast":
        ADMIN_BROADCAST_V28[callback.from_user.id] = {"step": "content"}
        await update_or_send(
            callback,
            "📢 Создание рассылки\n\n"
            "Отправьте текст сообщения в чат с ботом.\n"
            "После этого откроется предварительный просмотр.",
            reply_markup=admin_back_keyboard(),
        )
        await callback.answer()
        return True

    if data == "v28:broadcast_confirm":
        state = ADMIN_BROADCAST_V28.get(callback.from_user.id)
        if not state or (not state.get("text") and not state.get("media_file_id")):
            await callback.answer("Рассылка не найдена.", show_alert=True)
            return True

        broadcast_text = state.get("text", "")
        broadcast_media_type = state.get("media_type")
        broadcast_media_file_id = state.get("media_file_id")
        async with SessionLocal() as session:
            from app.models import BotUser

            recipients = sorted(
                {
                    int(user_id)
                    for user_id in (
                        await session.scalars(
                            select(BotUser.telegram_id).where(
                                BotUser.is_active.is_(True)
                            )
                        )
                    ).all()
                    if user_id
                }
            )

        async with SessionLocal() as session:
            job = BroadcastJob(
                admin_id=callback.from_user.id,
                text=broadcast_text,
                media_type=broadcast_media_type,
                media_file_id=broadcast_media_file_id,
                status="queued",
                total_count=len(recipients),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)

        ADMIN_BROADCAST_V28.pop(callback.from_user.id, None)
        await write_audit(
            callback.from_user.id,
            "broadcast_started",
            "broadcast",
            job.id,
            {"recipients": len(recipients)},
        )
        asyncio.create_task(
            run_broadcast_v29(
                bot,
                callback.from_user.id,
                recipients,
                broadcast_text,
                job.id,
                broadcast_media_type,
                broadcast_media_file_id,
            )
        )
        await update_or_send(
            callback,
            "📢 Рассылка запущена в фоне.\n\n"
            f"Получателей: {len(recipients)}\n"
            "После завершения бот отправит итог отдельным сообщением.",
            reply_markup=admin_panel_keyboard(),
        )
        await callback.answer("Рассылка запущена")
        return True

    if data == "v28:uncategorized":
        async with SessionLocal() as session:
            products = list(
                (
                    await session.scalars(
                        select(ShopProduct)
                        .where(ShopProduct.category_id.is_(None))
                        .order_by(ShopProduct.sort_order, ShopProduct.id)
                    )
                ).all()
            )
        kb = InlineKeyboardBuilder()
        for product in products:
            kb.button(
                text=f"{'🟢' if product.is_active else '⚪'} {product.name}",
                callback_data=f"v25:product:{product.id}",
            )
        kb.button(text="⬅️ Назад", callback_data="v25:catalog", style="danger")
        kb.adjust(1)
        await update_or_send(
            callback,
            "📁 Товары без категории",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return True

    if data in {"admin:suppliers", "admin:partners"}:
        await update_or_send(
            callback,
            "🤝 Партнёры и поставщики\n\n"
            "Здесь можно добавить/удалить партнёра, выдать доступ к товару или категории и управлять привязками.",
            reply_markup=admin_suppliers_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:services":
        await update_or_send(
            callback,
            "🧩 Сервисы\n\nВыберите действие:",
            reply_markup=admin_services_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:lists":
        await update_or_send(
            callback,
            "📚 Листы сервисов\n\nВыберите действие:",
            reply_markup=admin_lists_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:texts":
        await update_or_send(
            callback,
            "✏️ Тексты\n\nМожно посмотреть текущие тексты или выбрать текст для изменения.",
            reply_markup=admin_texts_menu_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:settings":
        await update_or_send(
            callback,
            "⚙️ Настройки\n\nВыберите действие:",
            reply_markup=admin_settings_keyboard(),
        )
        await callback.answer()
        return True

    if data == "admin:add_supplier":
        ADMIN_SUPPLIER_WAIT[callback.from_user.id] = {"action": "add"}
        await update_or_send(
            callback,
            "➕ Добавление поставщика\n\n"
            "Пришлите одним сообщением Telegram ID и имя.\n\n"
            "Пример:\n123456789 Иван\n\n"
            "Для отмены напишите: отмена",
            reply_markup=admin_suppliers_cancel_keyboard(),
        )
        await callback.answer("Жду ID и имя")
        return True

    if data == "admin:remove_supplier":
        ADMIN_SUPPLIER_WAIT[callback.from_user.id] = {"action": "remove"}
        await update_or_send(
            callback,
            "🗑 Отключение поставщика\n\n"
            "Пришлите Telegram ID поставщика.\n\n"
            "Для отмены напишите: отмена",
            reply_markup=admin_suppliers_cancel_keyboard(),
        )
        await callback.answer("Жду Telegram ID")
        return True

    if data == "admin:bind_supplier":
        ADMIN_SUPPLIER_WAIT[callback.from_user.id] = {"action": "bind"}
        await update_or_send(
            callback,
            "🔗 Доступ партнёра к товару\n\n"
            "Пришлите Telegram ID партнёра и ID товара.\n\n"
            "Пример:\n123456789 25\n\n"
            "Для отмены напишите: отмена",
            reply_markup=admin_suppliers_cancel_keyboard(),
        )
        await callback.answer("Жду ID партнёра и товара")
        return True

    if data == "admin:bind_supplier_category":
        ADMIN_SUPPLIER_WAIT[callback.from_user.id] = {"action": "bind_category"}
        await update_or_send(
            callback,
            "📁 Доступ партнёра к категории\n\n"
            "Пришлите Telegram ID партнёра и ID категории.\n\n"
            "Пример:\n123456789 7\n\n"
            "Для отмены напишите: отмена",
            reply_markup=admin_suppliers_cancel_keyboard(),
        )
        await callback.answer("Жду ID партнёра и категории")
        return True

    if data == "admin:unbind_supplier":
        ADMIN_SUPPLIER_WAIT[callback.from_user.id] = {"action": "unbind"}
        await update_or_send(
            callback,
            "🔓 Отвязка товара от поставщика\n\n"
            "Пришлите Telegram ID поставщика и ID товара.\n\n"
            "Пример:\n123456789 25\n\n"
            "Для отмены напишите: отмена",
            reply_markup=admin_suppliers_cancel_keyboard(),
        )
        await callback.answer("Жду ID поставщика и товара")
        return True

    if data == "admin:supplier_action_cancel":
        ADMIN_SUPPLIER_WAIT.pop(callback.from_user.id, None)
        await update_or_send(
            callback,
            "🚚 Поставщики\n\nДействие отменено.",
            reply_markup=admin_suppliers_keyboard(),
        )
        await callback.answer("Отменено")
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
        if callback.from_user and callback.from_user.id not in ADMIN_KEYBOARD_SENT:
            try:
                await bot.send_message(callback.message.chat.id, "🛠 Панель администратора", reply_markup=admin_main_reply_keyboard())
                ADMIN_KEYBOARD_SENT.add(callback.from_user.id)
            except Exception:
                pass
        await update_or_send(
            callback, admin_panel_text(), reply_markup=admin_panel_keyboard()
        )
        await callback.answer()
        return True

    if data == "admin:main_settings":
        await update_or_send(callback, await main_settings_text(), reply_markup=admin_hidden_keyboard())
        await callback.answer()
        return True

    if data == "admin:number_settings":
        await update_or_send(callback, await number_services_text(), reply_markup=admin_hidden_keyboard())
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
        "admin:add_service_help": "Добавить сервис:\n/add_service Название\n\nПример:\n/add_service Telegram",
        "admin:service_emoji_help": "Эмодзи сервиса:\n/set_service_emoji Название | эмодзи\n\nПример:\n/set_service_emoji Telegram | 🔥",
        "admin:set_text_help": "Изменить текст:\n/set_text ключ | новый текст\n\nКлючи:\nthank_you\nservice_accepted\nservice_select\norder_not_found\ncontact_forbidden\norder_closed\nproblem_sent",
        "admin:list_help": "Листы сервисов:\n/add_list Название\n/list_add_service Лист | Сервис\n\nПоставщика можно привязать к листу:\n/bind_supplier TELEGRAM_ID НазваниеЛиста",
        "admin:commands": admin_panel_text(),
    }

    if data in help_texts:
        await update_or_send(
            callback, help_texts[data], reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return True

    return False


async def handle_supplier_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user or not await is_supplier_user(callback.from_user.id):
        return False

    ADMIN_BROADCAST_V28.pop(callback.from_user.id, None)
    CATALOG_V25_STATE.pop(callback.from_user.id, None)
    SHOP_ADMIN_WAIT.pop(callback.from_user.id, None)
    data = callback.data or ""

    if data == "supplier:panel":
        try:
            await bot.send_message(callback.message.chat.id, "🚚 Панель поставщика", reply_markup=supplier_reply_keyboard())
        except Exception:
            pass
        await update_or_send(
            callback,
            supplier_main_panel_text(),
            reply_markup=supplier_inline_menu_keyboard(),
        )
        await callback.answer()
        return True

    if data == "supplier:my_orders":
        await update_or_send(callback, await supplier_orders_text(callback.from_user.id), reply_markup=supplier_inline_menu_keyboard())
        await callback.answer()
        return True

    if data == "supplier:products":
        await update_or_send(callback, await supplier_products_text(callback.from_user.id), reply_markup=supplier_inline_menu_keyboard())
        await callback.answer()
        return True

    if data == "supplier:price_help":
        SUPPLIER_PRICE_WAIT[callback.from_user.id] = True
        await update_or_send(
            callback,
            "💵 Изменение цены\n\n"
            "Отправьте одним сообщением: ID товара, цена и валюта.\n\n"
            "Пример: 12 4.50 USD\n"
            "Для отмены напишите: отмена",
            reply_markup=supplier_inline_menu_keyboard(),
        )
        await callback.answer("Жду цену")
        return True

    if data == "supplier:wallet":
        await update_or_send(callback, await get_wallet_text(callback.from_user.id), reply_markup=supplier_inline_menu_keyboard())
        await callback.answer()
        return True

    if data == "supplier:withdraw_help":
        withdraw_text = (
            "↗️ Вывод средств\n\n"
            "Комиссия вывода: 2.5 USDT.\n"
            "Нажмите «Вывод» и отправьте сумму + адрес одним сообщением.\n\n"
            "Пример: 10 UQ...\n\n"
            "Если автовыплата CryptoBot включена, бот создаст чек автоматически."
        )
        await update_or_send(callback, withdraw_text, reply_markup=supplier_inline_menu_keyboard())
        await callback.answer()
        return True

    if data == "supplier:requests":
        await update_or_send(
            callback,
            supplier_requests_panel_text(),
            reply_markup=supplier_requests_menu_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("supplier:filter:"):
        _, _, mode, page_raw = data.split(":")
        page = int(page_raw)

        async with SessionLocal() as session:
            rows, max_page = await supplier_rows_by_filter(
                session, callback.from_user.id, mode, page, SUPPLIER_PAGE_SIZE
            )
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
            text = await supplier_profile_text(
                session, callback.from_user.id, callback.from_user.username
            )
        await update_or_send(
            callback, text, reply_markup=supplier_inline_menu_keyboard()
        )
        await callback.answer()
        return True

    if data == "supplier:commands":
        await update_or_send(
            callback,
            supplier_commands_text(),
            reply_markup=supplier_commands_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("supplier:take:"):
        request_id = int(data.split(":")[2])

        async with SessionLocal() as session:
            ok, result, request, order = await mark_supplier_request_in_progress(
                session, request_id
            )

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
        target_business_id = (
            order.business_connection_id or ADMIN_BUSINESS_CONNECTION_ID
        )
        if target_chat_id:
            await safe_send_message(
                bot,
                target_chat_id,
                buyer_text,
                business_connection_id=target_business_id,
            )

        await update_or_send(
            callback,
            supplier_text,
            reply_markup=supplier_selected_request_keyboard(
                request.id, request.request_type
            ),
        )
        await callback.answer("Заявка в работе")
        return True

    if data.startswith("supplier:answer:"):
        request_id = int(data.split(":")[2])

        async with SessionLocal() as session:
            ok, result, request, order = await mark_supplier_request_in_progress(
                session, request_id
            )

        if not ok:
            await callback.answer(
                result or "Заявка неактивна или уже обработана", show_alert=True
            )
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

        await update_or_send(
            callback,
            text,
            reply_markup=supplier_request_actions_keyboard(
                request.id, request.request_type
            ),
        )
        await callback.answer("Жду сообщение")
        return True

    if data.startswith("supplier:cancel_selection:"):
        request_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            request, order = await get_supplier_request_order(session, request_id)
            if not request or request.supplier_telegram_id != callback.from_user.id:
                await callback.answer("Заявка не найдена", show_alert=True)
                return True
            if request.status == "in_progress":
                request.status = "sent"
                await session.commit()
        await update_or_send(
            callback,
            "Выбор заявки отменён. Выберите другую заявку.",
            reply_markup=supplier_inline_menu_keyboard(),
        )
        await callback.answer("Выбор отменён")
        return True

    if data.startswith("supplier:pending:"):
        page = int(data.split(":")[2])
        async with SessionLocal() as session:
            rows, max_page = await get_supplier_pending_rows(
                session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE
            )
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

        if (
            not request
            or not order
            or request.supplier_telegram_id != callback.from_user.id
        ):
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
        await update_or_send(
            callback, text, reply_markup=supplier_wait_confirm_keyboard(mode, page)
        )
        await callback.answer()
        return True

    if data.startswith("supplier:reqf:"):
        parts = data.split(":")
        request_id = int(parts[2])
        mode = parts[3] if len(parts) > 3 else "active"
        page = int(parts[4]) if len(parts) > 4 else 0

        async with SessionLocal() as session:
            ok, msg, request, order = await select_supplier_request(
                session, callback.from_user.id, request_id
            )
            if mode == "pending":
                rows, max_page = await get_supplier_pending_rows(
                    session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE
                )
            else:
                rows, max_page = await supplier_rows_by_filter(
                    session, callback.from_user.id, mode, page, SUPPLIER_PAGE_SIZE
                )

        if not ok or not request or not order:
            await callback.answer(msg or "Заявка не найдена", show_alert=True)
            text = supplier_section_text(mode, len(rows), page, max_page)
            markup = (
                supplier_section_orders_keyboard(rows, mode, page, max_page)
                if rows
                else supplier_empty_section_keyboard(mode)
            )
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
        await update_or_send(
            callback,
            selected_text,
            reply_markup=supplier_request_actions_keyboard(
                request.id, request.request_type
            ),
        )
        await callback.answer("Заявка выбрана")
        return True

    if data.startswith("supplier:req:"):
        parts = data.split(":")
        request_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
        async with SessionLocal() as session:
            ok, msg, request, order = await select_supplier_request(
                session, callback.from_user.id, request_id
            )
            rows, max_page = await get_supplier_pending_rows(
                session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE
            )

        if not ok or not request or not order:
            await callback.answer(msg, show_alert=True)
            await update_or_send(
                callback,
                msg,
                reply_markup=supplier_orders_keyboard(rows, page, max_page),
            )
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
        await update_or_send(
            callback,
            selected_text,
            reply_markup=supplier_orders_keyboard(rows, page, max_page),
        )
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
        ADMIN_KEYBOARD_SENT.discard(callback.from_user.id)
        BUYER_CATALOG_SEARCH_WAIT.discard(callback.from_user.id)
        try:
            await bot.send_message(callback.message.chat.id, "🏠 Режим покупателя", reply_markup=await buyer_reply_keyboard_for_user(callback.from_user.id))
        except Exception:
            pass
        await update_or_send(
            callback,
            await get_main_page_text(),
            reply_markup=await buyer_inline_keyboard_for_user(user_id),
        )
        await callback.answer()
        return True

    if data == "buyer:active":
        async with SessionLocal() as session:
            order = await find_active_order_for_customer(session, user_id, username)
            text = format_buyer_active_order_text(order)
            order_id = order.id if order else None
            status = order.status if order else None
        await update_or_send(
            callback, text, reply_markup=buyer_active_order_keyboard(order_id, status)
        )
        await callback.answer()
        return True

    if data == "buyer:profile":
        async with SessionLocal() as session:
            text = await buyer_profile_text(session, user_id, username)
        await update_or_send(callback, text, reply_markup=buyer_back_keyboard())
        await callback.answer()
        return True

    if data == "buyer:wallet":
        await update_or_send(callback, await get_wallet_text(user_id), reply_markup=wallet_keyboard(is_supplier=await is_supplier_user(user_id)))
        await callback.answer()
        return True

    if data == "buyer:orders":
        text_value, markup = await buyer_orders_page(callback.from_user.id, callback.from_user.username, 0)
        await update_or_send(callback, text_value, reply_markup=markup)
        await callback.answer()
        return True

    if data.startswith("buyer:orders_page:"):
        try:
            page = int(data.rsplit(":", 1)[1])
        except Exception:
            page = 0
        text_value, markup = await buyer_orders_page(callback.from_user.id, callback.from_user.username, page)
        await update_or_send(callback, text_value, reply_markup=markup)
        await callback.answer()
        return True

    if data.startswith("buyer:order:"):
        order_id = int(data.split(":")[2])
        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)

        if not order:
            await update_or_send(
                callback,
                "🧾 Заказ не найден.",
                reply_markup=buyer_empty_section_keyboard("buyer:orders"),
            )
            await callback.answer("Заказ не найден", show_alert=True)
            return True

        allowed_by_id = (
            order.customer_telegram_id == user_id or order.buyer_chat_id == user_id
        )
        allowed_by_username = bool(
            username
            and order.customer_username
            and order.customer_username.lower().replace("@", "")
            == username.lower().replace("@", "")
        )
        if not (allowed_by_id or allowed_by_username):
            await callback.answer("Это не ваш заказ", show_alert=True)
            return True

        await update_or_send(
            callback,
            buyer_order_card_text(order),
            reply_markup=buyer_order_card_keyboard(order.id, order.status),
        )
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
        allowed = (
            order.customer_telegram_id == user_id or order.buyer_chat_id == user_id
        )
        if not allowed and username and order.customer_username:
            allowed = order.customer_username.lower().replace("@", "") == username
        if not allowed:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return True
        provider = await get_product_provider(session, order.product_id)
        is_explicit_proxy = bool(
            provider and provider.enabled and provider.provider_type == "proxyline"
        )
        if not is_explicit_proxy and not is_proxyline_product(order.product_name):
            await callback.answer("Этот товар не привязан к автопрокси", show_alert=True)
            return True
        if not settings.enabled:
            await callback.answer(
                "Автовыдача прокси временно отключена", show_alert=True
            )
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
                await update_or_send(
                    callback,
                    "Сначала выберите страну.",
                    reply_markup=buyer_proxy_country_keyboard(
                        order.id, settings.countries, SUPPORTED_COUNTRIES
                    ),
                )
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
                "После подтверждения бот купит прокси автоматически и выдаст его в этом чате."
            )
            await update_or_send(
                callback, text, reply_markup=buyer_proxy_confirm_keyboard(order.id)
            )
            await callback.answer("Срок выбран")
            return True

        if action == "back_country":
            order.status = "waiting_proxy_country"
            order.service_name = selection_dump()
            order.updated_at = datetime.utcnow()
            await session.commit()
            await update_or_send(
                callback,
                "🌍 › Выбор страны\n\nВыберите страну, в которой должен находиться прокси.",
                reply_markup=buyer_proxy_country_keyboard(
                    order.id, settings.countries, SUPPORTED_COUNTRIES
                ),
            )
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
            await update_or_send(
                callback,
                f"📅 › Выбор срока\n\nСтрана: {country_label(country)}\n\nВыберите срок аренды прокси.",
                reply_markup=buyer_proxy_period_keyboard(order.id, settings.periods),
            )
            await callback.answer()
            return True

        if action == "confirm":
            country, period = selection_load(order.service_name)
            if not country or not period:
                await callback.answer("Сначала выберите страну и срок", show_alert=True)
                return True
            if order.status in {
                "proxy_processing",
                "code_sent_to_customer",
                "confirmed",
            }:
                await callback.answer(
                    "Заказ уже обрабатывается или выдан", show_alert=True
                )
                return True
            order.status = "proxy_processing"
            order.updated_at = datetime.utcnow()
            await session.commit()
            business_id = order.business_connection_id or get_callback_business_id(
                callback
            )

    await update_or_send(
        callback,
        "⏳ › Покупка прокси\n\nЗапрос отправлен. Не нажимайте кнопку повторно.",
        reply_markup=buyer_back_keyboard(),
    )
    await callback.answer("Покупаю прокси…")
    await process_proxyline_order(bot, order_id, business_id)
    return True


async def check_button_cooldown(callback: CallbackQuery, action: str) -> bool:
    if not callback.from_user:
        return True

    async with SessionLocal() as session:
        cooldown_seconds = await get_cooldown_seconds(
            session, f"button:{action}", BUTTON_COOLDOWN_SECONDS
        )
        ok, remaining = await check_cooldown(
            session,
            callback.from_user.id,
            f"button:{action}",
            cooldown_seconds,
        )

    if not ok:
        await callback.answer(
            "Слишком часто. Попробуйте ещё раз через пару секунд.", show_alert=False
        )
        return False

    return True


async def handle_callback(bot: Bot, callback: CallbackQuery) -> None:
    data = callback.data or ""

    # Админы и поставщики работают без cooldown.
    # Для покупателей оставляем защиту только на рискованных действиях: проверка оплаты,
    # подтверждение/повторная выдача и оформление заказа. Навигация работает без задержек.
    cooldown_prefixes = (
        "payment:check",
        "wallet:check",
        "buyer:checkout",
        "buyer:pxbuy",
        "proxy:confirm",
        "confirm_success",
        "code_sent",
        "number_invalid",
        "code_invalid",
    )
    if data and data.startswith(cooldown_prefixes):
        if not (callback.from_user and (await is_admin_user(callback.from_user.id) or await is_supplier_user(callback.from_user.id))):
            if not await check_button_cooldown(callback, data.split(":")[0]):
                return

    logger.info(
        "HANDLED_CALLBACK from_id=%s data=%s",
        callback.from_user.id if callback.from_user else None,
        data,
    )

    if data.startswith("market:"):
        handled = await handle_marketplace_callback(
            bot, callback, is_admin=bool(callback.from_user and await is_admin_user(callback.from_user.id))
        )
        if handled:
            return

    if data == "wallet:topup_help":
        await update_or_send(
            callback,
            "💼 Пополнение баланса\n\nВыберите сумму или нажмите «Своя сумма». Также можно написать в чат: @send 10",
            reply_markup=wallet_topup_amounts_keyboard(),
        )
        await callback.answer()
        return

    if data == "wallet:topup_custom":
        if callback.from_user:
            WALLET_TOPUP_WAIT.add(callback.from_user.id)
        await update_or_send(callback, "Введите сумму пополнения. Например: 10 или 10 USDT. Для отмены: отмена", reply_markup=wallet_keyboard(is_supplier=bool(callback.from_user and await is_supplier_user(callback.from_user.id))))
        await callback.answer("Жду сумму")
        return

    if data.startswith("wallet:topup_quick:"):
        if not callback.from_user:
            await callback.answer()
            return
        try:
            _, _, amount_raw, currency = data.split(":", 3)
            amount = parse_money(amount_raw)
            topup = await create_wallet_topup_invoice(callback.from_user.id, callback.from_user.username, amount, currency)
            await update_or_send(
                callback,
                f"💼 Пополнение баланса\n\nСумма: {amount} {currency}\nПосле оплаты нажмите «Проверить пополнение».",
                reply_markup=wallet_topup_invoice_keyboard(topup.invoice_url, topup.id),
            )
        except Exception as exc:
            logger.exception("WALLET_TOPUP_QUICK_FAILED user_id=%s", callback.from_user.id)
            await update_or_send(callback, f"Не удалось создать счёт: {exc}", reply_markup=wallet_keyboard(is_supplier=await is_supplier_user(callback.from_user.id)))
        await callback.answer()
        return

    if data.startswith("wallet_topup:check:"):
        if not callback.from_user:
            await callback.answer()
            return
        try:
            topup_id = int(data.split(":")[2])
            result = await check_wallet_topup(bot, topup_id, callback.from_user.id)
        except Exception as exc:
            logger.exception("WALLET_TOPUP_CHECK_FAILED user_id=%s data=%s", callback.from_user.id, data)
            result = f"Не удалось проверить пополнение: {exc}"
        await update_or_send(callback, result, reply_markup=wallet_keyboard(is_supplier=await is_supplier_user(callback.from_user.id)))
        await callback.answer()
        return

    if data.startswith("proxy:"):
        handled = await handle_proxy_callback(bot, callback)
        if handled:
            return

    if data.startswith(("admin:", "v25:", "v28:")):
        handled = await handle_admin_callback(bot, callback)
        if handled:
            return
        if not callback.from_user or not await is_admin_user(callback.from_user.id):
            await callback.answer("Команда только для админа", show_alert=True)
        else:
            logger.warning(
                "UNHANDLED_ADMIN_CALLBACK user_id=%s data=%s",
                callback.from_user.id,
                data,
            )
            await callback.answer(
                "Эта кнопка устарела. Откройте админ-меню заново.",
                show_alert=True,
            )
        return

    if data.startswith("supplier:"):
        handled = await handle_supplier_callback(bot, callback)
        if handled:
            return

        logger.warning(
            "STALE_OR_FORBIDDEN_SUPPLIER_CALLBACK user_id=%s data=%s",
            callback.from_user.id if callback.from_user else None,
            data,
        )
        await callback.answer(
            "Кнопка устарела или у вас нет доступа. Откройте /supplier.",
            show_alert=True,
        )
        return

    if data == "buyer:proxy_catalog":
        await update_or_send(
            callback,
            proxy_categories_text(),
            reply_markup=proxy_categories_keyboard(),
        )
        await callback.answer()
        return

    if data.startswith("buyer:proxycat:"):
        category_key = data.rsplit(":", 1)[1]
        countries = await available_proxyline_countries()
        await update_or_send(
            callback,
            proxy_category_title(category_key)
            + "\n\n🌍 <b>Шаг 1 из 3 — страна</b>\n"
            "Выберите страну прокси или нажмите 🔎 поиск.",
            reply_markup=countries_keyboard(category_key, countries, page=0),
        )
        await callback.answer()
        return

    if data.startswith("buyer:pxsearch:"):
        category_key = data.rsplit(":", 1)[1]
        PROXY_COUNTRY_SEARCH_WAIT[callback.from_user.id] = category_key
        await update_or_send(
            callback,
            proxy_category_title(category_key)
            + "\n\n🔎 <b>Поиск страны</b>\n"
            "Напишите страну сообщением: например <b>Россия</b>, <b>США</b>, <b>Германия</b>, <b>NL</b> или <b>TR</b>.",
            reply_markup=buyer_back_keyboard(),
        )
        await callback.answer("Введите название страны")
        return

    if data.startswith("buyer:pxcountries:"):
        _, _, category_key, page_raw = data.split(":")
        countries = await available_proxyline_countries()
        await update_or_send(
            callback,
            proxy_category_title(category_key)
            + "\n\n🌍 <b>Шаг 1 из 3 — страна</b>\n"
            "Выберите страну прокси или нажмите 🔎 поиск.",
            reply_markup=countries_keyboard(
                category_key,
                countries,
                page=int(page_raw),
            ),
        )
        await callback.answer()
        return

    if data.startswith("buyer:pxcountry:"):
        _, _, category_key, country_code, page_raw = data.split(":")
        async with SessionLocal() as session:
            products = await list_proxy_products_by_category(session, category_key)
            proxy_markup = await get_proxy_markup_multiplier(session)
        product = next(
            (
                row for row in products
                if row.payment_enabled
                and row.is_active
                and not row.is_deleted
            ),
            None,
        )
        if product is None:
            await callback.answer(
                "Нет активного прокси-товара. Админу: выполните /proxy_autofix 100 RUB, затем /proxy_markup 1.77.",
                show_alert=True,
            )
            return

        countries = dict(await available_proxyline_countries())
        country_name = country_display(country_code, countries.get(country_code, country_code.upper()))
        await update_or_send(
            callback,
            f"{proxy_category_title(category_key)}\n\n"
            "📅 <b>Шаг 2 из 3 — срок</b>\n"
            f"Страна: {country_name}\n"
            "Выберите срок аренды:",
            reply_markup=periods_keyboard(
                category_key,
                country_code,
                product.id,
                apply_proxy_markup(product.price, proxy_markup),
                product.currency,
            ),
        )
        await callback.answer()
        return

    if data.startswith("buyer:pxperiod:"):
        _, _, category_key, country_code, months_raw, product_id_raw = data.split(":")
        months = int(months_raw)
        product_id = int(product_id_raw)
        if months not in PROXY_PERIODS:
            await callback.answer("Некорректный срок.", show_alert=True)
            return

        async with SessionLocal() as session:
            product = await session.get(ShopProduct, product_id)
            proxy_markup = await get_proxy_markup_multiplier(session)
            if product and product.fulfillment_type != "proxyline":
                # Товар выбран именно через прокси-витрину, значит выдача должна идти через proxy-provider.
                product.fulfillment_type = "proxyline"
                await session.commit()
        if (
            product is None
            or product.is_deleted
            or not product.is_active
            or not product.payment_enabled
            or product.fulfillment_type != "proxyline"
        ):
            await callback.answer(
                "Тариф временно недоступен.",
                show_alert=True,
            )
            return

        countries = dict(await available_proxyline_countries())
        country_name = country_display(country_code, countries.get(country_code, country_code.upper()))
        amount = (
            apply_proxy_markup(product.price, proxy_markup) * Decimal(months)
        ).quantize(Decimal("0.01"))
        provider_key = build_provider_key(
            product.provider_key,
            country_code,
            months,
            category_key,
        )
        try:
            purchase, payment = await create_purchase_invoice(
                callback.from_user.id,
                callback.from_user.username,
                product.id,
                amount_override=amount,
                provider_key_override=provider_key,
                active_suffix=f"{country_code}:{months}",
                description_override=(
                    f"{product.name}, {country_name}, {months} мес."
                ),
            )
        except (PaymentConfigurationError, PaymentValidationError) as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        await update_or_send(
            callback,
            "🌐 <b>Заказ прокси создан</b>\n\n"
            f"Тип: {proxy_category_title(category_key)}\n"
            f"Страна: {country_name}\n"
            f"Срок: {months} мес.\n"
            f"Сумма: <b>{amount} {product.currency}</b>\n\n"
            "🪙 Оплатите счёт через CryptoBot. После оплаты прокси будет выдан автоматически.",
            reply_markup=invoice_keyboard(
                payment.invoice_url,
                purchase.id,
                product.id,
            ),
        )
        await callback.answer("Счёт создан")
        return


    if data == "buyer:cart":
        async with SessionLocal() as session:
            rows = await get_cart_rows(session, callback.from_user.id)
        await update_or_send(callback, cart_text(rows), reply_markup=cart_keyboard(rows))
        await callback.answer()
        return

    if data.startswith("buyer:cart_add:"):
        product_id = int(data.rsplit(":", 1)[1])
        try:
            async with SessionLocal() as session:
                await add_to_cart(session, callback.from_user.id, product_id, 1)
                rows = await get_cart_rows(session, callback.from_user.id)
        except Exception as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await update_or_send(callback, cart_text(rows), reply_markup=cart_keyboard(rows))
        await callback.answer("Добавлено в корзину")
        return

    if data.startswith("buyer:cart_inc:") or data.startswith("buyer:cart_dec:"):
        parts = data.split(":")
        action = parts[1].replace("cart_", "")
        item_id = int(parts[-1])
        async with SessionLocal() as session:
            rows = await get_cart_rows(session, callback.from_user.id)
            current = next((item for item, _ in rows if item.id == item_id), None)
            if current:
                qty = int(current.quantity or 1) + (1 if action == "inc" else -1)
                await set_cart_quantity(session, callback.from_user.id, item_id, qty)
            rows = await get_cart_rows(session, callback.from_user.id)
        await update_or_send(callback, cart_text(rows), reply_markup=cart_keyboard(rows))
        await callback.answer()
        return

    if data.startswith("buyer:cart_custom:"):
        item_id = int(data.rsplit(":", 1)[1])
        CART_QUANTITY_WAIT[callback.from_user.id] = item_id
        await update_or_send(
            callback,
            "🔢 <b>Своё количество</b>\n\nОтправьте числом, сколько штук нужно. Например: 3\nЧтобы удалить позицию — отправьте 0.\nДля отмены: отмена",
            reply_markup=buyer_back_to_panel_keyboard(),
        )
        await callback.answer("Введите количество")
        return

    if data == "buyer:cart_clear":
        async with SessionLocal() as session:
            await clear_cart(session, callback.from_user.id)
            rows = await get_cart_rows(session, callback.from_user.id)
        await update_or_send(callback, cart_text(rows), reply_markup=cart_keyboard(rows))
        await callback.answer("Корзина очищена")
        return

    if data == "buyer:cart_checkout":
        async with SessionLocal() as session:
            rows = await get_cart_rows(session, callback.from_user.id)
        if not rows:
            await callback.answer("Корзина пуста", show_alert=True)
            return
        if len(rows) > 5:
            await callback.answer("За один раз можно оформить до 5 позиций.", show_alert=True)
            return
        created = []
        try:
            for item, product in rows:
                if not product or not product.is_active or not product.payment_enabled:
                    continue
                qty = int(item.quantity or 1)
                if qty > 1 and product.fulfillment_type in {"stock", "number"}:
                    await callback.answer(
                        "Для складских товаров и номеров количество больше 1 оформляйте отдельными покупками.",
                        show_alert=True,
                    )
                    return
                amount = Decimal(str(product.price or 0)) * Decimal(qty)
                purchase, payment = await create_purchase_invoice(
                    callback.from_user.id,
                    callback.from_user.username,
                    product.id,
                    amount_override=amount,
                    active_suffix=f"cart:{item.id}:{qty}",
                    description_override=f"{product.name} × {qty}",
                    quantity=qty,
                )
                created.append((product, qty, purchase, payment))
        except (PaymentConfigurationError, PaymentValidationError) as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        async with SessionLocal() as session:
            await clear_cart(session, callback.from_user.id)
        if len(created) == 1:
            product, qty, purchase, payment = created[0]
            await update_or_send(
                callback,
                f"✅ <b>Счёт создан</b>\n\n{product.name} × {qty}\nСумма: <b>{purchase.amount} {purchase.currency}</b>",
                reply_markup=invoice_keyboard(payment.invoice_url, purchase.id, product.id),
            )
        else:
            await update_or_send(
                callback,
                f"✅ Создано счетов: {len(created)}. Ссылки отправлены отдельными сообщениями.",
                reply_markup=buyer_inline_menu_keyboard(is_admin=await is_admin_user(callback.from_user.id)),
            )
            for product, qty, purchase, payment in created:
                await callback.message.answer(
                    f"💳 {product.name} × {qty}\nСумма: {purchase.amount} {purchase.currency}",
                    reply_markup=invoice_keyboard(payment.invoice_url, purchase.id, product.id),
                )
        await callback.answer("Счёт создан")
        return

    if data == "buyer:noop":
        await callback.answer(
            "Действие недоступно. Обновите меню командой /start.", show_alert=True
        )
        return

    if data.startswith("buyer:proxygroup:"):
        legacy_key = data.rsplit(":", 1)[1]
        key_map = {
            "mtproxy": "mtproxy",
            "premium": "premium",
            "standard": "standard",
            "rotation": "residential",
            "residential": "residential",
        }
        category_key = key_map.get(legacy_key, legacy_key)
        countries = await available_proxyline_countries()
        await update_or_send(
            callback,
            proxy_category_title(category_key)
            + "\n\nВыберите страну прокси:",
            reply_markup=countries_keyboard(category_key, countries, page=0),
        )
        await callback.answer()
        return

    if data.startswith("buyer:proxypackage:"):
        await callback.answer(
            "Выберите актуальный тариф из раздела «Прокси».",
            show_alert=True,
        )
        return

    if data == "buyer:number_catalog":
        async with SessionLocal() as session:
            products = await list_number_products(session)
        await update_or_send(
            callback,
            special_catalog_text("📱 Номера", len(products)),
            reply_markup=special_products_keyboard(products, "buyer:panel"),
        )
        await callback.answer()
        return

    if data == "buyer:shop":
        BUYER_CATALOG_SEARCH_WAIT.discard(callback.from_user.id)
        async with SessionLocal() as session:
            categories = await list_categories(session)
            display_settings = await get_display_settings(session)
        admin_access = bool(
            callback.from_user and await is_admin_user(callback.from_user.id)
        )
        await update_or_send(
            callback,
            customer_home_text(),
            reply_markup=customer_home_keyboard(
                categories,
                is_admin=admin_access,
                columns_count=display_settings.columns_count,
                search_enabled=display_settings.search_enabled,
            ),
        )
        await callback.answer()
        return

    if data == "buyer:search":
        BUYER_CATALOG_SEARCH_WAIT.add(callback.from_user.id)
        await update_or_send(
            callback,
            "🔍 Поиск товара\n\nНапишите название или часть описания товара.",
            reply_markup=buyer_back_to_panel_keyboard(),
        )
        await callback.answer()
        return

    if data.startswith("buyer:shopcat:"):
        parts = data.split(":")
        try:
            category_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0
        except (ValueError, IndexError):
            await callback.answer("Некорректная категория", show_alert=True)
            return

        async with SessionLocal() as session:
            categories = await list_categories(session)
            category = next(
                (row for row in categories if row.id == category_id),
                None,
            )
            products = await list_general_products(session, category_id)
            display_settings = await get_display_settings(session)

        if not category:
            await callback.answer("Категория не найдена", show_alert=True)
            return

        products = sort_products(products, display_settings.sort_mode)
        category_photo = category.photo_file_id or category_asset(category.name)
        preview_lines = []
        for row in products[:10]:
            price = f" — {row.price} {row.currency}" if row.price is not None else ""
            preview_lines.append(f"• {row.name}{price}")
        category_text = category_caption(category)
        if preview_lines:
            category_text += "\n\nТовары в категории:\n" + "\n".join(preview_lines)
        await show_visual_card(
            callback,
            category_text,
            reply_markup=products_keyboard(
                products,
                category_id,
                display_settings.columns_count,
                page=page,
            ),
            photo=category_photo,
        )
        await callback.answer()
        return

    if data.startswith("buyer:walletbuy:"):
        product_id = int(data.rsplit(":", 1)[1])
        try:
            purchase, wallet_payment = await create_wallet_payment(
                buyer_id=callback.from_user.id,
                buyer_username=callback.from_user.username,
                product_id=product_id,
            )
        except (PaymentConfigurationError, PaymentValidationError) as exc:
            await callback.answer(str(exc), show_alert=True)
            return True
        except Exception:
            logger.exception(
                "CREATE_WALLET_PAYMENT_FAILED product_id=%s buyer_id=%s",
                product_id,
                callback.from_user.id,
            )
            await callback.answer(
                "Не удалось создать оплату на кошелёк. Администратор уже может проверить ошибку.",
                show_alert=True,
            )
            return True
        await update_or_send(
            callback,
            (
                "💼 Оплата на кошелёк\n\n"
                f"Заказ: #{purchase.id}\n"
                f"Сумма: {wallet_payment.amount} {wallet_payment.currency}\n"
                f"Адрес: {wallet_payment.address}\n"
                f"Комментарий/Memo: {wallet_payment.memo}\n\n"
                "После поступления платежа внешний монитор может подтвердить его через /wallet/webhook. "
                f"Админ также может подтвердить вручную: /wallet_confirm {wallet_payment.id}"
            ),
            reply_markup=wallet_payment_keyboard(wallet_payment.id),
        )
        await callback.answer("Реквизиты созданы")
        return True

    if data.startswith("buyer:buy:"):
        product_id = int(data.rsplit(":", 1)[1])
        try:
            purchase, payment = await create_purchase_invoice(
                buyer_id=callback.from_user.id,
                buyer_username=callback.from_user.username,
                product_id=product_id,
            )
        except (PaymentConfigurationError, PaymentValidationError) as exc:
            await callback.answer(str(exc), show_alert=True)
            return True
        except Exception:
            logger.exception(
                "CREATE_CRYPTO_INVOICE_FAILED product_id=%s buyer_id=%s",
                product_id,
                callback.from_user.id,
            )
            await callback.answer(
                "Не удалось создать счёт. Администратор уже может проверить ошибку.",
                show_alert=True,
            )
            return True

        await update_or_send(
            callback,
            "💳 Счёт создан\n\n"
            f"Заказ: #{purchase.id}\n"
            f"Сумма: {purchase.amount} {purchase.currency}\n\n"
            "После оплаты нажмите «Проверить оплату». "
            "Webhook также обработает платёж автоматически.",
            reply_markup=invoice_keyboard(payment.invoice_url, purchase.id),
        )
        await callback.answer()
        return True

    if data.startswith("wallet:check:"):
        payment_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            from app.models import WalletPayment
            wallet_payment = await session.get(WalletPayment, payment_id)
            if not wallet_payment:
                await callback.answer("Платёж не найден", show_alert=True)
                return True
            if wallet_payment.buyer_id != callback.from_user.id:
                await callback.answer("Это не ваш платёж.", show_alert=True)
                return True
            status = wallet_payment.status
        text = "Оплата подтверждена." if status == "paid" else "Оплата пока ожидается."
        await update_or_send(
            callback,
            f"💼 Проверка оплаты на кошелёк\n\n{text}",
            reply_markup=wallet_payment_keyboard(payment_id),
        )
        await callback.answer()
        return True

    if data.startswith("payment:check:"):
        purchase_id = int(data.rsplit(":", 1)[1])
        try:
            result_text = await check_purchase_payment(
                bot, purchase_id, callback.from_user.id
            )
        except Exception as exc:
            logger.exception("PAYMENT_MANUAL_CHECK_FAILED purchase_id=%s", purchase_id)
            await callback.answer(f"Проверка не выполнена: {exc}", show_alert=True)
            return True
        await update_or_send(
            callback,
            f"💳 Проверка оплаты\n\n{result_text}",
            reply_markup=payment_result_keyboard(),
        )
        await callback.answer()
        return True

    if data.startswith("payment:back:"):
        purchase_id = int(data.rsplit(":", 1)[1])
        async with SessionLocal() as session:
            from app.models import DigitalPurchase

            purchase = await session.get(DigitalPurchase, purchase_id)
            if purchase and purchase.buyer_id != callback.from_user.id:
                await callback.answer("Это не ваша покупка.", show_alert=True)
                return True
            product = (
                await session.get(ShopProduct, purchase.product_id)
                if purchase
                else None
            )
            provider = (
                await get_product_provider(session, product.internal_key)
                if product
                else None
            )
        if not product:
            await callback.answer("Товар не найден", show_alert=True)
            return True
        provider_type = provider.provider_type if provider else None
        # Фото категории не подставляется в карточку товара.
        # Если нужна картинка товара — задайте её самому товару.
        fallback_photo = None
        await show_visual_card(
            callback,
            product_caption(product, provider_type),
            reply_markup=product_keyboard(product, ""),
            photo=product.photo_file_id or fallback_photo,
            video_file_id=product.video_file_id,
        )
        await callback.answer()
        return True

    if data.startswith("buyer:shopproduct:"):
        try:
            product_id = int(data.split(":")[2])
        except (ValueError, IndexError):
            await callback.answer("Некорректный товар", show_alert=True)
            return
        async with SessionLocal() as session:
            product = await get_shop_product(session, product_id)
            provider = (
                await get_product_provider(session, product.internal_key)
                if product
                else None
            )
            if product:
                product.views_count = int(product.views_count or 0) + 1
                await session.commit()
                await session.refresh(product)
        if not product or not product.is_active:
            await callback.answer("Товар недоступен", show_alert=True)
            return
        provider_type = provider.provider_type if provider else None
        # Фото категории не подставляется в карточку товара.
        # Если нужна картинка товара — задайте её самому товару.
        fallback_photo = None
        await show_visual_card(
            callback,
            product_caption(product, provider_type),
            reply_markup=product_keyboard(product, ""),
            photo=product.photo_file_id or fallback_photo,
            video_file_id=product.video_file_id,
        )
        await callback.answer()
        return

    if data == "buyer:partner":
        PARTNER_APPLICATION_WAIT.add(callback.from_user.id)
        await update_or_send(
            callback,
            "🤝 <b>Стать партнёром</b>\n\nОпишите услугу одним сообщением:\n• что продаёте;\n• цена и валюта;\n• как выдаёте товар/услугу;\n• сроки и условия.\n\nЗаявка уйдёт администраторам на модерацию.\nДля отмены напишите: отмена",
            reply_markup=buyer_back_to_panel_keyboard(),
        )
        await callback.answer("Жду описание заявки")
        return

    if data == "buyer:feedback":
        await update_or_send(
            callback,
            "✉️ Обратная связь\n\nНажмите «Обратная связь» на панели и отправьте вопрос следующим сообщением.",
            reply_markup=buyer_back_to_panel_keyboard(),
        )
        await callback.answer()
        return

    if data == "buyer:faq":
        await update_or_send(
            callback,
            await get_faq_page_text(),
            reply_markup=buyer_back_to_panel_keyboard(),
        )
        await callback.answer()
        return

    if data.startswith("buyer:"):
        handled = await handle_buyer_callback(bot, callback)
        if handled:
            return

        logger.warning(
            "STALE_BUYER_CALLBACK user_id=%s data=%s",
            callback.from_user.id if callback.from_user else None,
            data,
        )
        await callback.answer(
            "Эта кнопка устарела. Откройте главное меню командой /start.",
            show_alert=True,
        )
        return

    if data.startswith("svcpage:"):

        _, order_id_raw, page_raw = data.split(":")
        order_id = int(order_id_raw)
        page = int(page_raw)

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id) if order_id else None
            if not order or order.status != "waiting_service":
                closed_text = await get_text(
                    session, "order_closed", "Заказ уже закрыт или уже в обработке."
                )
                await callback.answer(closed_text, show_alert=True)
                return
            if not await guard_order_owner(callback, order):
                return
            services, max_page = await get_services_page(
                session, page, SERVICE_PAGE_SIZE
            )
            text = await get_text(
                session,
                "service_select",
                "Выберите сервис кнопкой ниже или напишите название из списка.",
            )

        await update_or_send(
            callback,
            f"{text}\n\nСтраница {page + 1}/{max_page + 1}",
            reply_markup=service_keyboard_from_services(
                services, page, max_page, order_id
            ),
        )
        await callback.answer()
        return

    if data.startswith("service:"):
        _, order_id_raw, service_slug = data.split(":", 2)
        order_id = int(order_id_raw)

        async with SessionLocal() as session:
            service = await find_service_by_slug(session, service_slug)
            order = await get_order_by_id(session, order_id) if order_id else None

            if not order or order.status != "waiting_service":
                closed_text = await get_text(
                    session, "order_closed", "Заказ уже закрыт или уже в обработке."
                )
                await callback.answer(closed_text, show_alert=True)
                return
            if not await guard_order_owner(callback, order):
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
                closed_text = await get_text(
                    session, "order_closed", "Заказ уже закрыт или уже в обработке."
                )
                await callback.answer(closed_text, show_alert=True)
                return
            if not await guard_order_owner(callback, order):
                return

            business_id = order.business_connection_id

        if not service:
            await callback.answer("Сервис не найден", show_alert=True)
            return

        await accept_service_for_order(
            bot, message, order_id, service.name, business_id
        )
        await callback.answer("Сервис подтверждён")
        return

    if data.startswith("code_sent:"):
        order_id = int(data.split(":")[1])

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return
            if not await guard_order_owner(callback, order):
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            if order.status == "waiting_supplier_code":
                await callback.answer(
                    "Код уже запрошен. Подождите ответ поставщика.", show_alert=True
                )
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
            code_request = await create_supplier_request(
                session, order.id, supplier.telegram_id, "code"
            )

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
                await set_supplier_request_message_id(
                    session, code_request.id, ok.message_id
                )

        if callback.message:
            await callback.message.answer(
                "OK. Запросил код у поставщика."
                if ok
                else "Не смог написать поставщику."
            )

        await callback.answer()
        return

    if data.startswith("confirm_success:"):
        order_id = int(data.split(":")[1])

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return
            if not await guard_order_owner(callback, order):
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            order.status = "confirmed"
            order.updated_at = datetime.utcnow()
            await close_waiting_supplier_requests_for_order(session, order.id)
            await session.commit()
            await session.refresh(order)
            thank_you_text = await get_text(session, "thank_you", "Спасибо за покупку!")

        await sync_purchase_from_order(order.id, True)

        target_chat_id = order.buyer_chat_id or order.customer_telegram_id
        target_business_id = (
            order.business_connection_id or ADMIN_BUSINESS_CONNECTION_ID
        )

        thanks_sent = False
        if target_chat_id:
            thanks_sent = await send_buyer_role_panel(
                bot,
                target_chat_id,
                thank_you_text,
                business_connection_id=get_callback_business_id(callback)
                or target_business_id,
                reply_markup=await buyer_inline_keyboard_for_user(user_id),
                callback=callback,
            )

        if not thanks_sent and callback.message:
            await update_or_send(
                callback, thank_you_text, reply_markup=buyer_inline_menu_keyboard()
            )

        await callback.answer("Заказ завершён")
        return

    if data.startswith("number_invalid:") or data.startswith("code_invalid:"):
        order_id = int(data.split(":")[1])
        user_id = callback.from_user.id if callback.from_user else 0

        async with SessionLocal() as session:
            problem_cooldown = await get_cooldown_seconds(
                session, "problem", PROBLEM_COOLDOWN_SECONDS
            )
            ok_cd, remaining = await check_cooldown(
                session, user_id, "problem", problem_cooldown
            )

            if not ok_cd:
                minutes = max(1, remaining // 60)
                await callback.answer(
                    f"Проблему можно отправлять раз в 1 минуту. Осталось примерно {minutes} мин.",
                    show_alert=True,
                )
                return

            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return
            if not await guard_order_owner(callback, order):
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            order.status = "problem"
            order.updated_at = datetime.utcnow()
            await session.commit()

        await sync_purchase_from_order(order.id, False, "Покупатель сообщил о проблеме")
        problem_type = "code" if data.startswith("code_invalid:") else "number"
        await resend_problem_to_supplier(bot, order, problem_type)

        if callback.message:
            await callback.message.answer(
                "Понял. Передал проблему админу и поставщику."
            )

        await notify_admins(
            bot,
            "Покупатель сообщил о проблеме.\n\n"
            f"Тип: {'код' if problem_type == 'code' else 'номер'}\n"
            f"Заказ ID в базе: {order_id}\n"
            f"Сервис: {order.service_name or 'нет'}\n"
            f"Номер: {order.phone_number or 'нет'}\n"
            f"Код: {order.verification_code or 'нет'}\n\n"
            "Запрос повторно отправлен поставщику.",
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
        "🛠 Панель администратора\n"
        "Компактное служебное меню.\n\n"
        "Покупательские кнопки здесь скрыты. Для возврата нажмите «Главная».\n\n"
        "▫️ Магазин — товары, категории, склад\n"
        "▫️ Прокси — страны, сроки, наценка\n"
        "▫️ Оплата — платежи и проверки\n"
        "▫️ Рассылка — сообщение всем покупателям"
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
        "🛍 MCS Shop\n"
        "Быстрый магазин с автовыдачей.\n\n"
        "Выберите нужный раздел ниже.\n\n"
        "🛒 Каталог — все товары\n"
        "📱 Номера — товары со склада / поставщики\n"
        "🧾 Заказы — история и статусы\n"
        "💬 Поддержка — вопрос администратору"
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
