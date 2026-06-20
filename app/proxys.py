from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.config import (
    PROXYS_API_BASE_URL,
    PROXYS_IO_BASE_URL,
    PROXYS_IO_PROXY_POOL_ID,
    PROXYS_IO_SERVICE_ID,
    PROXYS_IO_USE_NEW_USER,
    PROXYS_PROVIDER_MODE,
)
from app.proxyline import ProxylineError, ProxylineService
from app.proxyline_products import ProxylineProduct

logger = logging.getLogger(__name__)


class ProxysError(ProxylineError):
    pass


class ProxysService:
    """Second proxy provider adapter.

    Supported modes:
    1. PROXYS_PROVIDER_MODE=proxys_io
       Native PROXYS.IO v2 API. Only the common API key is required by default.
       Used for standard/default proxies.

    2. PROXYS_PROVIDER_MODE=proxyline_adapter
       Legacy mode for your own adapter that exposes Proxyline-compatible
       /ips-count/ and /new-order/ endpoints.
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ProxysError("PROXYS_API_KEY is empty")
        self.api_key = api_key
        self.mode = (PROXYS_PROVIDER_MODE or "proxys_io").lower()
        if self.mode == "proxyline_adapter":
            if not PROXYS_API_BASE_URL:
                raise ProxysError(
                    "PROXYS_API_BASE_URL is empty. Set it or use PROXYS_PROVIDER_MODE=proxys_io."
                )
            self._adapter = _ProxylineCompatibleProxysService(api_key)
        else:
            self._adapter = None
            self.base_url = (PROXYS_IO_BASE_URL or "https://proxys.io/ru/api/v2").rstrip("/")

    async def balance(self) -> Any:
        if self._adapter is not None:
            return await self._adapter.balance()
        return await self._request("GET", "balance", params={"key": self.api_key}, timeout=30)

    async def ips_count(self, product: ProxylineProduct) -> int:
        if self._adapter is not None:
            return await self._adapter.ips_count(product)
        params = {
            "key": self.api_key,
            "service": PROXYS_IO_SERVICE_ID,
            "count": max(1, int(product.count)),
            "country": str(product.country or "ru").upper(),
            "server": PROXYS_IO_PROXY_POOL_ID or "S1",
        }
        data = await self._request(
            "GET", "overs/check-available-proxies-count", params=params, timeout=30
        )
        if isinstance(data, dict) and data.get("success") is True:
            return max(1, int(product.count))
        if isinstance(data, dict):
            value = _first(data, "count", "available", "available_count", "quantity")
            if value is not None:
                return int(value)
        logger.warning("Unexpected PROXYS.IO available-count response: %s", data)
        return 0

    async def buy_proxy(self, product: ProxylineProduct) -> Any:
        if self._adapter is not None:
            return await self._adapter.buy_proxy(product)
        body = {
            "key": self.api_key,
            "service": PROXYS_IO_SERVICE_ID,
            "count": max(1, int(product.count)),
            "country": str(product.country or "ru").upper(),
            "period": int(product.period or 30),
        }
        if PROXYS_IO_PROXY_POOL_ID:
            body["proxy_pool_id"] = PROXYS_IO_PROXY_POOL_ID
        if PROXYS_IO_USE_NEW_USER:
            body["use_new_user"] = True

        order = await self._request("POST", "buy", json=body, timeout=90)
        order_key = _extract_order_key(order)
        if not order_key:
            # Some installations return the proxy list directly from /buy.
            return order

        # PROXYS.IO /buy returns an order key; /ip with that key returns concrete
        # IP/port/login/password data. Return both raw responses for the existing
        # formatter, plus a normalized list of proxy records.
        ip_data = await self._request("GET", "ip", params={"key": order_key}, timeout=60)
        return _normalize_proxys_io_payload(order, ip_data)

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        url = f"{self.base_url}/{endpoint.strip('/')}"
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.request(method, url, params=params, json=json) as response:
                raw = await response.text()
                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    payload = raw
                if response.status >= 400:
                    raise ProxysError(f"PROXYS.IO {endpoint} HTTP {response.status}: {payload}")
                if isinstance(payload, dict) and payload.get("success") is False:
                    raise ProxysError(f"PROXYS.IO {endpoint} error: {payload.get('error') or payload}")
                return payload


class _ProxylineCompatibleProxysService(ProxylineService):
    def __init__(self, api_key: str):
        if not PROXYS_API_BASE_URL:
            raise ProxysError("PROXYS_API_BASE_URL is empty")
        self.BASE_URL = PROXYS_API_BASE_URL.rstrip("/")
        super().__init__(api_key)


def _first(obj: dict[str, Any], *keys: str) -> Any:
    lower = {str(k).lower(): v for k, v in obj.items()}
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
        value = lower.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _extract_order_key(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data", payload)
    if isinstance(data, dict):
        value = _first(data, "key", "order_key", "api_key")
        if value:
            return str(value)
    return None


def _normalize_proxys_io_payload(order_payload: Any, ip_payload: Any) -> dict[str, Any]:
    data = ip_payload.get("data") if isinstance(ip_payload, dict) else ip_payload
    if isinstance(data, list):
        # User-wide key may return a list of orders. Prefer the newest/last order.
        data = data[-1] if data else {}
    if not isinstance(data, dict):
        return {"provider": "proxys_io", "order": order_payload, "ip": ip_payload}

    username = _first(data, "username", "login", "user")
    password = _first(data, "password", "pass", "passwd")
    items = data.get("list_ip") or data.get("proxies") or data.get("items") or []
    normalized: list[dict[str, Any]] = []
    if isinstance(items, dict):
        items = [items]
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            host = _first(item, "ip", "host", "server", "address")
            http_port = _first(item, "port_http", "http_port", "port_https", "https_port", "http", "https")
            socks_port = _first(item, "port_socks", "socks_port", "port_socks5", "socks5_port", "socks", "socks5")
            normalized.append(
                {
                    "ip": host,
                    "host": host,
                    "username": username,
                    "login": username,
                    "password": password,
                    "pass": password,
                    "http_port": http_port,
                    "port_http": http_port,
                    "https_port": http_port,
                    "socks5_port": socks_port,
                    "port_socks5": socks_port,
                    "socks_port": socks_port,
                }
            )
    return {
        "provider": "proxys_io",
        "order": order_payload,
        "raw": ip_payload,
        "username": username,
        "password": password,
        "proxies": normalized,
        "items": normalized,
    }
