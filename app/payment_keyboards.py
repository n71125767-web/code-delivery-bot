from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def invoice_keyboard(invoice_url: str, purchase_id: int, product_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатить через CryptoBot", url=invoice_url)
    kb.button(text="🔄 Проверить оплату", callback_data=f"payment:check:{purchase_id}")
    kb.button(
        text="⬅️ Назад к товару",
        callback_data=f"payment:back:{purchase_id}",
    )
    kb.adjust(2)
    return kb.as_markup()


def payment_result_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(2)
    return kb.as_markup()
