import os
import json
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


# Proxyline API integration.
# ВАЖНО: настоящий ключ задавай только в Render Environment, не коммить в GitHub.
PROXYLINE_ENABLED = os.getenv("PROXYLINE_ENABLED", "0").strip() == "1"
PROXYLINE_API_KEY = os.getenv("PROXYLINE_API_KEY", "").strip()
PROXYLINE_DEFAULT_COUNTRY = os.getenv("PROXYLINE_DEFAULT_COUNTRY", "ru").strip().lower()
PROXYLINE_DEFAULT_PERIOD = int(os.getenv("PROXYLINE_DEFAULT_PERIOD", "30"))
PROXYLINE_DEFAULT_COUNT = int(os.getenv("PROXYLINE_DEFAULT_COUNT", "1"))
PROXYLINE_DEFAULT_IP_VERSION = int(os.getenv("PROXYLINE_DEFAULT_IP_VERSION", "4"))
PROXYLINE_DEFAULT_TYPE = os.getenv("PROXYLINE_DEFAULT_TYPE", "dedicated").strip().lower()
PROXYLINE_COUPON = os.getenv("PROXYLINE_COUPON", "").strip()
# Через JSON можно точно сопоставить названия товаров Admaker с параметрами Proxyline.
# Пример: {"Прокси RU 30 дней":{"country":"ru","period":30,"count":1,"ip_version":4,"type":"dedicated"}}
PROXYLINE_PRODUCTS_JSON = os.getenv("PROXYLINE_PRODUCTS_JSON", "").strip()

# JSON mapping UI proxy package key -> Admaker Product ID.
# Example: {"mt_1m":123,"premium_3m":456}
try:
    PROXY_PACKAGE_PRODUCT_IDS = json.loads(os.getenv("PROXY_PACKAGE_PRODUCT_IDS_JSON", "{}") or "{}")
except Exception:
    PROXY_PACKAGE_PRODUCT_IDS = {}
