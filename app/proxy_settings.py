from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_text, set_text

SUPPORTED_COUNTRIES = {
    "ru": "🇷🇺 Россия",
    "us": "🇺🇸 США",
    "de": "🇩🇪 Германия",
    "nl": "🇳🇱 Нидерланды",
    "gb": "🇬🇧 Великобритания",
    "fr": "🇫🇷 Франция",
    "ca": "🇨🇦 Канада",
    "pl": "🇵🇱 Польша",
    "kz": "🇰🇿 Казахстан",
}
SUPPORTED_PERIODS = [5, 10, 20, 30, 60, 90, 180, 360]
SUPPORTED_TYPES = ["dedicated", "shared"]


@dataclass
class ProxyShopSettings:
    enabled: bool
    countries: list[str]
    periods: list[int]
    proxy_type: str
    count: int
    ip_version: int


def _split_codes(raw: str) -> list[str]:
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _split_ints(raw: str) -> list[int]:
    result: list[int] = []
    for item in raw.split(","):
        try:
            value = int(item.strip())
        except ValueError:
            continue
        if value > 0 and value not in result:
            result.append(value)
    return result


async def get_proxy_shop_settings(session: AsyncSession) -> ProxyShopSettings:
    enabled = (await get_text(session, "proxy_shop_enabled", "1")).strip() == "1"
    countries = _split_codes(await get_text(session, "proxy_shop_countries", "ru,us,de"))
    countries = [x for x in countries if x in SUPPORTED_COUNTRIES] or ["ru"]
    periods = _split_ints(await get_text(session, "proxy_shop_periods", "30,90,180"))
    periods = [x for x in periods if x in SUPPORTED_PERIODS] or [30]
    proxy_type = (await get_text(session, "proxy_shop_type", "dedicated")).strip().lower()
    if proxy_type not in SUPPORTED_TYPES:
        proxy_type = "dedicated"
    try:
        count = max(1, min(100, int(await get_text(session, "proxy_shop_count", "1"))))
    except ValueError:
        count = 1
    try:
        ip_version = int(await get_text(session, "proxy_shop_ip_version", "4"))
    except ValueError:
        ip_version = 4
    if ip_version not in (4, 6):
        ip_version = 4
    return ProxyShopSettings(enabled, countries, periods, proxy_type, count, ip_version)


async def save_proxy_setting(session: AsyncSession, key: str, value: str) -> None:
    await set_text(session, key, value)


def country_label(code: str) -> str:
    return SUPPORTED_COUNTRIES.get(code, code.upper())


def selection_dump(country: str | None = None, period: int | None = None) -> str:
    parts = ["proxy"]
    if country:
        parts.append(f"country={country}")
    if period:
        parts.append(f"period={period}")
    return ";".join(parts)


def selection_load(value: str | None) -> tuple[str | None, int | None]:
    country: str | None = None
    period: int | None = None
    for part in (value or "").split(";"):
        if part.startswith("country="):
            country = part.split("=", 1)[1].strip().lower()
        elif part.startswith("period="):
            try:
                period = int(part.split("=", 1)[1])
            except ValueError:
                period = None
    return country, period
