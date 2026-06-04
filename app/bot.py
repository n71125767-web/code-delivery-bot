import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import BOT_TOKEN
from app.database import init_db
from app.handlers import (
    on_message,
    on_business_message,
    on_callback_query,
    on_business_connection,
    on_edited_business_message,
    on_deleted_business_messages,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None),
    )

    dp = Dispatcher()

    # Без Router. Регистрируем обработчики напрямую.
    dp.message.register(on_message)
    dp.callback_query.register(on_callback_query)
    dp.business_message.register(on_business_message)
    dp.business_connection.register(on_business_connection)
    dp.edited_business_message.register(on_edited_business_message)
    dp.deleted_business_messages.register(on_deleted_business_messages)

    me = await bot.me()
    logger.info("Bot started: @%s id=%s", me.username, me.id)

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )


if __name__ == "__main__":
    asyncio.run(main())
