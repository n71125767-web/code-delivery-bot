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


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db").strip()

ADMIN_IDS = parse_ids(os.getenv("ADMIN_IDS", ""))
SUPPLIER_IDS = parse_ids(os.getenv("SUPPLIER_IDS", ""))

SHOP_BOT_USERNAME = os.getenv("SHOP_BOT_USERNAME", "MrvlShopXBot").replace("@", "").strip().lower()

# ВАЖНО:
# Не обязательно заполнять вручную. Правильный business_connection_id бот получает
# из входящего business_message и сохраняет в заказ.
# Если всё же указать ADMIN_BUSINESS_CONNECTION_ID, он будет запасным вариантом.
ADMIN_BUSINESS_CONNECTION_ID = os.getenv("ADMIN_BUSINESS_CONNECTION_ID", "").strip() or None

IGNORE_OTHER_BOTS = os.getenv("IGNORE_OTHER_BOTS", "1").strip() == "1"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Render Environment")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing in Render Environment")
if not SUPPLIER_IDS:
    raise RuntimeError("SUPPLIER_IDS is missing in Render Environment")
