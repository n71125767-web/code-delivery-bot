from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_text, set_text

# V39: базовая цена хранится в товаре, покупателю показывается цена с наценкой.
# Значение можно переопределить через Render env PROXY_MARKUP_MULTIPLIER или командой /proxy_markup.
DEFAULT_PROXY_MARKUP_MULTIPLIER = os.getenv("PROXY_MARKUP_MULTIPLIER", "1.77").strip() or "1.77"
PROXY_MARKUP_TEXT_KEY = "proxy_markup_multiplier"
PROXY_KIND_MARKUP_KEYS = {
    "mtproxy": "proxy_markup_multiplier_mtproxy",
    "premium": "proxy_markup_multiplier_premium",
    "standard": "proxy_markup_multiplier_standard",
    "residential": "proxy_markup_multiplier_residential",
}
PROXY_KIND_LABELS = {
    "mtproxy": "MTProxy",
    "premium": "Premium",
    "standard": "Standard",
    "residential": "Residential",
}


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


async def get_proxy_markup_multiplier_for_category(session: AsyncSession, category_key: str | None = None) -> Decimal:
    category_key = (category_key or "").strip().lower()
    key = PROXY_KIND_MARKUP_KEYS.get(category_key)
    if not key:
        return await get_proxy_markup_multiplier(session)
    fallback = str(await get_proxy_markup_multiplier(session))
    raw = await get_text(session, key, fallback)
    return _to_decimal(raw, fallback)


async def set_proxy_markup_multiplier_for_category(session: AsyncSession, category_key: str, value: object) -> Decimal:
    category_key = (category_key or "").strip().lower()
    key = PROXY_KIND_MARKUP_KEYS.get(category_key)
    if not key:
        return await set_proxy_markup_multiplier(session, value)
    multiplier = _to_decimal(value, DEFAULT_PROXY_MARKUP_MULTIPLIER)
    if multiplier < Decimal("1"):
        raise ValueError("Наценка должна быть не меньше 1.00")
    if multiplier > Decimal("20"):
        raise ValueError("Слишком большая наценка. Максимум 20.00")
    await set_text(session, key, str(multiplier.normalize()))
    return multiplier


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
