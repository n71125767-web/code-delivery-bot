import logging
import re
from typing import Any
from urllib.parse import quote, unquote, urlparse, parse_qs

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


_HOST_KEYS = (
    "host",
    "ip",
    "server",
    "address",
    "addr",
    "proxy_host",
    "proxy_ip",
    "hostname",
)
_LOGIN_KEYS = ("login", "username", "user", "proxy_login", "proxy_user")
_PASSWORD_KEYS = ("password", "pass", "passwd", "proxy_password", "proxy_pass")
_COMMON_PORT_KEYS = ("port", "proxy_port", "common_port")
_HTTP_PORT_KEYS = (
    "http_port",
    "port_http",
    "https_port",
    "port_https",
    "proxy_http_port",
    "http",
    "https",
)
_SOCKS_PORT_KEYS = (
    "socks5_port",
    "port_socks5",
    "socks_port",
    "port_socks",
    "proxy_socks5_port",
    "socks5",
    "socks",
)
_MTPROXY_PORT_KEYS = (
    "mtproxy_port",
    "mtproto_port",
    "telegram_port",
    "proxy_port",
    "port",
    "common_port",
)
_MTPROXY_SECRET_KEYS = (
    "secret",
    "secret_key",
    "key",
    "mt_secret",
    "mtproxy_secret",
    "mtproto_secret",
    "telegram_secret",
    "proxy_secret",
    "tg_secret",
)
_MTPROXY_LINK_KEYS = (
    "link",
    "url",
    "tg_link",
    "telegram_link",
    "connect_link",
    "connection_link",
    "connection_url",
)
_CONTAINER_KEYS = (
    "proxies",
    "proxy",
    "items",
    "data",
    "result",
    "results",
    "order",
    "orders",
    "list",
)
_STRING_KEYS = (
    "proxy",
    "line",
    "text",
    "http",
    "https",
    "socks5",
    "socks",
)


def _get_first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lower_map = {str(k).lower(): v for k, v in mapping.items()}
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
        value = lower_map.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _as_port(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        # Some providers return {"port": 1234} or {"value": 1234}.
        value = _get_first(value, ("port", "value", "number"))
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"\d{2,6}", text)
    return match.group(0) if match else text


def _parse_proxy_string(value: str) -> dict[str, str | None] | None:
    raw = value.strip()
    if not raw:
        return None

    # URI formats: socks5://login:pass@1.2.3.4:1080 or http://login:pass@1.2.3.4:8080
    if "://" in raw:
        try:
            parsed = urlparse(raw)
            if parsed.hostname:
                protocol = (parsed.scheme or "").lower()
                item = {
                    "host": parsed.hostname,
                    "login": unquote(parsed.username or "") or None,
                    "password": unquote(parsed.password or "") or None,
                    "http_port": None,
                    "socks5_port": None,
                    "port": str(parsed.port) if parsed.port else None,
                }
                if protocol.startswith("socks"):
                    item["socks5_port"] = item["port"]
                elif protocol.startswith("http"):
                    item["http_port"] = item["port"]
                return item
        except Exception:
            pass

    # login:password@ip:port
    match = re.match(r"(?P<login>[^:@\s]+):(?P<password>[^@\s]+)@(?P<host>[^:\s]+):(?P<port>\d{2,6})$", raw)
    if match:
        d = match.groupdict()
        d["http_port"] = d.get("port")
        d["socks5_port"] = d.get("port")
        return d

    # ip:port:login:password or ip:port@login:password are common export formats.
    separators = ":" if raw.count(":") >= 3 else None
    if separators:
        parts = raw.split(":")
        if len(parts) >= 4:
            host = parts[0].strip()
            port = parts[1].strip()
            login = parts[2].strip()
            password = ":".join(parts[3:]).strip()
            if host and port:
                return {
                    "host": host,
                    "port": port,
                    "http_port": port,
                    "socks5_port": port,
                    "login": login or None,
                    "password": password or None,
                }

    # ip:port only.
    match = re.match(r"(?P<host>[^:\s]+):(?P<port>\d{2,6})$", raw)
    if match:
        d = match.groupdict()
        d["http_port"] = d.get("port")
        d["socks5_port"] = d.get("port")
        d["login"] = None
        d["password"] = None
        return d

    return None


def _extract_proxy_items(payload: Any) -> list[Any]:
    """Extract possible proxy rows from nested provider responses."""
    if payload is None:
        return []
    if isinstance(payload, list):
        result: list[Any] = []
        for value in payload:
            result.extend(_extract_proxy_items(value))
        return result
    if isinstance(payload, str):
        # Providers sometimes return several proxy lines separated by newlines.
        lines = [line.strip() for line in payload.replace(";", "\n").splitlines() if line.strip()]
        return lines or [payload]
    if isinstance(payload, dict):
        found: list[Any] = []
        for key in _CONTAINER_KEYS:
            value = payload.get(key)
            if value not in (None, ""):
                extracted = _extract_proxy_items(value)
                if extracted:
                    found.extend(extracted)
        if found:
            return found
        # A single proxy can be represented as a dict.
        return [payload]
    return [payload]


