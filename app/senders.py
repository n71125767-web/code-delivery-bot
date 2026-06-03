import logging
from aiogram import Bot
from aiogram.types import Message

logger = logging.getLogger(__name__)


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
) -> bool:
    """
    Если передан business_connection_id — сообщение уходит от Business-аккаунта.
    Если нет — обычным ботом.

    Нельзя отправлять самому боту и нельзя использовать business_id вслепую:
    Telegram даст отправить через Business только в чаты, доступные этому business_connection.
    """
    me = await bot.me()
    if chat_id == me.id:
        logger.info("Skip self-send to bot id=%s", chat_id)
        return False

    try:
        if business_connection_id:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                business_connection_id=business_connection_id,
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
        return True
    except Exception as exc:
        logger.exception(
            "Send failed chat_id=%s business_connection_id=%s error=%s",
            chat_id,
            business_connection_id,
            exc,
        )
        return False


async def answer_message(
    bot: Bot,
    message: Message,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
) -> bool:
    me = await bot.me()
    if message.from_user and message.from_user.id == me.id:
        logger.info("Skip answering own bot message")
        return False

    if business_connection_id:
        return await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            text=text,
            business_connection_id=business_connection_id,
            reply_markup=reply_markup,
        )

    try:
        await message.answer(text, reply_markup=reply_markup)
        return True
    except Exception:
        logger.exception("message.answer failed")
        return False
