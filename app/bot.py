import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.runtime_state import restore_runtime_state, runtime_state_loop, save_runtime_state
from app.broadcast_service import resume_broadcast_jobs
from app.config import (
    BOT_TOKEN,
    CRYPTO_PAY_ENABLED,
    CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS,
)
from app.cryptopay_service import (
    close_crypto_client,
    process_webhook,
    recover_pending_payments,
)
from sqlalchemy import text
from app.database import SessionLocal, init_db
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

_health_runner = None
_health_start_lock = asyncio.Lock()
_web_bot: Bot | None = None


async def health(_request):
    db_ok = False
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("HEALTH_DB_FAILED")
    status = 200 if db_ok else 503
    return web.json_response(
        {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "cryptopay_enabled": CRYPTO_PAY_ENABLED,
            "bot_ready": _web_bot is not None,
        },
        status=status,
    )


async def crypto_webhook(request: web.Request):
    if not CRYPTO_PAY_ENABLED:
        return web.Response(status=503, text="cryptopay disabled")
    if _web_bot is None:
        return web.Response(status=503, text="bot unavailable")

    raw_body = await request.read()
    signature = request.headers.get("crypto-pay-api-signature")
    status, text = await process_webhook(_web_bot, raw_body, signature)
    return web.Response(status=status, text=text)


async def start_health_server(bot: Bot):
    global _health_runner, _web_bot
    _web_bot = bot

    async with _health_start_lock:
        if _health_runner is not None:
            return _health_runner

        port = int(os.getenv("PORT", "10000"))
        app = web.Application(client_max_size=1024 * 1024)
        app.router.add_get("/", health)
        app.router.add_get("/health", health)
        app.router.add_post("/crypto/webhook", crypto_webhook)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        _health_runner = runner
        logger.info("HTTP server started on port %s", port)
        if CRYPTO_PAY_ENABLED:
            logger.info("Crypto Pay webhook path configured: /crypto/webhook")
        return runner


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.register(on_message)
    dp.callback_query.register(on_callback_query)
    dp.business_message.register(on_business_message)
    dp.business_connection.register(on_business_connection)
    dp.edited_business_message.register(on_edited_business_message)
    dp.deleted_business_messages.register(on_deleted_business_messages)
    return dp


async def payment_recovery_loop(bot: Bot) -> None:
    while True:
        try:
            if CRYPTO_PAY_ENABLED:
                recovered = await recover_pending_payments(bot)
                if recovered:
                    logger.info("Recovered paid invoices: %s", recovered)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment recovery cycle failed")
        await asyncio.sleep(max(30, CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS))


async def main():
    logger.info("Starting MCS Clean V33")
    await init_db()
    await restore_runtime_state()
    logger.info("Database initialization and runtime-state restore completed")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    await start_health_server(bot)
    recovery_task = asyncio.create_task(payment_recovery_loop(bot))
    state_task = asyncio.create_task(runtime_state_loop())
    resumed_broadcast_tasks = await resume_broadcast_jobs(bot)

    try:
        me = await bot.me()
        logger.info("Bot started: @%s id=%s", me.username, me.id)
        logger.info("FIX_MARKER_CRYPTOPAY_STABLE=v26 loaded")
        logger.info("FIX_MARKER_MCS_HARDENED=v31 loaded")
        logger.info("FIX_MARKER_MCS_CLEAN=v33 loaded")
        logger.info("FIX_MARKER_MCS_HARDENED=v34 loaded")
        dp = build_dispatcher()
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
    finally:
        recovery_task.cancel()
        state_task.cancel()
        for task in resumed_broadcast_tasks:
            task.cancel()
        await asyncio.gather(recovery_task, state_task, *resumed_broadcast_tasks, return_exceptions=True)
        await save_runtime_state()
        await close_crypto_client()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
