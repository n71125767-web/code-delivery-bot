from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def invoice_keyboard(invoice_url: str, purchase_id: int, product_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # Telegram Bot API не поддерживает реальные цвета inline-кнопок.
    # Поэтому зелёную основную кнопку обозначаем единым зелёным маркером.
    kb.button(text="🟢 Оплатить CryptoBot", url=invoice_url)
    kb.button(text="🔄 Проверить оплату", callback_data=f"payment:check:{purchase_id}")
    kb.button(text="❌ Отмена", callback_data=f"payment:cancel:{purchase_id}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def payment_result_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(2)
    return kb.as_markup()


# ---------------- V77 clean payment keyboard ----------------
def invoice_keyboard(invoice_url: str, purchase_id: int, product_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Оплатить через CryptoBot", url=invoice_url)
    kb.button(text="🔄 Проверить оплату", callback_data=f"payment:check:{purchase_id}")
    kb.button(text="❌ Отменить оплату", callback_data=f"payment:cancel:{purchase_id}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()
