from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services import format_service_label


def supplier_panel_keyboard(page: int = 0, max_page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ В ожидании", callback_data=f"supplier:pending:{page}")
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"supplier:pending:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Дальше", callback_data=f"supplier:pending:{page + 1}")
    kb.button(text="🔄 Обновить", callback_data=f"supplier:pending:{page}")
    kb.adjust(2)
    return kb.as_markup()


def _short_button_text(value: str | None, limit: int = 24) -> str:
    text = (value or "Товар").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def supplier_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="🚚 Панель поставщика")],
            [KeyboardButton(text="⏳ Заявки в ожидании")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Откройте профиль, панель или отправьте номер/код",
    )


def _short_admin_button_text(value: str | None, limit: int = 28) -> str:
    text = (value or "Заказ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def buyer_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="📦 Мои заказы")],
            [KeyboardButton(text="🆘 Помощь")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )


# ---------------- Role menus patch v6 ----------------
# Эти функции переопределяют простые меню выше. В Python последнее def с тем же именем становится актуальным.


# -----------------------------------------------------


# ---------------- Section lists patch v7 ----------------
# Нормальные разделы: в каждом разделе показываются именно заявки/заказы этого раздела + назад.


# -----------------------------------------------------


# ---------------- Full shop visual keyboard patch v15 ----------------
# Единый стиль кнопок: "иконка › действие".
# Эти функции переопределяют старые def выше.


def confirm_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ › Всё успешно", callback_data=f"confirm_success:{order_id}")
    kb.button(text="⚠️ › Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def number_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📩 › Код отправлен", callback_data=f"code_sent:{order_id}")
    kb.button(text="⚠️ › Номер не работает", callback_data=f"number_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def service_keyboard_from_services(
    services, page: int, max_page: int, order_id: int | None = None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for service in services:
        slug = service.name.lower().replace(" ", "_")
        kb.button(
            text=f"🧩 › {format_service_label(service)}",
            callback_data=f"service:{order_id or 0}:{slug}",
        )
    if page > 0:
        kb.button(
            text="⬅️ › Назад", callback_data=f"svcpage:{order_id or 0}:{page - 1}"
        )
    if page < max_page:
        kb.button(
            text="➡️ › Дальше", callback_data=f"svcpage:{order_id or 0}:{page + 1}"
        )
    kb.adjust(1)
    return kb.as_markup()


def service_keyboard(order_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🧩 › Открыть список сервисов", callback_data=f"svcpage:{order_id or 0}:0"
    )
    kb.adjust(1)
    return kb.as_markup()


def service_confirm_keyboard(order_id: int, service_slug: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ › Подтвердить сервис",
        callback_data=f"service_confirm:{order_id}:{service_slug}",
    )
    kb.button(text="🔄 › Выбрать другой", callback_data=f"svcpage:{order_id}:0")
    kb.adjust(1)
    return kb.as_markup()


def admin_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_suppliers_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список партнёров", callback_data="admin:suppliers_list")
    kb.button(text="➕ Добавить партнёра", callback_data="admin:add_supplier")
    kb.button(text="🔗 Доступ к товару", callback_data="admin:bind_supplier")
    kb.button(text="📁 Доступ к категории", callback_data="admin:bind_supplier_category")
    kb.button(text="🔓 Забрать доступ", callback_data="admin:unbind_supplier")
    kb.button(text="🗑 Удалить партнёра", callback_data="admin:remove_supplier")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_suppliers_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="❌ › Отмена",
        callback_data="admin:supplier_action_cancel",
        style="danger",
    )
    kb.adjust(1)
    return kb.as_markup()


def admin_services_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 › Список сервисов", callback_data="admin:services_list")
    kb.button(text="➕ › Добавить сервис", callback_data="admin:add_service_help")
    kb.button(text="🗑 › Удалить сервис", callback_data="admin:remove_service_help")
    kb.button(text="🔥 › Эмодзи сервиса", callback_data="admin:service_emoji_help")
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_lists_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 › Список листов", callback_data="admin:lists_list")
    kb.button(text="➕ › Создать лист", callback_data="admin:list_help")
    kb.button(
        text="➕ › Добавить сервис в лист", callback_data="admin:list_add_service_help"
    )
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_texts_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 › Список текстов", callback_data="admin:texts_list")
    kb.button(text="✏️ › Изменить текст", callback_data="admin:set_text_help")
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_text_keys_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🙏 › Спасибо за покупку", callback_data="admin:edit_text:thank_you")
    kb.button(
        text="✅ › Сервис принят", callback_data="admin:edit_text:service_accepted"
    )
    kb.button(text="🧩 › Выбор сервиса", callback_data="admin:edit_text:service_select")
    kb.button(
        text="❌ › Заказ не найден", callback_data="admin:edit_text:order_not_found"
    )
    kb.button(
        text="🚫 › Запрет контактов", callback_data="admin:edit_text:contact_forbidden"
    )
    kb.button(text="🔒 › Заказ закрыт", callback_data="admin:edit_text:order_closed")
    kb.button(
        text="⚠️ › Проблема отправлена", callback_data="admin:edit_text:problem_sent"
    )
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📖 › Команды", callback_data="admin:commands")
    kb.button(text="🔄 › Обновить", callback_data="admin:panel")
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_profile_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 › Мой профиль", callback_data="admin:profile")
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_admins_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 › Список админов", callback_data="admin:admins_list")
    kb.button(text="➕ › Добавить админа", callback_data="admin:add_admin_prompt")
    kb.button(text="➖ › Удалить админа", callback_data="admin:remove_admin_list")
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_remove_admin_keyboard(
    admin_rows, env_admin_ids: list[int] | None = None
) -> InlineKeyboardMarkup:
    env_admin_ids = set(env_admin_ids or [])
    kb = InlineKeyboardBuilder()
    active_rows = [admin for admin in admin_rows if getattr(admin, "is_active", False)]
    if active_rows:
        for admin in active_rows:
            name = (admin.name or "без имени").strip()
            if len(name) > 24:
                name = name[:23] + "…"
            if admin.telegram_id in env_admin_ids:
                kb.button(
                    text=f"🔒 › {admin.telegram_id} — {name}",
                    callback_data="admin:remove_admin_env_locked",
                )
            else:
                kb.button(
                    text=f"🗑 › {admin.telegram_id} — {name}",
                    callback_data=f"admin:remove_admin:{admin.telegram_id}",
                )
    else:
        kb.button(text="📭 › Доп. админов нет", callback_data="admin:noop")
    kb.button(text="⬅️ › Назад к админам", callback_data="admin:admins")
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_add_admin_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ › Отмена", callback_data="admin:add_admin_cancel")
    kb.button(text="⬅️ › Назад к админам", callback_data="admin:admins")
    kb.adjust(1)
    return kb.as_markup()


def admin_orders_keyboard(
    orders, back_callback: str = "admin:panel"
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for order in orders:
        status_icon = {
            "waiting_service": "⏳",
            "waiting_supplier_number": "📞",
            "number_sent_to_customer": "📩",
            "waiting_supplier_code": "🔑",
            "code_sent_to_customer": "🔐",
            "confirmed": "✅",
            "problem": "⚠️",
        }.get(order.status, "🧾")
        label = f"{status_icon} › #{order.operation_id} — {_short_admin_button_text(order.service_name or order.product_name)}"
        kb.button(text=label, callback_data=f"admin:order:{order.id}")
    kb.button(text="⬅️ › Назад", callback_data=back_callback)
    kb.adjust(1)
    return kb.as_markup()


def admin_order_card_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🔁 › Повторить запрос", callback_data=f"admin:order_resend:{order_id}"
    )
    kb.button(
        text="📞 › Ждать номер",
        callback_data=f"admin:order_status:{order_id}:waiting_supplier_number",
    )
    kb.button(
        text="🔑 › Ждать код",
        callback_data=f"admin:order_status:{order_id}:waiting_supplier_code",
    )
    kb.button(
        text="⚠️ › Пометить проблемным",
        callback_data=f"admin:order_status:{order_id}:problem",
    )
    kb.button(
        text="✅ › Закрыть вручную",
        callback_data=f"admin:order_status:{order_id}:confirmed",
    )
    kb.button(text="⬅️ › К проблемам", callback_data="admin:problems")
    kb.button(text="🏠 › Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def buyer_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 › Активный заказ", callback_data="buyer:active")
    kb.button(text="🧾 › Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def buyer_orders_list_keyboard(orders) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for order in orders:
        status_icons = {
            "waiting_service": "🧩",
            "waiting_supplier_number": "📞",
            "number_sent_to_customer": "📩",
            "waiting_supplier_code": "🔑",
            "code_sent_to_customer": "🔐",
            "confirmed": "✅",
            "problem": "⚠️",
            "cancelled": "❌",
        }
        icon = status_icons.get(order.status, "🧾")
        op_id = getattr(order, "operation_id", None) or getattr(order, "id", "?")
        label = f"{icon} › #{op_id} — {_short_button_text(order.service_name or order.product_name)}"
        kb.button(text=label, callback_data=f"buyer:order:{order.id}")
    kb.button(text="📦 › Активный заказ", callback_data="buyer:active")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def buyer_empty_section_keyboard(back_to: str = "buyer:panel") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ › Назад", callback_data=back_to)
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_inline_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Мои заказы", callback_data="supplier:my_orders")
    kb.button(text="💼 Баланс", callback_data="supplier:wallet")
    kb.button(text="↗️ Вывод средств", callback_data="supplier:withdraw_help")
    kb.button(text="📋 › Заявки", callback_data="supplier:requests")
    kb.button(text="⏳ › Ожидают", callback_data="supplier:pending:0")
    kb.button(text="📞 › Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 › Ждут код", callback_data="supplier:filter:code:0")
    kb.button(text="📊 › Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="👤 › Мой профиль", callback_data="supplier:profile")
    kb.button(text="📖 › Команды", callback_data="supplier:commands")
    kb.button(text="🔄 › Обновить", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_requests_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ › Ожидающие заявки", callback_data="supplier:pending:0")
    kb.button(text="📞 › Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 › Ждут код", callback_data="supplier:filter:code:0")
    kb.button(text="📊 › Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_commands_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 › Заявки", callback_data="supplier:requests")
    kb.button(text="⏳ › Ожидающие", callback_data="supplier:pending:0")
    kb.button(text="📊 › Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_filter_keyboard(
    mode: str = "active", page: int = 0, max_page: int = 0
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 › Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="📞 › Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 › Ждут код", callback_data="supplier:filter:code:0")
    if page > 0:
        kb.button(text="⬅️ › Назад", callback_data=f"supplier:filter:{mode}:{page - 1}")
    if page < max_page:
        kb.button(
            text="➡️ › Дальше", callback_data=f"supplier:filter:{mode}:{page + 1}"
        )
    kb.button(
        text="🔄 › Обновить раздел", callback_data=f"supplier:filter:{mode}:{page}"
    )
    kb.button(text="📋 › К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_orders_keyboard(
    rows, page: int = 0, max_page: int = 0
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for request, order in rows:
        if request.request_type == "number":
            label = f"📞 › {_short_button_text(order.product_name)} — номер"
        else:
            label = f"🔑 › {_short_button_text(order.product_name)} — код"
        kb.button(text=label, callback_data=f"supplier:req:{request.id}:{page}")
    if page > 0:
        kb.button(text="⬅️ › Назад", callback_data=f"supplier:pending:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ › Дальше", callback_data=f"supplier:pending:{page + 1}")
    kb.button(text="🔄 › Обновить", callback_data=f"supplier:pending:{page}")
    kb.button(text="📋 › К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_section_orders_keyboard(
    rows, mode: str = "active", page: int = 0, max_page: int = 0
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for request, order in rows:
        status = getattr(request, "status", "")
        op_id = getattr(order, "operation_id", None) or getattr(order, "id", "?")
        title = _short_button_text(order.service_name or order.product_name)
        if status == "waiting_buyer_confirm":
            kb.button(
                text=f"⏳ › #{op_id} — {title} — ждём OK",
                callback_data=f"supplier:wait:{request.id}:{mode}:{page}",
            )
            continue
        icon = "📞" if request.request_type == "number" else "🔑"
        action = "номер" if request.request_type == "number" else "код"
        kb.button(
            text=f"{icon} › #{op_id} — {title} — {action}",
            callback_data=f"supplier:reqf:{request.id}:{mode}:{page}",
        )
    if page > 0:
        kb.button(text="⬅️ › Назад", callback_data=f"supplier:filter:{mode}:{page - 1}")
    if page < max_page:
        kb.button(
            text="➡️ › Дальше", callback_data=f"supplier:filter:{mode}:{page + 1}"
        )
    kb.button(
        text="🔄 › Обновить раздел", callback_data=f"supplier:filter:{mode}:{page}"
    )
    kb.button(text="📋 › К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_wait_confirm_keyboard(
    mode: str = "active", page: int = 0
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="⬅️ › Назад к разделу", callback_data=f"supplier:filter:{mode}:{page}"
    )
    kb.button(text="📋 › К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_empty_section_keyboard(mode: str = "active") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 › К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_request_actions_keyboard(
    request_id: int, request_type: str
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if request_type == "number":
        kb.button(text="📞 › Взять номер", callback_data=f"supplier:take:{request_id}")
        kb.button(
            text="✍️ › Отправить номер", callback_data=f"supplier:answer:{request_id}"
        )
    else:
        kb.button(text="🔑 › Взять код", callback_data=f"supplier:take:{request_id}")
        kb.button(
            text="✍️ › Отправить код", callback_data=f"supplier:answer:{request_id}"
        )
    kb.button(text="📋 › Все заявки", callback_data="supplier:pending:0")
    kb.button(text="🏠 › Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_new_order_keyboard(
    request_id: int, request_type: str
) -> InlineKeyboardMarkup:
    return supplier_request_actions_keyboard(request_id, request_type)


# --------------------------------------------------

# ---------------- Proxy shop admin + buyer selection ----------------


def admin_proxy_countries_keyboard(
    settings, country_labels: dict[str, str]
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, label in country_labels.items():
        selected = code in settings.countries
        kb.button(
            text=f"{'✅' if selected else '▫️'} › {label}",
            callback_data=f"admin:proxy:country:{code}",
        )
    kb.button(text="⬅️ › К настройкам прокси", callback_data="admin:proxy")
    kb.adjust(1)
    return kb.as_markup()


def admin_proxy_periods_keyboard(settings, periods: list[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for period in periods:
        selected = period in settings.periods
        kb.button(
            text=f"{'✅' if selected else '▫️'} › {period} дней",
            callback_data=f"admin:proxy:period:{period}",
        )
    kb.button(text="⬅️ › К настройкам прокси", callback_data="admin:proxy")
    kb.adjust(2)
    return kb.as_markup()


def admin_proxy_count_keyboard(count: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➖", callback_data="admin:proxy:count:minus")
    kb.button(text=f"📦 {count}", callback_data="admin:proxy")
    kb.button(text="➕", callback_data="admin:proxy:count:plus")
    kb.button(text="⬅️ › К настройкам прокси", callback_data="admin:proxy")
    kb.adjust(3, 1)
    return kb.as_markup()


def buyer_proxy_country_keyboard(
    order_id: int, countries: list[str], labels: dict[str, str]
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code in countries:
        kb.button(
            text=f"{labels.get(code, code.upper())}",
            callback_data=f"proxy:country:{order_id}:{code}",
        )
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def buyer_proxy_period_keyboard(
    order_id: int, periods: list[int]
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for period in periods:
        kb.button(
            text=f"📅 › {period} дней",
            callback_data=f"proxy:period:{order_id}:{period}",
        )
    kb.button(
        text="⬅️ › Назад к странам",
        callback_data=f"proxy:back_country:{order_id}",
        style="danger",
    )
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(2)
    return kb.as_markup()


def buyer_proxy_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ › Купить и выдать",
        callback_data=f"proxy:confirm:{order_id}",
        style="success",
    )
    kb.button(
        text="⬅️ › Изменить срок",
        callback_data=f"proxy:back_period:{order_id}",
        style="danger",
    )
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


# Final overrides for Proxyline-enabled menus.


def buyer_active_order_keyboard(
    order_id: int | None = None, status: str | None = None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if order_id and status == "waiting_proxy_country":
        kb.button(
            text="🌍 › Выбрать страну", callback_data=f"proxy:back_country:{order_id}"
        )
    elif order_id and status == "waiting_proxy_period":
        kb.button(
            text="📅 › Выбрать срок", callback_data=f"proxy:back_period:{order_id}"
        )
    elif order_id and status == "waiting_proxy_confirm":
        kb.button(
            text="✅ › Подтвердить прокси", callback_data=f"proxy:confirm:{order_id}"
        )
        kb.button(
            text="⬅️ › Изменить срок",
            callback_data=f"proxy:back_period:{order_id}",
            style="danger",
        )
    elif order_id and status == "waiting_service":
        kb.button(text="🧩 › Выбрать сервис", callback_data=f"svcpage:{order_id}:0")
    elif order_id and status == "number_sent_to_customer":
        kb.button(text="📩 › Код отправлен", callback_data=f"code_sent:{order_id}")
        kb.button(
            text="⚠️ › Номер не работает", callback_data=f"number_invalid:{order_id}"
        )
    elif order_id and status == "code_sent_to_customer":
        kb.button(text="✅ › Всё успешно", callback_data=f"confirm_success:{order_id}")
        kb.button(text="⚠️ › Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.button(text="🧾 › Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def buyer_order_card_keyboard(
    order_id: int, status: str | None = None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if status == "waiting_proxy_country":
        kb.button(
            text="🌍 › Выбрать страну", callback_data=f"proxy:back_country:{order_id}"
        )
    elif status == "waiting_proxy_period":
        kb.button(
            text="📅 › Выбрать срок", callback_data=f"proxy:back_period:{order_id}"
        )
    elif status == "waiting_proxy_confirm":
        kb.button(
            text="✅ › Купить и выдать",
            callback_data=f"proxy:confirm:{order_id}",
            style="success",
        )
        kb.button(
            text="⬅️ › Изменить срок",
            callback_data=f"proxy:back_period:{order_id}",
            style="danger",
        )
    elif status == "waiting_service":
        kb.button(text="🧩 › Выбрать сервис", callback_data=f"svcpage:{order_id}:0")
    elif status == "number_sent_to_customer":
        kb.button(text="📩 › Код отправлен", callback_data=f"code_sent:{order_id}")
        kb.button(
            text="⚠️ › Номер не работает", callback_data=f"number_invalid:{order_id}"
        )
    elif status == "code_sent_to_customer":
        kb.button(text="✅ › Всё успешно", callback_data=f"confirm_success:{order_id}")
        kb.button(text="⚠️ › Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.button(text="⬅️ › К заказам", callback_data="buyer:orders")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_proxy_products_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📦 Собственные товары / инструкция",
        callback_data="admin:proxy:products_help",
    )
    kb.button(text="🔄 › Обновить список", callback_data="admin:proxy:products")
    kb.button(text="⬅️ › К настройкам прокси", callback_data="admin:proxy")
    kb.adjust(1)
    return kb.as_markup()


# Финальное переопределение с явной привязкой товаров.
def admin_proxy_settings_keyboard(settings) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=(
            "🟢 › Автовыдача включена"
            if settings.enabled
            else "🔴 › Автовыдача выключена"
        ),
        callback_data="admin:proxy:toggle",
    )
    kb.button(text="🔗 Товары", callback_data="admin:proxy:products")
    kb.button(text="💹 Наценка", callback_data="admin:proxy:markup_help")
    kb.button(text="🌍 Страны", callback_data="admin:proxy:countries")
    kb.button(text="📅 Сроки", callback_data="admin:proxy:periods")
    type_label = "Выделенные" if settings.proxy_type == "dedicated" else "Общие"
    kb.button(text=f"🔐 {type_label}", callback_data="admin:proxy:type")
    kb.button(
        text=f"📦 {settings.count} шт.", callback_data="admin:proxy:count"
    )
    kb.button(
        text=f"🌐 IPv{settings.ip_version}", callback_data="admin:proxy:ip_version"
    )
    kb.button(text="🔄 Обновить", callback_data="admin:proxy")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(2, 2, 2, 1, 2)
    return kb.as_markup()


# Shop catalog merge v19: final buyer main menu override.


# Shop UI/admin v20 overrides
def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Чистая админ-панель без покупательских кнопок."""
    kb = InlineKeyboardBuilder()
    kb.button(text="▫️ Магазин", callback_data="v25:catalog")
    kb.button(text="▫️ Оплата", callback_data="admin:payments")
    kb.button(text="▫️ Рассылка", callback_data="admin:broadcast")
    kb.button(text="▫️ Админы", callback_data="admin:admins")
    kb.button(text="▫️ Проблемы", callback_data="admin:problems")
    kb.button(text="▫️ Настройки", callback_data="admin:store_settings")
    kb.button(text="▫️ Прокси-настройки", callback_data="admin:proxy")
    kb.button(text="▫️ Скрытые", callback_data="admin:hidden")
    kb.button(text="🏠 Главная", callback_data="buyer:panel")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


def admin_hidden_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="▫️ Привязки прокси", callback_data="admin:proxy:products")
    kb.button(text="▫️ Наценка", callback_data="admin:proxy:markup_help")
    kb.button(text="▫️ Страны", callback_data="admin:proxy:countries")
    kb.button(text="▫️ Сроки", callback_data="admin:proxy:periods")
    kb.button(text="▫️ Статистика", callback_data="admin:status")
    kb.button(text="▫️ Заявки партнёров", callback_data="market:admin:list")
    kb.button(text="▫️ Выводы поставщиков", callback_data="admin:withdrawals")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.button(text="🏠 Главная", callback_data="buyer:panel")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def buyer_inline_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data="buyer:shop")
    kb.button(text="🛒 Корзина", callback_data="buyer:cart")
    kb.button(text="📱 Номера", callback_data="buyer:number_catalog")
    kb.button(text="🧾 Заказы", callback_data="buyer:orders")
    kb.button(text="💼 Кошелёк", callback_data="buyer:wallet")
    kb.button(text="🤝 Стать партнёром", callback_data="buyer:partner")
    kb.button(text="🚚 Я поставщик", callback_data="supplier:panel")
    kb.button(text="💬 Поддержка", callback_data="buyer:feedback")
    kb.button(text="📕 FAQ", callback_data="buyer:faq")
    if is_admin:
        kb.button(text="🛠 Админ", callback_data="admin:panel")
        kb.adjust(2, 2, 2, 2, 1, 1)
    else:
        kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


# Shop UI navigation fix v20.1
def buyer_back_to_panel_keyboard() -> InlineKeyboardMarkup:
    """Навигация из информационных разделов покупателя."""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="buyer:shop")
    kb.button(text="🏠 Главная", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


# Main sections reply keyboard v20.4
def buyer_main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🛒 Корзина")],
        [KeyboardButton(text="📱 Номера"), KeyboardButton(text="🧾 Мои заказы")],
        [KeyboardButton(text="💼 Кошелёк"), KeyboardButton(text="🚚 Я поставщик")],
        [KeyboardButton(text="🤝 Стать партнёром")],
        [KeyboardButton(text="✉️ Обратная связь"), KeyboardButton(text="📕 FAQ")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Админ")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел",
        selective=True,
    )


def admin_currency_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code in ("USD", "RUB", "EUR", "USDT"):
        kb.button(text=code, callback_data=f"admin:shop:wizard_currency:{code}")
    kb.button(
        text="❌ Отмена", callback_data="admin:shop:wizard_cancel", style="danger"
    )
    kb.adjust(2)
    return kb.as_markup()


def admin_category_select_keyboard(categories) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in categories:
        kb.button(
            text=f"{row.name}",
            callback_data=f"admin:shop:wizard_category:{row.id}",
        )
    kb.button(
        text="➕ Новая категория",
        callback_data="admin:shop:add_category",
        style="success",
    )
    kb.button(
        text="❌ Отмена", callback_data="admin:shop:wizard_cancel", style="danger"
    )
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_product_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Удалить",
        callback_data=f"admin:shop:product_delete_confirm:{product_id}",
        style="danger",
    )
    kb.button(
        text="⬅️ Отмена",
        callback_data=f"admin:shop:product:{product_id}",
        style="danger",
    )
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_category_keyboard(category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Удалить",
        callback_data=f"admin:shop:category_delete_confirm:{category_id}",
        style="danger",
    )
    kb.button(
        text="⬅️ Отмена",
        callback_data=f"admin:shop:category:{category_id}",
        style="danger",
    )
    kb.adjust(1)
    return kb.as_markup()


def supplier_selected_request_keyboard(
    request_id: int, request_type: str
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✍️ Отправить номер" if request_type == "number" else "✍️ Отправить код",
        callback_data=f"supplier:answer:{request_id}",
    )
    kb.button(
        text="❌ Отменить выбор",
        callback_data=f"supplier:cancel_selection:{request_id}",
        style="danger",
    )
    kb.button(text="⬅️ К заявкам", callback_data="supplier:pending:0", style="danger")
    kb.adjust(1)
    return kb.as_markup()

# V50 final UI overrides: role-separated reply panels, cleaner categories, no auto-emojis.
def admin_main_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📦 Управление товарами")],
        [KeyboardButton(text="💳 Способы оплаты"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="👁 Скрытые")],
        [KeyboardButton(text="🏠 Главное меню")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Админ-панель",
        selective=True,
    )


def supplier_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📦 Мои заказы"), KeyboardButton(text="🛍 Мои товары")],
        [KeyboardButton(text="💼 Баланс"), KeyboardButton(text="↗️ Вывод")],
        [KeyboardButton(text="📖 Помощь"), KeyboardButton(text="🏠 Режим покупателя")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Панель поставщика",
        selective=True,
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Управление товарами", callback_data="v25:catalog")
    kb.button(text="💳 Способы оплаты", callback_data="admin:payments")
    kb.button(text="⚙️ Настройки", callback_data="admin:main_settings")
    kb.button(text="📢 Рассылка", callback_data="admin:broadcast")
    kb.button(text="👥 Админы", callback_data="admin:admins")
    kb.button(text="🧩 Прокси", callback_data="admin:proxy")
    kb.button(text="👁 Скрытые", callback_data="admin:hidden")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1, 2, 2, 2, 1)
    return kb.as_markup()


def admin_hidden_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 Привязки прокси", callback_data="admin:proxy:products")
    kb.button(text="📈 Наценка прокси", callback_data="admin:proxy:markup_help")
    kb.button(text="🌍 Страны", callback_data="admin:proxy:countries")
    kb.button(text="📱 Сервисы номеров", callback_data="admin:number_settings")
    kb.button(text="🤝 Заявки партнёров", callback_data="market:admin:list")
    kb.button(text="↗️ Выводы", callback_data="admin:withdrawals")
    kb.button(text="📊 Статистика", callback_data="admin:status")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def supplier_inline_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Мои заказы", callback_data="supplier:my_orders")
    kb.button(text="🛍 Мои товары", callback_data="supplier:products")
    kb.button(text="💼 Баланс", callback_data="supplier:wallet")
    kb.button(text="↗️ Вывод", callback_data="supplier:withdraw_help")
    kb.button(text="📝 Заявки в работе", callback_data="supplier:requests")
    kb.button(text="📖 Помощь", callback_data="supplier:price_help")
    kb.button(text="🏠 Режим покупателя", callback_data="buyer:panel")
    kb.adjust(2, 2, 1, 1, 1)
    return kb.as_markup()


def buyer_inline_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data="buyer:shop")
    kb.button(text="🛒 Корзина", callback_data="buyer:cart")
    kb.button(text="📱 Номера", callback_data="buyer:number_catalog")
    kb.button(text="🧾 Заказы", callback_data="buyer:orders")
    kb.button(text="💼 Кошелёк", callback_data="buyer:wallet")
    kb.button(text="🤝 Стать партнёром", callback_data="buyer:partner")
    kb.button(text="🚚 Я поставщик", callback_data="supplier:panel")
    kb.button(text="💬 Поддержка", callback_data="buyer:feedback")
    kb.button(text="📕 FAQ", callback_data="buyer:faq")
    if is_admin:
        kb.button(text="🛠 Админ", callback_data="admin:panel")
    kb.adjust(2, 2, 2, 2, 1, 1)
    return kb.as_markup()


def buyer_main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🛒 Корзина")],
        [KeyboardButton(text="📱 Номера"), KeyboardButton(text="🧾 Мои заказы")],
        [KeyboardButton(text="💼 Кошелёк"), KeyboardButton(text="🚚 Я поставщик")],
        [KeyboardButton(text="🤝 Стать партнёром")],
        [KeyboardButton(text="✉️ Обратная связь"), KeyboardButton(text="📕 FAQ")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Админ")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел",
        selective=True,
    )


def admin_category_select_keyboard(categories) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in categories:
        kb.button(text=f"{row.name}", callback_data=f"admin:shop:wizard_category:{row.id}")
    kb.button(text="➕ Новая категория", callback_data="admin:shop:add_category")
    kb.button(text="❌ Отмена", callback_data="admin:shop:wizard_cancel")
    kb.adjust(1)
    return kb.as_markup()

# V51 final visual overrides: role-aware menus, softer labels, paginated admin countries.
def admin_main_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📦 Управление товарами")],
        [KeyboardButton(text="🤝 Партнёры"), KeyboardButton(text="💳 Способы оплаты")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="🧩 Прокси")],
        [KeyboardButton(text="👁 Скрытые"), KeyboardButton(text="👥 Админы")],
        [KeyboardButton(text="🏠 Главное меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Панель администратора", selective=True)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Управление товарами", callback_data="v25:catalog")
    kb.button(text="🤝 Партнёры", callback_data="admin:partners")
    kb.button(text="💳 Способы оплаты", callback_data="admin:payments")
    kb.button(text="⚙️ Настройки", callback_data="admin:main_settings")
    kb.button(text="📊 Статистика", callback_data="admin:status")
    kb.button(text="📢 Рассылка", callback_data="admin:broadcast")
    kb.button(text="👥 Админы и права", callback_data="admin:admins")
    kb.button(text="🧩 Прокси", callback_data="admin:proxy")
    kb.button(text="👁 Скрытые", callback_data="admin:hidden")
    kb.button(text="🏠 Режим покупателя", callback_data="buyer:panel")
    kb.adjust(1, 2, 2, 2, 2, 1)
    return kb.as_markup()


def admin_hidden_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🤝 Заявки партнёров", callback_data="market:admin:list")
    kb.button(text="↗️ Выводы", callback_data="admin:withdrawals")
    kb.button(text="🔗 Привязки прокси", callback_data="admin:proxy:products")
    kb.button(text="📈 Наценка прокси", callback_data="admin:proxy:markup_help")
    kb.button(text="🌍 Страны прокси", callback_data="admin:proxy:countries:0")
    kb.button(text="📱 Номера", callback_data="admin:number_settings")
    kb.button(text="👥 Права админов", callback_data="admin:caps")
    kb.button(text="🤖 Зеркала", callback_data="admin:mirrors")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


def supplier_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📦 Мои заказы"), KeyboardButton(text="🛍 Мои товары")],
        [KeyboardButton(text="💼 Баланс"), KeyboardButton(text="↗️ Вывод")],
        [KeyboardButton(text="💵 Изменить цену"), KeyboardButton(text="📖 Помощь")],
        [KeyboardButton(text="🏠 Режим покупателя")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Панель поставщика", selective=True)


def supplier_inline_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Мои заказы", callback_data="supplier:my_orders")
    kb.button(text="🛍 Мои товары", callback_data="supplier:products")
    kb.button(text="💼 Баланс", callback_data="supplier:wallet")
    kb.button(text="↗️ Вывод", callback_data="supplier:withdraw_help")
    kb.button(text="💵 Изменить цену", callback_data="supplier:price_help")
    kb.button(text="📝 Заявки", callback_data="supplier:requests")
    kb.button(text="📖 Помощь", callback_data="supplier:price_help")
    kb.button(text="🏠 Режим покупателя", callback_data="buyer:panel")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def buyer_inline_menu_keyboard(is_admin: bool = False, is_supplier: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data="buyer:shop")
    kb.button(text="🛒 Корзина", callback_data="buyer:cart")
    kb.button(text="📱 Номера", callback_data="buyer:number_catalog")
    kb.button(text="🧾 Заказы", callback_data="buyer:orders")
    kb.button(text="💼 Кошелёк", callback_data="buyer:wallet")
    kb.button(text="🤝 Стать партнёром", callback_data="buyer:partner")
    if is_supplier:
        kb.button(text="🚚 Я поставщик", callback_data="supplier:panel")
    kb.button(text="💬 Поддержка", callback_data="buyer:feedback")
    kb.button(text="📕 FAQ", callback_data="buyer:faq")
    if is_admin:
        kb.button(text="🛠 Админ", callback_data="admin:panel")
    kb.adjust(2, 2, 2, 2, 1, 1)
    return kb.as_markup()


def buyer_main_reply_keyboard(is_admin: bool = False, is_supplier: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🛒 Корзина")],
        [KeyboardButton(text="📱 Номера"), KeyboardButton(text="🧾 Мои заказы")],
        [KeyboardButton(text="💼 Кошелёк"), KeyboardButton(text="🤝 Стать партнёром")],
        [KeyboardButton(text="✉️ Обратная связь"), KeyboardButton(text="📕 FAQ")],
    ]
    if is_supplier:
        rows.append([KeyboardButton(text="🚚 Я поставщик")])
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Админ")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Главное меню", selective=True)


def admin_category_select_keyboard(categories) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📁 Без категории", callback_data="admin:shop:wizard_category:0")
    for row in categories:
        kb.button(text=f"📁 {row.name}", callback_data=f"admin:shop:wizard_category:{row.id}")
    kb.button(text="➕ Новая категория", callback_data="admin:shop:add_category")
    kb.button(text="❌ Отмена", callback_data="admin:shop:wizard_cancel")
    kb.adjust(1)
    return kb.as_markup()


def admin_proxy_settings_keyboard(settings) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=("🟢 Автовыдача" if settings.enabled else "🔴 Автовыдача"), callback_data="admin:proxy:toggle")
    kb.button(text="🔗 Товары", callback_data="admin:proxy:products")
    kb.button(text="📈 Наценка", callback_data="admin:proxy:markup_help")
    kb.button(text="🌍 Страны", callback_data="admin:proxy:countries:0")
    kb.button(text="📅 Сроки", callback_data="admin:proxy:periods")
    kb.button(text=f"📦 {settings.count} шт.", callback_data="admin:proxy:count")
    kb.button(text=f"🌐 IPv{settings.ip_version}", callback_data="admin:proxy:ip_version")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def admin_proxy_countries_keyboard(settings, country_labels: dict[str, str], page: int = 0, per_page: int = 12) -> InlineKeyboardMarkup:
    rows = list(country_labels.items())
    pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = max(0, min(int(page or 0), pages - 1))
    start = page * per_page
    chunk = rows[start:start + per_page]
    kb = InlineKeyboardBuilder()
    for code, label in chunk:
        selected = code in settings.countries
        kb.button(text=f"{'✅' if selected else '▫️'} {label}", callback_data=f"admin:proxy:country:{code}:{page}")
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"admin:proxy:countries:{page - 1}")
    if page < pages - 1:
        kb.button(text="➡️ Вперёд", callback_data=f"admin:proxy:countries:{page + 1}")
    kb.button(text="⬅️ К прокси", callback_data="admin:proxy")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def payments_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 CryptoBot", callback_data="admin:payments:cryptobot")
    kb.button(text="💼 Баланс магазина", callback_data="admin:payments:wallet")
    kb.button(text="🔄 Обновить", callback_data="admin:payments")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1, 1, 2)
    return kb.as_markup()

# V51 add rights button to admins menu.
def admin_admins_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список админов", callback_data="admin:admins_list")
    kb.button(text="➕ Добавить админа", callback_data="admin:add_admin_prompt")
    kb.button(text="➖ Удалить админа", callback_data="admin:remove_admin_list")
    kb.button(text="🔐 Права админов", callback_data="admin:caps")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()
