import hashlib
import logging
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

logger = logging.getLogger(__name__)


def normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    username = username.strip().replace("@", "").lower()
    return username or None


def make_hash(text: str | None) -> str:
    value = (text or "").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_message_key(source: str, chat_id: int | None, message_id: int | None, text: str | None) -> str:
    raw = f"{source}:{chat_id}:{message_id}:{text or ''}"
    return make_hash(raw)


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
) -> tuple[bool, str | None]:
    try:
        kwargs = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
        }

        if business_connection_id:
            kwargs["business_connection_id"] = business_connection_id

        await bot.send_message(**kwargs)
        return True, None

    except TelegramForbiddenError as e:
        return False, f"forbidden / bot was blocked: {e}"

    except TelegramBadRequest as e:
        err = str(e).lower()

        if "chat not found" in err:
            return False, f"chat not found: {e}"

        if "message is not modified" in err:
            return False, f"message is not modified: {e}"

        return False, f"bad request: {e}"

    except TelegramRetryAfter as e:
        return False, f"retry after {e.retry_after}: {e}"

    except TelegramNetworkError as e:
        return False, f"network error: {e}"

    except Exception as e:
        return False, f"unknown telegram error: {e}"