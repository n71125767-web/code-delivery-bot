from __future__ import annotations

import asyncio
from decimal import Decimal

from aiogram import Bot

from app.config import ADMIN_IDS, PROXY_BALANCE_CHECK_INTERVAL_SECONDS, PROXY_BALANCE_WARN_USD, PROXY_BALANCE_CRITICAL_USD
from app.database import SessionLocal
from app.services import get_text, set_text
from app.proxy_admin_v61 import get_provider_balance, fmt_amount

async def _send_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass

def _level(amount):
    if amount is None:
        return "unknown"
    if amount < Decimal(str(PROXY_BALANCE_CRITICAL_USD)):
        return "critical"
    if amount < Decimal(str(PROXY_BALANCE_WARN_USD)):
        return "warn"
    return "ok"

async def check_once(bot: Bot) -> None:
    for provider, title in (("proxyline", "Proxyline"), ("proxys", "Proxys")):
        amount, currency, err = await get_provider_balance(provider)
        if err or amount is None:
            continue
        level = _level(amount)
        key = f"proxy_balance_alert:{provider}"
        async with SessionLocal() as session:
            old = await get_text(session, key, "")
            if level in {"warn", "critical"} and old != level:
                icon = "🔴" if level == "critical" else "🟡"
                await _send_admins(
                    bot,
                    f"{icon} Баланс {title} низкий\n\nБаланс: {fmt_amount(amount, currency)}\nПорог предупреждения: {PROXY_BALANCE_WARN_USD}$\nКритический порог: {PROXY_BALANCE_CRITICAL_USD}$",
                )
                await set_text(session, key, level)
            elif level == "ok" and old != "ok":
                await set_text(session, key, "ok")
            await session.commit()

async def proxy_balance_monitor_loop(bot: Bot) -> None:
    while True:
        try:
            await check_once(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(max(300, int(PROXY_BALANCE_CHECK_INTERVAL_SECONDS)))
