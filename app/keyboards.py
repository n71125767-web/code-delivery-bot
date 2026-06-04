from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import SERVICE_OPTIONS


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


def service_keyboard(order_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for service in SERVICE_OPTIONS:
        slug = service.lower().replace(" ", "_")
        if order_id:
            callback_data = f"service:{order_id}:{slug}"
        else:
            callback_data = f"service:0:{slug}"
        kb.button(text=service, callback_data=callback_data)

    kb.adjust(2)
    return kb.as_markup()
