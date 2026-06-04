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
    kb.button(text="🧾 Последние заказы", callback_data="admin:last_orders")
    kb.button(text="🚚 Поставщики", callback_data="admin:suppliers")
    kb.button(text="🧩 Сервисы", callback_data="admin:services")
    kb.button(text="📚 Листы", callback_data="admin:lists")
    kb.button(text="✏️ Тексты", callback_data="admin:texts")
    kb.button(text="➕ Добавить поставщика", callback_data="admin:add_supplier_help")
    kb.button(text="🔗 Привязать товар/лист", callback_data="admin:bind_supplier_help")
    kb.button(text="➕ Добавить сервис", callback_data="admin:add_service_help")
    kb.button(text="📚 Добавить лист", callback_data="admin:list_help")
    kb.button(text="🔥 Эмодзи сервиса", callback_data="admin:service_emoji_help")
    kb.button(text="✏️ Изменить текст", callback_data="admin:set_text_help")
    kb.button(text="📖 Команды", callback_data="admin:commands")
    kb.button(text="🔄 Обновить", callback_data="admin:panel")

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
            [KeyboardButton(text="🚚 Панель поставщика")],
            [KeyboardButton(text="⏳ Заявки в ожидании")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Откройте панель или отправьте номер/код",
    )
