from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import SERVICE_PAGE_SIZE
from app.services import format_service_label


def confirm_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="OK, всё успешно", callback_data=f"confirm_success:{order_id}")
    kb.button(text="Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def number_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Код отправлен", callback_data=f"code_sent:{order_id}")
    kb.button(text="Номер не работает", callback_data=f"number_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def service_keyboard_from_services(services, page: int, max_page: int, order_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for service in services:
        slug = service.name.lower().replace(" ", "_")
        callback_data = f"service:{order_id or 0}:{slug}"
        kb.button(text=format_service_label(service), callback_data=callback_data)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(("Назад", f"svcpage:{order_id or 0}:{page - 1}"))
    if page < max_page:
        nav_buttons.append(("Дальше", f"svcpage:{order_id or 0}:{page + 1}"))

    for text, data in nav_buttons:
        kb.button(text=text, callback_data=data)

    kb.adjust(2)
    return kb.as_markup()


def service_keyboard(order_id: int | None = None) -> InlineKeyboardMarkup:
    """
    Fallback-заглушка. Основная клавиатура сервисов собирается в handlers.py из базы.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="Обновить список сервисов", callback_data=f"svcpage:{order_id or 0}:0")
    kb.adjust(1)
    return kb.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="Статус", callback_data="admin:status")
    kb.button(text="Последние заказы", callback_data="admin:last_orders")
    kb.button(text="Поставщики", callback_data="admin:suppliers")
    kb.button(text="Сервисы", callback_data="admin:services")
    kb.button(text="Тексты", callback_data="admin:texts")
    kb.button(text="Добавить поставщика", callback_data="admin:add_supplier_help")
    kb.button(text="Привязать товар", callback_data="admin:bind_supplier_help")
    kb.button(text="Добавить сервис", callback_data="admin:add_service_help")
    kb.button(text="Эмодзи сервиса", callback_data="admin:service_emoji_help")
    kb.button(text="Изменить текст", callback_data="admin:set_text_help")
    kb.button(text="Команды", callback_data="admin:commands")
    kb.button(text="Обновить панель", callback_data="admin:panel")

    kb.adjust(2)
    return kb.as_markup()
