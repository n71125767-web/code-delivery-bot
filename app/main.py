import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from app.config import get_settings
from app.db import init_db
from app.handlers import build_router
from app.integrations.cryptopay import CryptoPayService
from app.middlewares import DatabaseMiddleware, SettingsMiddleware
from app.web import app


async def run_web(host: str, port: int) -> None:
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    await init_db()

    storage = RedisStorage.from_url(settings.redis_url)
    dispatcher = Dispatcher(storage=storage)
    router = build_router()

    database_middleware = DatabaseMiddleware()
    settings_middleware = SettingsMiddleware(settings)

    dispatcher.update.outer_middleware(settings_middleware)
    dispatcher.update.outer_middleware(database_middleware)
    dispatcher.include_router(router)

    bot = Bot(token=settings.bot_token)
    crypto_pay = CryptoPayService(settings)
    await crypto_pay.start()

    web_task = asyncio.create_task(
        run_web(settings.app_host, settings.app_port)
    )

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        web_task.cancel()
        await crypto_pay.close()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
