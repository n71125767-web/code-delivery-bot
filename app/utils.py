import hashlib
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

def make_hash(text: str | None) -> str:
    value = (text or "").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def make_message_key(source: str, chat_id: int | None, message_id: int | None, text: str | None) -> str:
    raw = f"{source}:{chat_id}:{message_id}:{text or ''}"
    return make_hash(raw)

async def safe_send_message(bot: Bot, chat_id: int, text: str, business_connection_id: str | None = None):
    try:
        kwargs = {"chat_id": chat_id, "text": text}
        if business_connection_id:
            kwargs["business_connection_id"] = business_connection_id
        await bot.send_message(**kwargs)
        return True, None
    except Exception as e:
        logger.exception("Ошибка отправки сообщения")
        return False, str(e)

async def notify_admins(bot: Bot, text: str):
    from app.config import ADMIN_IDS
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text)