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
ADMIN_BUSINESS_CONNECTION_ID = os.getenv("ADMIN_BUSINESS_CONNECTION_ID")

IGNORE_OTHER_BOTS = os.getenv("IGNORE_OTHER_BOTS", "1").strip() == "1"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing in .env")
if not SUPPLIER_IDS:
    raise RuntimeError("SUPPLIER_IDS is missing in .env")
if not ADMIN_BUSINESS_CONNECTION_ID:
    raise RuntimeError("ADMIN_BUSINESS_CONNECTION_ID is missing in .env")
