import os
from dotenv import load_dotenv

load_dotenv()


def parse_ids(value: str | None) -> list[int]:
    if not value:
        return []

    ids = []

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            ids.append(int(item))
        except ValueError:
            raise RuntimeError(
                f"Неверный ID в переменной окружения: {item}. "
                f"ID должен быть числом."
            )

    return ids


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_IDS = parse_ids(os.getenv("ADMIN_IDS"))

# Теперь это необязательная переменная.
# Поставщиков добавляем через команды бота.
SUPPLIER_IDS = parse_ids(os.getenv("SUPPLIER_IDS"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing")