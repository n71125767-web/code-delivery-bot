import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test-smoke.db")

from app.keyboards import buyer_inline_menu_keyboard, buyer_main_reply_keyboard


def test_buyer_reply_admin_visibility():
    buyer = buyer_main_reply_keyboard(is_admin=False)
    admin = buyer_main_reply_keyboard(is_admin=True)

    buyer_texts = {button.text for row in buyer.keyboard for button in row}
    admin_texts = {button.text for row in admin.keyboard for button in row}

    assert "⚙️ Админ меню" not in buyer_texts
    assert "⚙️ Админ меню" in admin_texts


def test_buyer_inline_callbacks():
    markup = buyer_inline_menu_keyboard()
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }

    assert "buyer:shop" in callbacks
    assert "buyer:proxy_catalog" in callbacks
    assert "buyer:number_catalog" in callbacks
