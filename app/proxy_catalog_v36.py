from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal
from typing import Any

from app.config import PROXYLINE_MTPROXY_API_TYPE

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import (
    PROXYLINE_API_KEY,
    PROXYLINE_COUNTRIES_JSON,
    PROXYLINE_ENABLED,
)
from app.proxyline import ProxylineService
from app.country_ru import COUNTRY_RU_NAMES, country_display, country_matches, country_ru_name

logger = logging.getLogger(__name__)

PROXY_PERIODS = {
    1: 30,
    3: 90,
    6: 180,
    9: 270,
    12: 360,
}

# Используется только если API временно не вернул справочник стран.
FALLBACK_COUNTRIES = COUNTRY_RU_NAMES

_cache: tuple[float, list[tuple[str, str]]] | None = None
_cache_lock = asyncio.Lock()


def _normalize_country_rows(payload: Any) -> list[tuple[str, str]]:
    if isinstance(payload, dict):
        for key in ("countries", "items", "data", "result"):
            if key in payload:
                return _normalize_country_rows(payload[key])
        result = []
        for code, value in payload.items():
            code = str(code).strip().lower()
            if len(code) != 2:
                continue
            if isinstance(value, dict):
                name = value.get("name") or value.get("title") or value.get("country")
            else:
                name = value
            result.append((code, country_ru_name(code, str(name or code.upper()))))
        return result

    if isinstance(payload, list):
        result = []
        for item in payload:
            if isinstance(item, str):
                code = item.strip().lower()
                if len(code) == 2:
                    result.append((code, country_ru_name(code)))
            elif isinstance(item, dict):
                code = str(
                    item.get("code")
                    or item.get("country_code")
                    or item.get("iso")
                    or item.get("id")
                    or ""
                ).strip().lower()
                if len(code) != 2:
                    continue
                name = (
                    item.get("name")
                    or item.get("title")
                    or item.get("country")
                    or FALLBACK_COUNTRIES.get(code)
                    or code.upper()
                )
                result.append((code, country_ru_name(code, str(name))))
        return result
    return []


def _configured_countries() -> list[tuple[str, str]]:
    if not PROXYLINE_COUNTRIES_JSON:
        return []
    try:
        return _normalize_country_rows(json.loads(PROXYLINE_COUNTRIES_JSON))
    except Exception:
        logger.exception("Invalid PROXYLINE_COUNTRIES_JSON")
        return []


async def available_proxyline_countries(force: bool = False) -> list[tuple[str, str]]:
    global _cache
    now = time.monotonic()
    if not force and _cache and now - _cache[0] < 600:
        return _cache[1]

    async with _cache_lock:
        if not force and _cache and now - _cache[0] < 600:
            return _cache[1]

        rows: list[tuple[str, str]] = []
        if PROXYLINE_ENABLED and PROXYLINE_API_KEY:
            service = ProxylineService(PROXYLINE_API_KEY)
            for endpoint in ("countries", "countries-list", "country-list"):
                try:
                    payload = await service.request("GET", endpoint, timeout=30)
                    rows = _normalize_country_rows(payload)
                    if rows:
                        break
                except Exception:
                    logger.info("Proxyline country endpoint unavailable: %s", endpoint)

        if not rows:
            rows = _configured_countries()
        if not rows:
            rows = list(FALLBACK_COUNTRIES.items())

        unique = {code: country_ru_name(code, name) for code, name in rows if len(code) == 2}
        rows = sorted(unique.items(), key=lambda item: item[1].lower())
        _cache = (time.monotonic(), rows)
        return rows


def countries_keyboard(
    category_key: str,
    countries: list[tuple[str, str]],
    page: int = 0,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    pages = max(1, (len(countries) + page_size - 1) // page_size)
    page = max(0, min(page, pages - 1))
    start = page * page_size
    rows = countries[start:start + page_size]

    kb = InlineKeyboardBuilder()
    for code, name in rows:
        kb.button(
            text=country_display(code, name),
            callback_data=f"buyer:pxcountry:{category_key}:{code}:{page}",
        )
    kb.adjust(2)

    kb.button(
        text="🔎 Поиск страны",
        callback_data=f"buyer:pxsearch:{category_key}",
    )

    kb.button(
        text="⬅️ Назад",
        callback_data=f"buyer:pxcountries:{category_key}:{max(page - 1, 0)}",
    )
    kb.button(text=f"{page + 1}/{pages}", callback_data="buyer:noop")
    kb.button(
        text="Вперёд ➡️",
        callback_data=f"buyer:pxcountries:{category_key}:{min(page + 1, pages - 1)}",
    )
    kb.button(
        text="↩️ К категориям",
        callback_data="buyer:proxy_catalog",
    )
    kb.adjust(2, 2, 2, 2, 2, 1, 3, 1)
    return kb.as_markup()


def filter_countries(countries: list[tuple[str, str]], query: str) -> list[tuple[str, str]]:
    query = (query or "").strip()
    if not query:
        return countries
    result = [(code, name) for code, name in countries if country_matches(code, name, query)]
    return sorted(result, key=lambda item: item[1].lower())


def periods_keyboard(
    category_key: str,
    country_code: str,
    product_id: int,
    monthly_price: Decimal,
    currency: str,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for months in PROXY_PERIODS:
        amount = (monthly_price * Decimal(months)).quantize(Decimal("0.01"))
        kb.button(
            text=f"{months} мес. — {amount} {currency}",
            callback_data=(
                f"buyer:pxperiod:{category_key}:{country_code}:"
                f"{months}:{product_id}"
            ),
        )
    kb.button(
        text="⬅️ К странам",
        callback_data=f"buyer:pxcountries:{category_key}:0",
        style="danger",
    )
    kb.adjust(1)
    return kb.as_markup()


def build_provider_key(
    original_provider_key: str | None,
    country_code: str,
    months: int,
    category_key: str | None = None,
) -> str:
    data: dict[str, Any] = {}
    if original_provider_key:
        try:
            parsed = json.loads(original_provider_key)
            if isinstance(parsed, dict):
                data.update(parsed)
        except Exception:
            pass

    category = str(category_key or data.get("category") or data.get("proxy_kind") or "").lower()
    proxy_type = str(data.get("type", data.get("proxy_type", "dedicated"))).lower()
    if category == "mtproxy" and proxy_type not in {"dedicated", "shared"}:
        proxy_type = PROXYLINE_MTPROXY_API_TYPE or "dedicated"

    data.update(
        {
            "country": country_code.lower(),
            "period": PROXY_PERIODS[months],
            "months": months,
            "count": max(1, int(data.get("count", 1))),
            "ip_version": int(data.get("ip_version", 4)),
            "type": proxy_type,
        }
    )
    if category_key:
        data["category"] = str(category_key).lower()
        data["proxy_kind"] = str(category_key).lower()
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
