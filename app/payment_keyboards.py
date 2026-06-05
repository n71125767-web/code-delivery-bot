from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def invoice_keyboard(invoice_url: str, purchase_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатить через CryptoBot", url=invoice_url, style="success")
    kb.button(text="🔄 Проверить оплату", callback_data=f"payment:check:{purchase_id}")
    kb.button(text="⬅️ Назад к товару", callback_data=f"payment:back:{purchase_id}", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def payment_result_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()
