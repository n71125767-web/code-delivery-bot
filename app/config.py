import os
from dotenv import load_dotenv

load_dotenv()


def parse_ids(value: str) -> list[int]:
    if not value:
        return []
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            result.append(int(item))
    return result


def parse_words(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db").strip()

ADMIN_IDS = parse_ids(os.getenv("ADMIN_IDS", ""))

# Общий чат/ЛС для алертов админам. Не обязательно.
ADMIN_ALERT_CHAT_ID = os.getenv("ADMIN_ALERT_CHAT_ID", "").strip()
ADMIN_ALERT_CHAT_ID = int(ADMIN_ALERT_CHAT_ID) if ADMIN_ALERT_CHAT_ID else None

# Старый SUPPLIER_IDS оставляем как стартовый список.
# Новых поставщиков можно добавлять через /add_supplier.
SUPPLIER_IDS = parse_ids(os.getenv("SUPPLIER_IDS", ""))

SHOP_BOT_USERNAME = os.getenv("SHOP_BOT_USERNAME", "MrvlShopXBot").replace("@", "").strip().lower()

# Можно оставить пустым. Обычно business_connection_id берётся из входящего business_message.
ADMIN_BUSINESS_CONNECTION_ID = os.getenv("ADMIN_BUSINESS_CONNECTION_ID", "").strip() or None

IGNORE_OTHER_BOTS = os.getenv("IGNORE_OTHER_BOTS", "1").strip() == "1"

SERVICE_OPTIONS = parse_words(
    os.getenv(
        "SERVICE_OPTIONS",
        "Telegram,WhatsApp,Google,Instagram,VK,TikTok,Discord,Facebook,Twitter,Steam,Avito,Yandex,Mail.ru,Microsoft,Apple",
    )
)

SERVICE_PAGE_SIZE = int(os.getenv("SERVICE_PAGE_SIZE", "8"))
SUPPLIER_PAGE_SIZE = int(os.getenv("SUPPLIER_PAGE_SIZE", "5"))
PROBLEM_COOLDOWN_SECONDS = int(os.getenv("PROBLEM_COOLDOWN_SECONDS", "60"))
POPULAR_SERVICE_THRESHOLD = int(os.getenv("POPULAR_SERVICE_THRESHOLD", "3"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Render Environment")

if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing in Render Environment")


# FIX_MARKER_AUTODELETE_IGNORE_TEXT_BUTTONS=v2
AUTO_DELETE_MESSAGES = os.getenv("AUTO_DELETE_MESSAGES", "1").strip() == "1"
AUTO_DELETE_DELAY_SECONDS = int(os.getenv("AUTO_DELETE_DELAY_SECONDS", "30"))
AUTO_DELETE_UNKNOWN_BUYERS = os.getenv("AUTO_DELETE_UNKNOWN_BUYERS", "1").strip() == "1"
IGNORE_NON_BUYERS = os.getenv("IGNORE_NON_BUYERS", "1").strip() == "1"
NOTIFY_UNKNOWN_BUYERS = os.getenv("NOTIFY_UNKNOWN_BUYERS", "0").strip() == "1"


# Финальные настройки антиспама кнопок.
BUTTON_COOLDOWN_SECONDS = int(os.getenv("BUTTON_COOLDOWN_SECONDS", "2"))
BUYER_ORDERS_LIMIT = int(os.getenv("BUYER_ORDERS_LIMIT", "10"))

# Release patch v13
BUG_REPORT_CHAT_IDS = parse_ids(os.getenv("BUG_REPORT_CHAT_IDS", ""))
SUPPLIER_IMMUNITY_SKIP_AUTODELETE = os.getenv("SUPPLIER_IMMUNITY_SKIP_AUTODELETE", "1").strip() == "1"
