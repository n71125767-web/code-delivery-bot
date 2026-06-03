import logging
from aiogram import Bot, types
from app.config import ADMIN_BUSINESS_CONNECTION_ID

logger = logging.getLogger(__name__)


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
) -> bool:
    # Не отправляем сообщение самому себе
    if chat_id == bot.id:
        logger.info("Попытка написать себе, пропускаем")
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
    except Exception:
        logger.exception("Не смог отправить сообщение chat_id=%s", chat_id)
        return False


async def answer_message(
    bot: Bot,
    message: types.Message,
    text: str,
    business_connection_id: str | None = None,
    reply_markup=None,
) -> bool:
    if business_connection_id:
        return await safe_send_message(
            bot=bot,
            chat_id=message.chat.id,
            text=text,
            business_connection_id=business_connection_id,
            reply_markup=reply_markup,
        )

    try:
        # Не отвечаем самому себе
        if message.from_user and message.from_user.id == bot.id:
            logger.info("Попытка ответить самому себе, пропускаем")
            return False
        await message.answer(text, reply_markup=reply_markup)
        return True
    except Exception:
        logger.exception("Не смог ответить через message.answer")
        return False
