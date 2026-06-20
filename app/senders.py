import logging
from aiogram import Bot
from aiogram.types import Message

from app.text_utils import plain_text

logger = logging.getLogger(__name__)


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
    allow_normal_fallback: bool = True,
):
    """
    V78: Telegram Business полностью отключён.
    Все сообщения отправляются только в обычный чат с ботом.
    Параметры business_connection_id/allow_normal_fallback оставлены для совместимости
    со старым кодом, но больше не используются.
    """
    text = plain_text(text)
    me = await bot.me()
    has_keyboard = reply_markup is not None

    if chat_id == me.id:
        logger.info("SKIP_SEND_TO_SELF chat_id=%s has_keyboard=%s", chat_id, has_keyboard)
        return False

    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        logger.info(
            "SEND_OK_NORMAL chat_id=%s message_id=%s has_keyboard=%s",
            chat_id,
            getattr(msg, "message_id", None),
            has_keyboard,
        )
        return msg
    except Exception as exc:
        logger.exception(
            "SEND_FAILED_FINAL chat_id=%s has_keyboard=%s error=%s",
            chat_id,
            has_keyboard,
            exc,
        )
        return False


async def answer_message(
    bot: Bot,
    message: Message,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
):
    """V78: отвечает только в обычный чат с ботом, без Telegram Business."""
    text = plain_text(text)
    me = await bot.me()

    if message.from_user and message.from_user.id == me.id:
        logger.info("SKIP ANSWER: message from own bot")
        return False

    try:
        return await message.answer(text, reply_markup=reply_markup)
    except Exception as exc:
        logger.exception("message.answer failed error=%s", exc)
        return False
