from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services import format_service_label


def confirm_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ OK, всё успешно", callback_data=f"confirm_success:{order_id}")
    kb.button(text="⚠️ Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def number_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📩 Код отправлен", callback_data=f"code_sent:{order_id}")
    kb.button(text="⚠️ Номер не работает", callback_data=f"number_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def service_keyboard_from_services(services, page: int, max_page: int, order_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for service in services:
        slug = service.name.lower().replace(" ", "_")
        kb.button(text=format_service_label(service), callback_data=f"service:{order_id or 0}:{slug}")

    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"svcpage:{order_id or 0}:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Дальше", callback_data=f"svcpage:{order_id or 0}:{page + 1}")

    kb.adjust(2)
    return kb.as_markup()


def service_keyboard(order_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Открыть список сервисов", callback_data=f"svcpage:{order_id or 0}:0")
    kb.adjust(1)
    return kb.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статус", callback_data="admin:status")
    kb.button(text="📈 Статистика", callback_data="admin:stats")
    kb.button(text="🧾 Заказы", callback_data="admin:last_orders")
    kb.button(text="⚠️ Проблемы", callback_data="admin:problems")
    kb.button(text="🚚 Поставщики", callback_data="admin:suppliers")
    kb.button(text="🧩 Сервисы", callback_data="admin:services")
    kb.button(text="📚 Листы", callback_data="admin:lists")
    kb.button(text="✏️ Тексты", callback_data="admin:texts")
    kb.button(text="👮 Админы", callback_data="admin:admins")
    kb.button(text="⚙️ Настройки", callback_data="admin:settings")
    kb.adjust(2)
    return kb.as_markup()


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


def supplier_orders_keyboard(rows, page: int = 0, max_page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for request, order in rows:
        if request.request_type == "number":
            label = f"📞 {_short_button_text(order.product_name)} — номер"
        else:
            label = f"🔑 {_short_button_text(order.product_name)} — код"
        kb.button(text=label, callback_data=f"supplier:req:{request.id}:{page}")

    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"supplier:pending:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Дальше", callback_data=f"supplier:pending:{page + 1}")
    kb.button(text="🔄 Обновить", callback_data=f"supplier:pending:{page}")
    kb.adjust(1)
    return kb.as_markup()


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



def admin_text_keys_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🙏 Спасибо за покупку", callback_data="admin:edit_text:thank_you")
    kb.button(text="✅ Сервис принят", callback_data="admin:edit_text:service_accepted")
    kb.button(text="🧩 Выбор сервиса", callback_data="admin:edit_text:service_select")
    kb.button(text="❌ Заказ не найден", callback_data="admin:edit_text:order_not_found")
    kb.button(text="🚫 Запрет контактов", callback_data="admin:edit_text:contact_forbidden")
    kb.button(text="🔒 Заказ закрыт", callback_data="admin:edit_text:order_closed")
    kb.button(text="⚠️ Проблема отправлена", callback_data="admin:edit_text:problem_sent")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад в главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_suppliers_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список поставщиков", callback_data="admin:suppliers_list")
    kb.button(text="➕ Добавить поставщика", callback_data="admin:add_supplier_help")
    kb.button(text="🔗 Привязать товар/лист", callback_data="admin:bind_supplier_help")
    kb.button(text="🗑 Удалить поставщика", callback_data="admin:remove_supplier_help")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_services_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список сервисов", callback_data="admin:services_list")
    kb.button(text="➕ Добавить сервис", callback_data="admin:add_service_help")
    kb.button(text="🗑 Удалить сервис", callback_data="admin:remove_service_help")
    kb.button(text="🔥 Эмодзи сервиса", callback_data="admin:service_emoji_help")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_lists_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список листов", callback_data="admin:lists_list")
    kb.button(text="➕ Создать лист", callback_data="admin:list_help")
    kb.button(text="➕ Добавить сервис в лист", callback_data="admin:list_add_service_help")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_texts_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список текстов", callback_data="admin:texts_list")
    kb.button(text="✏️ Изменить текст", callback_data="admin:set_text_help")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📖 Команды", callback_data="admin:commands")
    kb.button(text="🔄 Обновить меню", callback_data="admin:panel")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()




def admin_admins_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список админов", callback_data="admin:admins_list")
    kb.button(text="➕ Добавить админа", callback_data="admin:add_admin_prompt")
    kb.button(text="➖ Удалить админа", callback_data="admin:remove_admin_list")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_remove_admin_keyboard(admin_rows, env_admin_ids: list[int] | None = None) -> InlineKeyboardMarkup:
    env_admin_ids = set(env_admin_ids or [])
    kb = InlineKeyboardBuilder()

    active_rows = [admin for admin in admin_rows if getattr(admin, "is_active", False)]
    if active_rows:
        for admin in active_rows:
            name = (admin.name or "без имени").strip()
            if len(name) > 24:
                name = name[:23] + "…"
            locked = " 🔒" if admin.telegram_id in env_admin_ids else ""
            if admin.telegram_id in env_admin_ids:
                kb.button(text=f"🔒 {admin.telegram_id} — {name}", callback_data="admin:remove_admin_env_locked")
            else:
                kb.button(text=f"🗑 {admin.telegram_id} — {name}{locked}", callback_data=f"admin:remove_admin:{admin.telegram_id}")
    else:
        kb.button(text="Доп. админов нет", callback_data="admin:noop")

    kb.button(text="⬅️ Назад к админам", callback_data="admin:admins")
    kb.button(text="🏠 Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def admin_add_admin_cancel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin:add_admin_cancel")
    kb.button(text="⬅️ Назад к админам", callback_data="admin:admins")
    kb.adjust(1)
    return kb.as_markup()

def _short_admin_button_text(value: str | None, limit: int = 28) -> str:
    text = (value or "Заказ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def admin_orders_keyboard(orders, back_callback: str = "admin:panel") -> InlineKeyboardMarkup:
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
        label = f"{status_icon} #{order.operation_id} — {_short_admin_button_text(order.service_name or order.product_name)}"
        kb.button(text=label, callback_data=f"admin:order:{order.id}")

    kb.button(text="⬅️ Назад", callback_data=back_callback)
    kb.adjust(1)
    return kb.as_markup()


def admin_order_card_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="🔁 Повторить запрос поставщику", callback_data=f"admin:order_resend:{order_id}")
    kb.button(text="📞 Ждать номер", callback_data=f"admin:order_status:{order_id}:waiting_supplier_number")
    kb.button(text="🔑 Ждать код", callback_data=f"admin:order_status:{order_id}:waiting_supplier_code")
    kb.button(text="⚠️ Пометить проблемным", callback_data=f"admin:order_status:{order_id}:problem")
    kb.button(text="✅ Закрыть вручную", callback_data=f"admin:order_status:{order_id}:confirmed")
    kb.button(text="⬅️ К проблемам", callback_data="admin:problems")
    kb.button(text="🏠 Главное меню", callback_data="admin:panel")

    kb.adjust(1)
    return kb.as_markup()



def service_confirm_keyboard(order_id: int, service_slug: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"service_confirm:{order_id}:{service_slug}")
    kb.button(text="🔄 Выбрать другой сервис", callback_data=f"svcpage:{order_id}:0")
    kb.adjust(1)
    return kb.as_markup()



def supplier_request_actions_keyboard(request_id: int, request_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if request_type == "number":
        kb.button(text="📞 Взять номер в работу", callback_data=f"supplier:take:{request_id}")
        kb.button(text="✍️ Отправить номер", callback_data=f"supplier:answer:{request_id}")
    else:
        kb.button(text="🔑 Взять код в работу", callback_data=f"supplier:take:{request_id}")
        kb.button(text="✍️ Отправить код", callback_data=f"supplier:answer:{request_id}")

    kb.button(text="⏳ Все заявки", callback_data="supplier:pending:0")
    kb.adjust(1)
    return kb.as_markup()



def supplier_new_order_keyboard(request_id: int, request_type: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if request_type == "number":
        kb.button(text="📞 Взять номер в работу", callback_data=f"supplier:take:{request_id}")
        kb.button(text="✍️ Отправить номер", callback_data=f"supplier:answer:{request_id}")
    else:
        kb.button(text="🔑 Взять код в работу", callback_data=f"supplier:take:{request_id}")
        kb.button(text="✍️ Отправить код", callback_data=f"supplier:answer:{request_id}")

    kb.button(text="⏳ Заявки в ожидании", callback_data="supplier:pending:0")
    kb.button(text="📖 Команды", callback_data="supplier:commands")
    kb.adjust(1)
    return kb.as_markup()


def supplier_commands_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Заявки в ожидании", callback_data="supplier:pending:0")
    kb.button(text="🚚 Панель поставщика", callback_data="supplier:pending:0")
    kb.adjust(1)
    return kb.as_markup()



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



def buyer_inline_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Inline-меню покупателя.
    ВАЖНО: inline-кнопки видны прямо под сообщением.
    Это надёжнее, чем ReplyKeyboardMarkup в Telegram Business-чатах.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Мой профиль", callback_data="buyer:profile")
    kb.button(text="📦 Мои заказы", callback_data="buyer:orders")
    kb.button(text="🆘 Помощь", callback_data="buyer:help")
    kb.adjust(1)
    return kb.as_markup()


def supplier_inline_menu_keyboard() -> InlineKeyboardMarkup:
    """Inline-меню поставщика, чтобы кнопки точно появились под сообщением."""
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Мой профиль", callback_data="supplier:profile")
    kb.button(text="🚚 Панель поставщика", callback_data="supplier:pending:0")
    kb.button(text="⏳ Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="📞 Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 Ждут код", callback_data="supplier:filter:code:0")
    kb.button(text="📖 Команды", callback_data="supplier:commands")
    kb.adjust(1)
    return kb.as_markup()


def supplier_filter_keyboard(mode: str = "active", page: int = 0, max_page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="⏳ Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="📞 Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 Ждут код", callback_data="supplier:filter:code:0")

    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"supplier:filter:{mode}:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Дальше", callback_data=f"supplier:filter:{mode}:{page + 1}")

    kb.button(text="🔄 Обновить", callback_data=f"supplier:filter:{mode}:{page}")
    kb.button(text="📖 Команды", callback_data="supplier:commands")
    kb.adjust(1)
    return kb.as_markup()



def admin_profile_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Мой профиль", callback_data="admin:profile")
    kb.button(text="🏠 Главное меню", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


# ---------------- Role menus patch v6 ----------------
# Эти функции переопределяют простые меню выше. В Python последнее def с тем же именем становится актуальным.

def buyer_inline_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное inline-меню покупателя в стиле админ-панели."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Активный заказ", callback_data="buyer:active")
    kb.button(text="🧾 Мои заказы", callback_data="buyer:orders")
    kb.button(text="👤 Мой профиль", callback_data="buyer:profile")
    kb.button(text="🆘 Помощь", callback_data="buyer:help")
    kb.button(text="🔄 Обновить меню", callback_data="buyer:panel")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def buyer_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Активный заказ", callback_data="buyer:active")
    kb.button(text="🧾 Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def buyer_active_order_keyboard(order_id: int | None = None, status: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if order_id and status == "waiting_service":
        kb.button(text="🧩 Выбрать сервис", callback_data=f"svcpage:{order_id}:0")
    if order_id and status == "number_sent_to_customer":
        kb.button(text="📩 Код отправлен", callback_data=f"code_sent:{order_id}")
        kb.button(text="⚠️ Номер не работает", callback_data=f"number_invalid:{order_id}")
    if order_id and status == "code_sent_to_customer":
        kb.button(text="✅ OK, всё успешно", callback_data=f"confirm_success:{order_id}")
        kb.button(text="⚠️ Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.button(text="🧾 Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_inline_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное inline-меню поставщика в стиле админ-панели."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заявки", callback_data="supplier:requests")
    kb.button(text="⏳ Ожидают", callback_data="supplier:pending:0")
    kb.button(text="📞 Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 Ждут код", callback_data="supplier:filter:code:0")
    kb.button(text="📊 Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="👤 Мой профиль", callback_data="supplier:profile")
    kb.button(text="📖 Команды", callback_data="supplier:commands")
    kb.button(text="🔄 Обновить", callback_data="supplier:panel")
    kb.adjust(2, 2, 2, 2)
    return kb.as_markup()


def supplier_requests_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Ожидающие заявки", callback_data="supplier:pending:0")
    kb.button(text="📊 Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="📞 Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 Ждут код", callback_data="supplier:filter:code:0")
    kb.button(text="🏠 Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_commands_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Заявки", callback_data="supplier:requests")
    kb.button(text="⏳ Ожидающие", callback_data="supplier:pending:0")
    kb.button(text="📊 Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="🏠 Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_filter_keyboard(mode: str = "active", page: int = 0, max_page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Все активные", callback_data="supplier:filter:active:0")
    kb.button(text="📞 Ждут номер", callback_data="supplier:filter:number:0")
    kb.button(text="🔑 Ждут код", callback_data="supplier:filter:code:0")
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"supplier:filter:{mode}:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Дальше", callback_data=f"supplier:filter:{mode}:{page + 1}")
    kb.button(text="🔄 Обновить", callback_data=f"supplier:filter:{mode}:{page}")
    kb.button(text="📋 К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_orders_keyboard(rows, page: int = 0, max_page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for request, order in rows:
        if request.request_type == "number":
            label = f"📞 {_short_button_text(order.product_name)} — номер"
        else:
            label = f"🔑 {_short_button_text(order.product_name)} — код"
        kb.button(text=label, callback_data=f"supplier:req:{request.id}:{page}")
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"supplier:pending:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Дальше", callback_data=f"supplier:pending:{page + 1}")
    kb.button(text="🔄 Обновить", callback_data=f"supplier:pending:{page}")
    kb.button(text="📋 К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()
# -----------------------------------------------------


# ---------------- Section lists patch v7 ----------------
# Нормальные разделы: в каждом разделе показываются именно заявки/заказы этого раздела + назад.

def supplier_section_orders_keyboard(rows, mode: str = "active", page: int = 0, max_page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for request, order in rows:
        status = getattr(request, "status", "")
        op_id = getattr(order, "operation_id", None) or getattr(order, "id", "?")
        title = _short_button_text(order.service_name or order.product_name)

        if status == "waiting_buyer_confirm":
            label = f"⏳ #{op_id} — {title} — ждём OK"
            kb.button(text=label, callback_data=f"supplier:wait:{request.id}:{mode}:{page}")
            continue

        icon = "📞" if request.request_type == "number" else "🔑"
        action = "номер" if request.request_type == "number" else "код"
        label = f"{icon} #{op_id} — {title} — {action}"
        kb.button(text=label, callback_data=f"supplier:reqf:{request.id}:{mode}:{page}")

    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"supplier:filter:{mode}:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Дальше", callback_data=f"supplier:filter:{mode}:{page + 1}")

    kb.button(text="🔄 Обновить раздел", callback_data=f"supplier:filter:{mode}:{page}")
    kb.button(text="📋 К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_wait_confirm_keyboard(mode: str = "active", page: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад к разделу", callback_data=f"supplier:filter:{mode}:{page}")
    kb.button(text="📋 К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 Главное меню", callback_data="supplier:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_empty_section_keyboard(mode: str = "active") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 К разделу заявок", callback_data="supplier:requests")
    kb.button(text="🏠 Главное меню", callback_data="supplier:panel")
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
        label = f"{icon} #{op_id} — {_short_button_text(order.service_name or order.product_name)}"
        kb.button(text=label, callback_data=f"buyer:order:{order.id}")

    kb.button(text="📦 Активный заказ", callback_data="buyer:active")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def buyer_empty_section_keyboard(back_to: str = "buyer:panel") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главное меню", callback_data=back_to)
    kb.adjust(1)
    return kb.as_markup()


def buyer_order_card_keyboard(order_id: int, status: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if status == "waiting_service":
        kb.button(text="🧩 Выбрать сервис", callback_data=f"svcpage:{order_id}:0")
    elif status == "number_sent_to_customer":
        kb.button(text="📩 Код отправлен", callback_data=f"code_sent:{order_id}")
        kb.button(text="⚠️ Номер не работает", callback_data=f"number_invalid:{order_id}")
    elif status == "code_sent_to_customer":
        kb.button(text="✅ OK, всё успешно", callback_data=f"confirm_success:{order_id}")
        kb.button(text="⚠️ Код не работает", callback_data=f"code_invalid:{order_id}")

    kb.button(text="⬅️ Назад к заказам", callback_data="buyer:orders")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()
# -----------------------------------------------------
