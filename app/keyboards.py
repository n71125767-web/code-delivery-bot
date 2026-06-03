from aiogram.utils.keyboard import InlineKeyboardBuilder


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