def _normalize_proxy_item(item: Any) -> dict[str, str | None] | None:
    if isinstance(item, str):
        return _parse_proxy_string(item)
    if not isinstance(item, dict):
        return None

    # Some fields can contain a ready-made proxy string.
    for key in _STRING_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parsed = _parse_proxy_string(value)
            if parsed:
                # Preserve more specific ports from the surrounding dict if present.
                parsed["http_port"] = _as_port(_get_first(item, _HTTP_PORT_KEYS)) or parsed.get("http_port")
                parsed["socks5_port"] = _as_port(_get_first(item, _SOCKS_PORT_KEYS)) or parsed.get("socks5_port")
                parsed["login"] = str(_get_first(item, _LOGIN_KEYS) or parsed.get("login") or "") or None
                parsed["password"] = str(_get_first(item, _PASSWORD_KEYS) or parsed.get("password") or "") or None
                return parsed

    host = _get_first(item, _HOST_KEYS)
    login = _get_first(item, _LOGIN_KEYS)
    password = _get_first(item, _PASSWORD_KEYS)
    common_port = _as_port(_get_first(item, _COMMON_PORT_KEYS))
    http_port = _as_port(_get_first(item, _HTTP_PORT_KEYS))
    socks5_port = _as_port(_get_first(item, _SOCKS_PORT_KEYS))

    # Do not treat a full proxy string in http/socks5 as a port only.
    for key, port_name in (("http", "http_port"), ("https", "http_port"), ("socks5", "socks5_port"), ("socks", "socks5_port")):
        value = item.get(key)
        if isinstance(value, str) and ":" in value:
            parsed = _parse_proxy_string(value)
            if parsed:
                host = host or parsed.get("host")
                login = login or parsed.get("login")
                password = password or parsed.get("password")
                if port_name == "http_port":
                    http_port = http_port or parsed.get("http_port") or parsed.get("port")
                else:
                    socks5_port = socks5_port or parsed.get("socks5_port") or parsed.get("port")

    if not host:
        return None

    # If the provider returns one universal port, show it for both protocols so the buyer gets both blocks.
    http_port = http_port or common_port
    socks5_port = socks5_port or common_port

    return {
        "host": str(host).strip(),
        "http_port": str(http_port).strip() if http_port else None,
        "socks5_port": str(socks5_port).strip() if socks5_port else None,
        "login": str(login).strip() if login not in (None, "") else None,
        "password": str(password).strip() if password not in (None, "") else None,
    }


def _format_protocol_block(
    title: str,
    host: str,
    port: str | None,
    login: str | None,
    password: str | None,
    scheme: str,
) -> str:
    port_text = port or "не выдан"
    login_text = login or "без логина"
    password_text = password or "без пароля"
    url = ""
    if port:
        if login and password:
            url = f"\nСтрока: {scheme}://{login}:{password}@{host}:{port}"
        else:
            url = f"\nСтрока: {scheme}://{host}:{port}"
    return (
        f"{title}\n"
        f"IP: {host}\n"
        f"Порт: {port_text}\n"
        f"Логин: {login_text}\n"
        f"Пароль: {password_text}"
        f"{url}"
    )



def _parse_mtproxy_string(value: str) -> dict[str, str | None] | None:
    raw = value.strip()
    if not raw:
        return None

    # Telegram connection links:
    # tg://proxy?server=1.2.3.4&port=443&secret=abcdef
    # https://t.me/proxy?server=1.2.3.4&port=443&secret=abcdef
    if "proxy?" in raw and (raw.startswith("tg://") or "t.me/proxy" in raw or "telegram.me/proxy" in raw):
        try:
            parsed = urlparse(raw)
            qs = parse_qs(parsed.query)
            host = (qs.get("server") or qs.get("host") or qs.get("ip") or [None])[0]
            port = (qs.get("port") or [None])[0]
            secret = (qs.get("secret") or qs.get("key") or [None])[0]
            if host and port and secret:
                return {
                    "host": str(host).strip(),
                    "port": _as_port(port),
                    "secret": str(secret).strip(),
                    "link": raw,
                }
        except Exception:
            pass

    # Common exports: ip:port:secret or ip|port|secret.
    for sep in (":", "|", ";", ","):
        parts = [part.strip() for part in raw.split(sep)]
        if len(parts) == 3 and parts[0] and parts[1] and parts[2]:
            port = _as_port(parts[1])
            if port:
                return {"host": parts[0], "port": port, "secret": parts[2], "link": None}

    # Multiline exports:
    # IP: 1.2.3.4\nPort: 443\nSecret: abc
    host_match = re.search(r"(?:ip|host|server|адрес)\s*[:=]\s*([^\s]+)", raw, flags=re.I)
    port_match = re.search(r"(?:port|порт)\s*[:=]\s*(\d{2,6})", raw, flags=re.I)
    secret_match = re.search(r"(?:secret|key|секрет|ключ)\s*[:=]\s*([^\s]+)", raw, flags=re.I)
    if host_match and port_match and secret_match:
        return {
            "host": host_match.group(1).strip(),
            "port": _as_port(port_match.group(1)),
            "secret": secret_match.group(1).strip(),
            "link": None,
        }

    return None


