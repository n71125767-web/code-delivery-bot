from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_text, set_text

# V39: базовая цена хранится в товаре, покупателю показывается цена с наценкой.
# Значение можно переопределить через Render env PROXY_MARKUP_MULTIPLIER или командой /proxy_markup.
DEFAULT_PROXY_MARKUP_MULTIPLIER = os.getenv("PROXY_MARKUP_MULTIPLIER", "1.77").strip() or "1.77"
PROXY_MARKUP_TEXT_KEY = "proxy_markup_multiplier"


def _to_decimal(value: object, fallback: str = "1.77") -> Decimal:
    try:
        result = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError, AttributeError):
        result = Decimal(fallback)
    if result <= 0:
        result = Decimal(fallback)
    return result


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def get_proxy_markup_multiplier(session: AsyncSession) -> Decimal:
    raw = await get_text(session, PROXY_MARKUP_TEXT_KEY, DEFAULT_PROXY_MARKUP_MULTIPLIER)
    return _to_decimal(raw, DEFAULT_PROXY_MARKUP_MULTIPLIER)


async def set_proxy_markup_multiplier(session: AsyncSession, value: object) -> Decimal:
    multiplier = _to_decimal(value, DEFAULT_PROXY_MARKUP_MULTIPLIER)
    if multiplier < Decimal("1"):
        raise ValueError("Наценка должна быть не меньше 1.00")
    if multiplier > Decimal("20"):
        raise ValueError("Слишком большая наценка. Максимум 20.00")
    await set_text(session, PROXY_MARKUP_TEXT_KEY, str(multiplier.normalize()))
    return multiplier


def apply_proxy_markup(base_price: object, multiplier: Decimal) -> Decimal:
    base = _to_decimal(base_price, "0")
    return money(base * multiplier)


def multiplier_label(multiplier: Decimal) -> str:
    value = multiplier.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"×{value}"
