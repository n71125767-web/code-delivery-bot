import logging
from typing import Any

import aiohttp

from app.proxyline_products import ProxylineProduct

logger = logging.getLogger(__name__)


class ProxylineError(Exception):
    pass


class ProxylineService:
    BASE_URL = "https://panel.proxyline.net/api"

    def __init__(self, api_key: str):
        if not api_key:
            raise ProxylineError("PROXYLINE_API_KEY is empty")
        self.api_key = api_key

    def _url(self, method: str) -> str:
        return f"{self.BASE_URL}/{method}/"

    def _headers(self) -> dict[str, str]:
        # Proxyline разрешает передавать ключ через API-KEY header.
        # Так ключ не светится в query URL и логах веб-сервера.
        return {"API-KEY": self.api_key}

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict | None = None,
        data: Any = None,
        timeout: int = 60,
    ) -> Any:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(
            timeout=timeout_obj, headers=self._headers()
        ) as session:
            async with session.request(
                method, self._url(endpoint), params=params, data=data
            ) as response:
                raw = await response.text()
                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    payload = raw

                if response.status >= 400:
                    raise ProxylineError(
                        f"{endpoint} HTTP {response.status}: {payload}"
                    )
                return payload

    async def balance(self) -> Any:
        return await self.request("GET", "balance", timeout=30)

    async def ips_count(self, product: ProxylineProduct) -> int:
        params = {
            "type": product.proxy_type,
            "ip_version": product.ip_version,
            "country": product.country,
        }
        data = await self.request("GET", "ips-count", params=params, timeout=30)
        try:
            return int(data)
        except Exception:
            if isinstance(data, dict):
                for key in ("count", "quantity", "ips_count", "result"):
                    if key in data:
                        return int(data[key])
            logger.warning("Unexpected Proxyline ips-count response: %s", data)
            return 0

    async def buy_proxy(self, product: ProxylineProduct) -> Any:
        data = {
            "type": product.proxy_type,
            "ip_version": product.ip_version,
            "country": product.country,
            "quantity": product.count,
            "period": product.period,
        }
        if product.coupon:
            data["coupon"] = product.coupon
        return await self.request("POST", "new-order", data=data, timeout=90)


def _first_proxy_item(payload: Any) -> Any:
    if isinstance(payload, list):
        return payload[0] if payload else None
    if not isinstance(payload, dict):
        return payload

    for key in ("proxies", "proxy", "items", "data", "result"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return value[0]
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return value
    return payload


def format_proxyline_result(payload: Any) -> str:
    item = _first_proxy_item(payload)

    if isinstance(item, str):
        return item.strip()

    if isinstance(item, dict):
        host = (
            item.get("host")
            or item.get("ip")
            or item.get("server")
            or item.get("address")
        )
        port = item.get("port")
        login = item.get("login") or item.get("username") or item.get("user")
        password = item.get("password") or item.get("pass")

        # Иногда API возвращает уже готовую строку.
        for key in ("proxy", "line", "text", "http", "socks5"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        if host and port and login and password:
            return (
                f"IP: {host}\n"
                f"PORT: {port}\n"
                f"LOGIN: {login}\n"
                f"PASSWORD: {password}"
            )
        if host and port:
            return f"IP: {host}\nPORT: {port}"

    return str(payload)