def _normalize_mtproxy_item(item: Any) -> dict[str, str | None] | None:
    if isinstance(item, str):
        return _parse_mtproxy_string(item)
    if not isinstance(item, dict):
        return None

    for key in _MTPROXY_LINK_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parsed = _parse_mtproxy_string(value)
            if parsed:
                return parsed

    # Some provider responses put a ready-made MTProxy line in generic fields.
    for key in _STRING_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parsed = _parse_mtproxy_string(value)
            if parsed:
                return parsed

    host = _get_first(item, _HOST_KEYS)
    port = _as_port(_get_first(item, _MTPROXY_PORT_KEYS))
    secret = _get_first(item, _MTPROXY_SECRET_KEYS)
    if not host or not port or not secret:
        return None
    return {
        "host": str(host).strip(),
        "port": str(port).strip(),
        "secret": str(secret).strip(),
        "link": None,
    }


def _mtproxy_link(host: str, port: str, secret: str) -> str:
    return (
        "tg://proxy?"
        f"server={quote(str(host), safe='')}"
        f"&port={quote(str(port), safe='')}"
        f"&secret={quote(str(secret), safe='')}"
    )


def _format_mtproxy_block(title: str, host: str, port: str, secret: str, link: str | None = None) -> str:
    connect_link = link or _mtproxy_link(host, port, secret)
    return (
        f"{title}\n\n"
        f"IP: {host}\n"
        f"Порт: {port}\n"
        f"Секретный ключ: {secret}\n"
        f"Ссылка подключения: {connect_link}"
    )


def format_mtproxy_result(payload: Any) -> str:
    """Return buyer-facing Telegram MTProxy credentials.

    Expected buyer format: IP, port, secret key, and a ready tg:// connection link.
    The parser accepts dicts, lists, tg://proxy links, t.me/proxy links, and compact
    strings like ip:port:secret.
    """
    normalized: list[dict[str, str | None]] = []
    for item in _extract_proxy_items(payload):
        proxy = _normalize_mtproxy_item(item)
        if proxy and proxy.get("host") and proxy.get("port") and proxy.get("secret"):
            if not any(
                old.get("host") == proxy.get("host")
                and old.get("port") == proxy.get("port")
                and old.get("secret") == proxy.get("secret")
                for old in normalized
            ):
                normalized.append(proxy)

    if not normalized:
        return str(payload)

    blocks: list[str] = []
    for index, proxy in enumerate(normalized, start=1):
        title = f"🧩 MTProxy #{index}" if len(normalized) > 1 else "🧩 MTProxy"
        blocks.append(
            _format_mtproxy_block(
                title,
                str(proxy["host"]),
                str(proxy["port"]),
                str(proxy["secret"]),
                proxy.get("link"),
            )
        )
    return "\n\n━━━━━━━━━━━━\n\n".join(blocks)

def format_proxyline_result(payload: Any) -> str:
    """Return buyer-facing proxy credentials in HTTP and SOCKS5 format.

    The formatter accepts several provider response shapes: nested dicts, lists,
    ready-made strings like ip:port:login:password, and URI lines. It always tries
    to show both protocols with the fields requested by buyers: IP, port, login,
    password.
    """
    normalized: list[dict[str, str | None]] = []
    for item in _extract_proxy_items(payload):
        proxy = _normalize_proxy_item(item)
        if proxy and proxy.get("host"):
            merged = False
            for old in normalized:
                if (
                    old.get("host") == proxy.get("host")
                    and old.get("login") == proxy.get("login")
                    and old.get("password") == proxy.get("password")
                ):
                    old["http_port"] = old.get("http_port") or proxy.get("http_port")
                    old["socks5_port"] = old.get("socks5_port") or proxy.get("socks5_port")
                    merged = True
                    break
            if not merged:
                normalized.append(proxy)

    if not normalized:
        return str(payload)

    blocks: list[str] = []
    for index, proxy in enumerate(normalized, start=1):
        host = str(proxy.get("host") or "").strip()
        login = proxy.get("login")
        password = proxy.get("password")
        socks5_port = proxy.get("socks5_port")
        http_port = proxy.get("http_port")
        title = f"🌐 Прокси #{index}" if len(normalized) > 1 else "🌐 Прокси"
        blocks.append(
            title
            + "\n\n"
            + _format_protocol_block("🔌 SOCKS5", host, socks5_port, login, password, "socks5")
            + "\n\n"
            + _format_protocol_block("🌍 HTTP", host, http_port, login, password, "http")
        )
    return "\n\n━━━━━━━━━━━━\n\n".join(blocks)
