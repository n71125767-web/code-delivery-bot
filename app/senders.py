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
    Возвращает Message при успехе или False при ошибке.

    Улучшение v9:
    1. Логирует, есть ли inline/reply-кнопки.
    2. Если отправка через business_connection_id не прошла,
       обычный fallback можно отключить через allow_normal_fallback=False.
       Это важно для Telegram Business: иначе уведомления начинают приходить
       в обычный чат с ботом, а не в Business-чат аккаунта.
    """
    text = plain_text(text)
    me = await bot.me()
    has_keyboard = reply_markup is not None

    if chat_id == me.id:
        logger.info(
            "SKIP_SEND_TO_SELF chat_id=%s has_keyboard=%s", chat_id, has_keyboard
        )
        return False

    if business_connection_id:
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                business_connection_id=business_connection_id,
                reply_markup=reply_markup,
            )
            logger.info(
                "SEND_OK_BUSINESS chat_id=%s message_id=%s business_connection_id=%s has_keyboard=%s",
                chat_id,
                getattr(msg, "message_id", None),
                business_connection_id,
                has_keyboard,
            )
            return msg
        except Exception as exc:
            logger.warning(
                "SEND_FAILED_BUSINESS chat_id=%s business_connection_id=%s has_keyboard=%s allow_normal_fallback=%s error=%s",
                chat_id,
                business_connection_id,
                has_keyboard,
                allow_normal_fallback,
                exc,
            )
            if not allow_normal_fallback:
                logger.info(
                    "SEND_NORMAL_FALLBACK_DISABLED chat_id=%s business_connection_id=%s has_keyboard=%s",
                    chat_id,
                    business_connection_id,
                    has_keyboard,
                )
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
            "SEND_FAILED_FINAL chat_id=%s business_connection_id=%s has_keyboard=%s error=%s",
            chat_id,
            business_connection_id,
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
    text = plain_text(text)
    me = await bot.me()

    if message.from_user and message.from_user.id == me.id:
        logger.info("SKIP ANSWER: message from own bot")
        return False

    if business_connection_id:
        return await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            text=text,
            business_connection_id=business_connection_id,
            reply_markup=reply_markup,
            allow_normal_fallback=False,
        )

    try:
        return await message.answer(text, reply_markup=reply_markup)
    except Exception as exc:
        logger.exception("message.answer failed error=%s", exc)
        return False
