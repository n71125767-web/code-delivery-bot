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

# Старый SUPPLIER_IDS оставляем как запасной список.
# После запуска админ может добавлять поставщиков командами прямо в боте.
SUPPLIER_IDS = parse_ids(os.getenv("SUPPLIER_IDS", ""))

SHOP_BOT_USERNAME = os.getenv("SHOP_BOT_USERNAME", "MrvlShopXBot").replace("@", "").strip().lower()

# Можно оставить пустым. Обычно business_connection_id берётся из входящего business_message.
ADMIN_BUSINESS_CONNECTION_ID = os.getenv("ADMIN_BUSINESS_CONNECTION_ID", "").strip() or None

IGNORE_OTHER_BOTS = os.getenv("IGNORE_OTHER_BOTS", "1").strip() == "1"

# Кнопки/разрешённые сервисы для покупателя.
SERVICE_OPTIONS = parse_words(
    os.getenv(
        "SERVICE_OPTIONS",
        "Telegram,WhatsApp,Google,Instagram,VK,TikTok,Discord,Facebook,Twitter,Steam",
    )
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Render Environment")

if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing in Render Environment")
