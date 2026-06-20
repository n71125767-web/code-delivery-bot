import asyncio
import logging
import os
import hashlib

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import (
    BOT_TOKEN,
    CRYPTO_PAY_ENABLED,
    CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS,
    WALLET_PAYMENT_ENABLED,
)
from app.cryptopay_service import (
    close_crypto_client,
    process_webhook,
    recover_pending_payments,
)
from app.wallet_service import process_wallet_webhook
from app.proxy_balance_v61 import proxy_balance_monitor_loop
from sqlalchemy import text
from app.database import SessionLocal, init_db, engine
from app.handlers_main import (
    on_message,
    on_callback_query,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_health_runner = None
_health_start_lock = asyncio.Lock()
_web_bot: Bot | None = None

_single_instance_conn = None


async def acquire_single_instance_lock() -> bool:
    """Prevent two Render/local processes from polling the same Telegram bot.

    Telegram allows only one long-polling getUpdates consumer per BOT_TOKEN.
    On PostgreSQL deployments this uses an advisory lock bound to the DB session.
    If a second service starts with the same DATABASE_URL, it keeps HTTP health
    alive but does not call start_polling, so logs stay clean.
    """
    global _single_instance_conn
    if os.getenv("BOT_SINGLE_INSTANCE_LOCK", "1").strip().lower() in {"0", "false", "no"}:
        return True
    try:
        if engine.dialect.name != "postgresql":
            return True
        # Stable signed 32-bit lock id, unique enough for this project/token.
        key = int(hashlib.sha256((BOT_TOKEN or "mcs-bot").encode()).hexdigest()[:8], 16) % 2147483647
        conn = await engine.connect()
        got = await conn.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        if not got:
            await conn.close()
            logger.error("Another bot instance already owns the polling lock. This process will not call getUpdates.")
            return False
        _single_instance_conn = conn
        logger.info("Single-instance polling lock acquired: %s", key)
        return True
    except Exception:
        logger.exception("Could not acquire single-instance lock; continuing to avoid false downtime")
        return True


async def release_single_instance_lock() -> None:
    global _single_instance_conn
    if _single_instance_conn is not None:
        try:
            await _single_instance_conn.close()
        finally:
            _single_instance_conn = None



async def health(_request):
    db_ok = False
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            await session.execute(text("SELECT id FROM shop_products LIMIT 1"))
            await session.execute(text("SELECT id FROM digital_purchases LIMIT 1"))
        db_ok = True
    except Exception:
        logger.exception("HEALTH_DB_FAILED")
    status = 200 if db_ok else 503
    return web.json_response(
        {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "cryptopay_enabled": CRYPTO_PAY_ENABLED,
            "wallet_payment_enabled": WALLET_PAYMENT_ENABLED,
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




async def wallet_webhook(request: web.Request):
    if not WALLET_PAYMENT_ENABLED:
        return web.Response(status=503, text="wallet disabled")
    if _web_bot is None:
        return web.Response(status=503, text="bot unavailable")

    raw_body = await request.read()
    signature = request.headers.get("x-wallet-signature")
    status, text = await process_wallet_webhook(_web_bot, raw_body, signature)
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
        app.router.add_post("/wallet/webhook", wallet_webhook)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        _health_runner = runner
        logger.info("HTTP server started on port %s", port)
        if CRYPTO_PAY_ENABLED:
            logger.info("Crypto Pay webhook path configured: /crypto/webhook")
        if WALLET_PAYMENT_ENABLED:
            logger.info("Wallet webhook path configured: /wallet/webhook")
        return runner


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.register(on_message)
    dp.callback_query.register(on_callback_query)
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
    logger.info("Database initialization completed")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    await start_health_server(bot)
    recovery_task = asyncio.create_task(payment_recovery_loop(bot))
    proxy_balance_task = asyncio.create_task(proxy_balance_monitor_loop(bot))

    try:
        me = await bot.me()
        logger.info("Bot started: @%s id=%s", me.username, me.id)
        if not await acquire_single_instance_lock():
            while True:
                await asyncio.sleep(3600)
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            logger.info("No webhook to delete or webhook deletion failed", exc_info=True)
        logger.info("FIX_MARKER_CRYPTOPAY_STABLE=v26 loaded")
        logger.info("FIX_MARKER_MCS_HARDENED=v31 loaded")
        logger.info("FIX_MARKER_MCS_CLEAN=v33 loaded")
        logger.info("FIX_MARKER_MCS_SERVER=v35 loaded")
        logger.info("FIX_MARKER_MCS_PROXYLINE=v36 loaded")
        logger.info("FIX_MARKER_MCS_EXTENDED_MARKETPLACE_V37 loaded")
        logger.info("FIX_MARKER_MCS_ALERT_IDS=v36.1 loaded")
        dp = build_dispatcher()
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "callback_query",
            ],
        )
    finally:
        recovery_task.cancel()
        proxy_balance_task.cancel()
        await asyncio.gather(recovery_task, proxy_balance_task, return_exceptions=True)
        await close_crypto_client()
        await release_single_instance_lock()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
