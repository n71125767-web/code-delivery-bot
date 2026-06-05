import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import (
    BOT_TOKEN,
    CRYPTO_PAY_ENABLED,
    CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS,
    CRYPTO_PAY_WEBHOOK_SECRET,
)
from app.cryptopay_service import (
    close_crypto_client,
    process_webhook,
    recover_pending_payments,
)
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

_health_runner = None
_health_start_lock = asyncio.Lock()
_web_bot: Bot | None = None


async def health(_request):
    return web.json_response(
        {
            "status": "ok",
            "cryptopay_enabled": CRYPTO_PAY_ENABLED,
        }
    )


async def crypto_webhook(request: web.Request):
    if not CRYPTO_PAY_ENABLED:
        return web.Response(status=503, text="cryptopay disabled")
    if not CRYPTO_PAY_WEBHOOK_SECRET:
        return web.Response(status=503, text="webhook secret missing")
    if request.match_info.get("secret") != CRYPTO_PAY_WEBHOOK_SECRET:
        return web.Response(status=404, text="not found")
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
        app.router.add_post("/crypto/webhook/{secret}", crypto_webhook)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        _health_runner = runner
        logger.info("HTTP server started on port %s", port)
        if CRYPTO_PAY_ENABLED:
            logger.info(
                "Crypto Pay webhook path configured: /crypto/webhook/<secret>"
            )
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
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    await start_health_server(bot)
    recovery_task = asyncio.create_task(payment_recovery_loop(bot))

    try:
        me = await bot.me()
        logger.info("Bot started: @%s id=%s", me.username, me.id)
        logger.info("FIX_MARKER_CRYPTOPAY_STABLE=v26 loaded")
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
        await asyncio.gather(recovery_task, return_exceptions=True)
        await close_crypto_client()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
