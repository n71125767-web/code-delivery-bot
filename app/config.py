import os
from dotenv import load_dotenv

load_dotenv()

def parse_ids(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip()]

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db").strip()
ADMIN_IDS = parse_ids(os.getenv("ADMIN_IDS", ""))
SUPPLIER_IDS = parse_ids(os.getenv("SUPPLIER_IDS", ""))
SHOP_BOT_USERNAME = os.getenv("SHOP_BOT_USERNAME", "MrvlShopXBot").replace("@", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing")
if not SUPPLIER_IDS:
    raise RuntimeError("SUPPLIER_IDS is missing")