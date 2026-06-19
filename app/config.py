import os
from dotenv import load_dotenv

load_dotenv()


def parse_ids(value: str) -> list[int]:
    if not value:
        return []

    result: list[int] = []
    invalid: list[str] = []

    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            invalid.append(item)

    if invalid:
        raise RuntimeError(
            "Invalid Telegram ID values: " + ", ".join(invalid)
        )

    return result


def parse_words(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db").strip()

ADMIN_IDS = parse_ids(os.getenv("ADMIN_IDS", ""))
GA_IDS = sorted(set(ADMIN_IDS + parse_ids(os.getenv("GA_IDS", ""))))

# Общий чат/ЛС для алертов админам. Не обязательно.
ADMIN_ALERT_CHAT_IDS = parse_ids(
    os.getenv("ADMIN_ALERT_CHAT_ID", "")
)
ADMIN_ALERT_CHAT_ID = (
    ADMIN_ALERT_CHAT_IDS[0]
    if ADMIN_ALERT_CHAT_IDS
    else None
)

# Старый SUPPLIER_IDS оставляем как стартовый список.
# Новых поставщиков можно добавлять через /add_supplier.


# Можно оставить пустым. Обычно business_connection_id берётся из входящего business_message.
ADMIN_BUSINESS_CONNECTION_ID = (
    os.getenv("ADMIN_BUSINESS_CONNECTION_ID", "").strip() or None
)

IGNORE_OTHER_BOTS = os.getenv("IGNORE_OTHER_BOTS", "1").strip() == "1"

SERVICE_OPTIONS = parse_words(
    os.getenv(
        "SERVICE_OPTIONS",
        "Telegram,WhatsApp,Google,Instagram,VK,TikTok,Discord,Facebook,Twitter,Steam,Avito,Yandex,Mail.ru,Microsoft,Apple",
    )
)

SERVICE_PAGE_SIZE = int(os.getenv("SERVICE_PAGE_SIZE", "8"))
SUPPLIER_PAGE_SIZE = int(os.getenv("SUPPLIER_PAGE_SIZE", "8"))
PROBLEM_COOLDOWN_SECONDS = int(os.getenv("PROBLEM_COOLDOWN_SECONDS", "30"))
POPULAR_SERVICE_THRESHOLD = int(os.getenv("POPULAR_SERVICE_THRESHOLD", "3"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Render Environment")

if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing in Render Environment")


# FIX_MARKER_AUTODELETE_IGNORE_TEXT_BUTTONS=v2
AUTO_DELETE_MESSAGES = os.getenv("AUTO_DELETE_MESSAGES", "0").strip() == "1"
AUTO_DELETE_DELAY_SECONDS = int(os.getenv("AUTO_DELETE_DELAY_SECONDS", "3"))
AUTO_DELETE_UNKNOWN_BUYERS = os.getenv("AUTO_DELETE_UNKNOWN_BUYERS", "0").strip() == "1"
IGNORE_NON_BUYERS = os.getenv("IGNORE_NON_BUYERS", "0").strip() == "1"
NOTIFY_UNKNOWN_BUYERS = os.getenv("NOTIFY_UNKNOWN_BUYERS", "1").strip() == "1"


# Финальные настройки антиспама кнопок.
BUTTON_COOLDOWN_SECONDS = int(os.getenv("BUTTON_COOLDOWN_SECONDS", "2"))
BUYER_ORDERS_LIMIT = int(os.getenv("BUYER_ORDERS_LIMIT", "10"))

# Release patch v13
BUG_REPORT_CHAT_IDS = parse_ids(os.getenv("BUG_REPORT_CHAT_IDS", ""))
SUPPLIER_IMMUNITY_SKIP_AUTODELETE = (
    os.getenv("SUPPLIER_IMMUNITY_SKIP_AUTODELETE", "1").strip() == "1"
)


# Proxyline API integration.
# ВАЖНО: настоящий ключ задавай только в Render Environment, не коммить в GitHub.
PROXYLINE_ENABLED = os.getenv("PROXYLINE_ENABLED", "0").strip() == "1"
PROXYLINE_API_KEY = os.getenv("PROXYLINE_API_KEY", "").strip()
PROXYLINE_DEFAULT_COUNTRY = os.getenv("PROXYLINE_DEFAULT_COUNTRY", "ru").strip().lower()
PROXYLINE_DEFAULT_PERIOD = int(os.getenv("PROXYLINE_DEFAULT_PERIOD", "30"))
PROXYLINE_DEFAULT_COUNT = int(os.getenv("PROXYLINE_DEFAULT_COUNT", "1"))
PROXYLINE_DEFAULT_IP_VERSION = int(os.getenv("PROXYLINE_DEFAULT_IP_VERSION", "4"))
PROXYLINE_DEFAULT_TYPE = (
    os.getenv("PROXYLINE_DEFAULT_TYPE", "dedicated").strip().lower()
)
# Режим MTProxy/Telegram-прокси.
# stock — выдавать реальные MTProxy строки из склада.
# api — покупать через Proxyline API. У публичного new-order Proxyline типы только dedicated/shared,
# поэтому по умолчанию для Telegram-прокси используем dedicated.
PROXYLINE_MTPROXY_MODE = os.getenv("PROXYLINE_MTPROXY_MODE", "api").strip().lower()
PROXYLINE_MTPROXY_API_TYPE = os.getenv("PROXYLINE_MTPROXY_API_TYPE", "dedicated").strip().lower()
# Старое имя оставлено для совместимости с предыдущими деплоями.
PROXYLINE_MTPROXY_TYPE = os.getenv("PROXYLINE_MTPROXY_TYPE", PROXYLINE_MTPROXY_API_TYPE).strip().lower()
PROXYLINE_COUPON = os.getenv("PROXYLINE_COUPON", "").strip()
# JSON maps own product names to Proxyline parameters.
# Пример: {"Прокси RU 30 дней":{"country":"ru","period":30,"count":1,"ip_version":4,"type":"dedicated"}}
PROXYLINE_PRODUCTS_JSON = os.getenv("PROXYLINE_PRODUCTS_JSON", "").strip()
PROXYLINE_COUNTRIES_JSON = os.getenv("PROXYLINE_COUNTRIES_JSON", "").strip()

# Optional secondary proxy provider for standard/residential tariffs.
# Configure only if you have a compatible Proxys API adapter/base URL.
PROXYS_ENABLED = os.getenv("PROXYS_ENABLED", "0").strip() == "1"
PROXYS_API_KEY = os.getenv("PROXYS_API_KEY", "").strip()
PROXYS_API_BASE_URL = os.getenv("PROXYS_API_BASE_URL", "").strip()


# Crypto Pay / @CryptoBot
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "").strip()
CRYPTO_PAY_NETWORK = os.getenv("CRYPTO_PAY_NETWORK", "testnet").strip().lower()
CRYPTO_PAY_ACCEPTED_ASSETS = os.getenv(
    "CRYPTO_PAY_ACCEPTED_ASSETS",
    "USDT,TON,BTC,ETH,LTC,BNB,TRX,USDC",
).strip()
CRYPTO_PAY_ACCEPTED_ASSET_LIST = [
    item.strip().upper()
    for item in CRYPTO_PAY_ACCEPTED_ASSETS.split(",")
    if item.strip()
]
CRYPTO_PAY_INVOICE_EXPIRES_SECONDS = int(
    os.getenv("CRYPTO_PAY_INVOICE_EXPIRES_SECONDS", "3600")
)
CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS = int(
    os.getenv("CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS", "300")
)
CRYPTO_PAY_PENDING_LIMIT = int(os.getenv("CRYPTO_PAY_PENDING_LIMIT", "50"))
CRYPTO_PAY_DELIVERY_STALE_SECONDS = int(
    os.getenv("CRYPTO_PAY_DELIVERY_STALE_SECONDS", "600")
)
CRYPTO_PAY_ENABLED = bool(CRYPTO_PAY_TOKEN)

# Direct wallet payments. The bot creates a pending wallet payment and can mark it
# as paid either by admin command or by a signed /wallet/webhook event from your
# own blockchain/payment monitor.
WALLET_PAYMENT_ENABLED = os.getenv("WALLET_PAYMENT_ENABLED", "0").strip() == "1"
WALLET_PAYMENT_ADDRESS = os.getenv("WALLET_PAYMENT_ADDRESS", "").strip()
WALLET_PAYMENT_CURRENCY = os.getenv("WALLET_PAYMENT_CURRENCY", "USDT").strip().upper()
WALLET_WEBHOOK_SECRET = os.getenv("WALLET_WEBHOOK_SECRET", "").strip()

MARKETPLACE_ENABLED = os.getenv("MARKETPLACE_ENABLED", "1").strip() == "1"

if CRYPTO_PAY_NETWORK not in {"mainnet", "testnet"}:
    raise RuntimeError("CRYPTO_PAY_NETWORK must be mainnet or testnet")
if CRYPTO_PAY_INVOICE_EXPIRES_SECONDS < 60:
    raise RuntimeError("CRYPTO_PAY_INVOICE_EXPIRES_SECONDS must be at least 60")
if CRYPTO_PAY_PENDING_LIMIT < 1:
    raise RuntimeError("CRYPTO_PAY_PENDING_LIMIT must be at least 1")
if CRYPTO_PAY_DELIVERY_STALE_SECONDS < 60:
    raise RuntimeError("CRYPTO_PAY_DELIVERY_STALE_SECONDS must be at least 60")


if SERVICE_PAGE_SIZE < 1:
    raise RuntimeError("SERVICE_PAGE_SIZE must be at least 1")
if SUPPLIER_PAGE_SIZE < 1:
    raise RuntimeError("SUPPLIER_PAGE_SIZE must be at least 1")
if BUTTON_COOLDOWN_SECONDS < 0:
    raise RuntimeError("BUTTON_COOLDOWN_SECONDS cannot be negative")
if BUYER_ORDERS_LIMIT < 1:
    raise RuntimeError("BUYER_ORDERS_LIMIT must be at least 1")
if PROXYLINE_DEFAULT_PERIOD < 1:
    raise RuntimeError("PROXYLINE_DEFAULT_PERIOD must be at least 1")
if PROXYLINE_DEFAULT_COUNT < 1:
    raise RuntimeError("PROXYLINE_DEFAULT_COUNT must be at least 1")
if PROXYLINE_DEFAULT_IP_VERSION not in {4, 6}:
    raise RuntimeError("PROXYLINE_DEFAULT_IP_VERSION must be 4 or 6")

# Production safety. Render should use PostgreSQL unless explicitly overridden.
ALLOW_SQLITE_ON_RENDER = os.getenv("ALLOW_SQLITE_ON_RENDER", "0").strip() == "1"
if (
    os.getenv("RENDER")
    and DATABASE_URL.startswith("sqlite")
    and not ALLOW_SQLITE_ON_RENDER
):
    raise RuntimeError(
        "Render production requires DATABASE_URL for PostgreSQL; SQLite is ephemeral"
    )

STOCK_RESERVATION_TTL_SECONDS = int(
    os.getenv("STOCK_RESERVATION_TTL_SECONDS", "3900")
)


class Settings:
    """Backward-compatible settings view for older modular handlers.

    The active bot uses module-level constants, but older files may import
    Settings from app.config. Keeping this class prevents import-time crashes
    during mixed/stale deployments.
    """

    BOT_TOKEN = BOT_TOKEN
    DATABASE_URL = DATABASE_URL
    ADMIN_IDS = ADMIN_IDS
    GA_IDS = GA_IDS
    ADMIN_ALERT_CHAT_IDS = ADMIN_ALERT_CHAT_IDS
    ADMIN_ALERT_CHAT_ID = ADMIN_ALERT_CHAT_ID
    ADMIN_BUSINESS_CONNECTION_ID = ADMIN_BUSINESS_CONNECTION_ID
    IGNORE_OTHER_BOTS = IGNORE_OTHER_BOTS
    SERVICE_OPTIONS = SERVICE_OPTIONS
    SERVICE_PAGE_SIZE = SERVICE_PAGE_SIZE
    SUPPLIER_PAGE_SIZE = SUPPLIER_PAGE_SIZE
    PROBLEM_COOLDOWN_SECONDS = PROBLEM_COOLDOWN_SECONDS
    POPULAR_SERVICE_THRESHOLD = POPULAR_SERVICE_THRESHOLD
    AUTO_DELETE_MESSAGES = AUTO_DELETE_MESSAGES
    AUTO_DELETE_DELAY_SECONDS = AUTO_DELETE_DELAY_SECONDS
    AUTO_DELETE_UNKNOWN_BUYERS = AUTO_DELETE_UNKNOWN_BUYERS
    IGNORE_NON_BUYERS = IGNORE_NON_BUYERS
    NOTIFY_UNKNOWN_BUYERS = NOTIFY_UNKNOWN_BUYERS
    BUTTON_COOLDOWN_SECONDS = BUTTON_COOLDOWN_SECONDS
    BUYER_ORDERS_LIMIT = BUYER_ORDERS_LIMIT
    BUG_REPORT_CHAT_IDS = BUG_REPORT_CHAT_IDS
    SUPPLIER_IMMUNITY_SKIP_AUTODELETE = SUPPLIER_IMMUNITY_SKIP_AUTODELETE
    PROXYLINE_ENABLED = PROXYLINE_ENABLED
    PROXYLINE_API_KEY = PROXYLINE_API_KEY
    PROXYLINE_DEFAULT_COUNTRY = PROXYLINE_DEFAULT_COUNTRY
    PROXYLINE_DEFAULT_PERIOD = PROXYLINE_DEFAULT_PERIOD
    PROXYLINE_DEFAULT_COUNT = PROXYLINE_DEFAULT_COUNT
    PROXYLINE_DEFAULT_IP_VERSION = PROXYLINE_DEFAULT_IP_VERSION
    PROXYLINE_DEFAULT_TYPE = PROXYLINE_DEFAULT_TYPE
    PROXYLINE_MTPROXY_MODE = PROXYLINE_MTPROXY_MODE
    PROXYLINE_MTPROXY_API_TYPE = PROXYLINE_MTPROXY_API_TYPE
    PROXYLINE_MTPROXY_TYPE = PROXYLINE_MTPROXY_TYPE
    PROXYLINE_COUPON = PROXYLINE_COUPON
    PROXYLINE_PRODUCTS_JSON = PROXYLINE_PRODUCTS_JSON
    PROXYLINE_COUNTRIES_JSON = PROXYLINE_COUNTRIES_JSON
    CRYPTO_PAY_TOKEN = CRYPTO_PAY_TOKEN
    CRYPTO_PAY_NETWORK = CRYPTO_PAY_NETWORK
    CRYPTO_PAY_ACCEPTED_ASSETS = CRYPTO_PAY_ACCEPTED_ASSETS
    CRYPTO_PAY_ACCEPTED_ASSET_LIST = CRYPTO_PAY_ACCEPTED_ASSET_LIST
    CRYPTO_PAY_INVOICE_EXPIRES_SECONDS = CRYPTO_PAY_INVOICE_EXPIRES_SECONDS
    CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS = CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS
    CRYPTO_PAY_PENDING_LIMIT = CRYPTO_PAY_PENDING_LIMIT
    CRYPTO_PAY_DELIVERY_STALE_SECONDS = CRYPTO_PAY_DELIVERY_STALE_SECONDS
    CRYPTO_PAY_ENABLED = CRYPTO_PAY_ENABLED
    WALLET_PAYMENT_ENABLED = WALLET_PAYMENT_ENABLED
    WALLET_PAYMENT_ADDRESS = WALLET_PAYMENT_ADDRESS
    WALLET_PAYMENT_CURRENCY = WALLET_PAYMENT_CURRENCY
    WALLET_WEBHOOK_SECRET = WALLET_WEBHOOK_SECRET
    MARKETPLACE_ENABLED = MARKETPLACE_ENABLED
    ALLOW_SQLITE_ON_RENDER = ALLOW_SQLITE_ON_RENDER
    STOCK_RESERVATION_TTL_SECONDS = STOCK_RESERVATION_TTL_SECONDS
