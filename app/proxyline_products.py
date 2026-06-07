import json
import re
from dataclasses import dataclass
from typing import Any

from app.config import (
    PROXYLINE_DEFAULT_COUNTRY,
    PROXYLINE_DEFAULT_PERIOD,
    PROXYLINE_DEFAULT_COUNT,
    PROXYLINE_DEFAULT_IP_VERSION,
    PROXYLINE_DEFAULT_TYPE,
    PROXYLINE_PRODUCTS_JSON,
)


@dataclass(frozen=True)
class ProxylineProduct:
    country: str
    period: int
    count: int = 1
    ip_version: int = 4
    proxy_type: str = "dedicated"
    coupon: str | None = None


COUNTRY_ALIASES = {
    "ru": "ru",
    "rus": "ru",
    "russia": "ru",
    "россия": "ru",
    "рф": "ru",
    "us": "us",
    "usa": "us",
    "сша": "us",
    "america": "us",
    "de": "de",
    "germany": "de",
    "германия": "de",
    "nl": "nl",
    "netherlands": "nl",
    "нидерланды": "nl",
    "gb": "gb",
    "uk": "gb",
    "england": "gb",
    "britain": "gb",
    "великобритания": "gb",
    "ca": "ca",
    "canada": "ca",
    "канада": "ca",
    "fr": "fr",
    "france": "fr",
    "франция": "fr",
    "es": "es",
    "spain": "es",
    "испания": "es",
    "it": "it",
    "italy": "it",
    "италия": "it",
    "pl": "pl",
    "poland": "pl",
    "польша": "pl",
    "ua": "ua",
    "ukraine": "ua",
    "украина": "ua",
    "kz": "kz",
    "kazakhstan": "kz",
    "казахстан": "kz",
}


def _load_exact_products() -> dict[str, dict[str, Any]]:
    if not PROXYLINE_PRODUCTS_JSON:
        return {}
    try:
        data = json.loads(PROXYLINE_PRODUCTS_JSON)
        if isinstance(data, dict):
            return {
                str(k).strip().lower(): v
                for k, v in data.items()
                if isinstance(v, dict)
            }
    except Exception:
        return {}
    return {}


EXACT_PRODUCTS = _load_exact_products()


def is_proxyline_product(product_name: str | None) -> bool:
    if not product_name:
        return False
    name = product_name.strip().lower()
    if name in EXACT_PRODUCTS:
        return True
    return any(word in name for word in ("proxyline", "proxy", "прокси"))


def resolve_proxyline_product(product_name: str | None) -> ProxylineProduct | None:
    if not is_proxyline_product(product_name):
        return None

    name = (product_name or "").strip().lower()
    exact = EXACT_PRODUCTS.get(name)
    if exact:
        return ProxylineProduct(
            country=str(exact.get("country", PROXYLINE_DEFAULT_COUNTRY)).lower(),
            period=int(exact.get("period", PROXYLINE_DEFAULT_PERIOD)),
            count=int(
                exact.get("count", exact.get("quantity", PROXYLINE_DEFAULT_COUNT))
            ),
            ip_version=int(exact.get("ip_version", PROXYLINE_DEFAULT_IP_VERSION)),
            proxy_type=str(
                exact.get("type", exact.get("proxy_type", PROXYLINE_DEFAULT_TYPE))
            ).lower(),
            coupon=exact.get("coupon"),
        )

    country = PROXYLINE_DEFAULT_COUNTRY
    for alias, code in COUNTRY_ALIASES.items():
        if re.search(
            rf"(^|[^a-zа-я0-9]){re.escape(alias)}([^a-zа-я0-9]|$)", name, flags=re.I
        ):
            country = code
            break

    period = PROXYLINE_DEFAULT_PERIOD
    m = re.search(
        r"(5|10|20|30|60|90|120|150|180|210|240|270|300|330|360)\s*(дн|day|days|дней|сут|месяц)?",
        name,
    )
    if m:
        period = int(m.group(1))

    count = PROXYLINE_DEFAULT_COUNT
    m = re.search(r"(?:x|х|кол-?во|count|quantity)\s*(\d{1,3})", name)
    if m:
        count = max(1, int(m.group(1)))

    ip_version = 6 if "ipv6" in name or "ip6" in name else PROXYLINE_DEFAULT_IP_VERSION
    proxy_type = (
        "shared" if "shared" in name or "общ" in name else PROXYLINE_DEFAULT_TYPE
    )

    return ProxylineProduct(
        country=country,
        period=period,
        count=count,
        ip_version=ip_version,
        proxy_type=proxy_type,
    )
