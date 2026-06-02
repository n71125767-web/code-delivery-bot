import os
from dotenv import load_dotenv

load_dotenv()


def parse_ids(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip()]


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

ADMIN_IDS = parse_ids(os.getenv("ADMIN_IDS", ""))
SUPPLIER_IDS = parse_ids(os.getenv("SUPPLIER_IDS", ""))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing in .env")