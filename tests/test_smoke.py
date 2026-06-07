import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test-smoke.db")

from app.keyboards import buyer_inline_menu_keyboard, buyer_main_reply_keyboard


def callback_set(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def reply_text_set(markup):
    return {button.text for row in markup.keyboard for button in row}


def test_buyer_inline_menu():
    buyer = callback_set(buyer_inline_menu_keyboard(is_admin=False))
    admin = callback_set(buyer_inline_menu_keyboard(is_admin=True))

    assert {"buyer:shop", "buyer:feedback", "buyer:faq"} <= buyer
    assert "admin:panel" not in buyer
    assert "admin:panel" in admin


def test_main_reply_keyboard():
    buyer = reply_text_set(buyer_main_reply_keyboard(is_admin=False))
    admin = reply_text_set(buyer_main_reply_keyboard(is_admin=True))

    assert {"🛒 Товары", "🌐 Прокси", "📱 Номера"} <= buyer
    assert "⚙️ Админ меню" not in buyer
    assert "⚙️ Админ меню" in admin


def test_proxy_entry_is_local_catalog():
    buyer = callback_set(buyer_inline_menu_keyboard(is_admin=False))
    assert "buyer:proxy_catalog" in buyer
