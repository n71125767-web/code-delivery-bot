from __future__ import annotations

from app.config import PROXYS_API_BASE_URL
from app.proxyline import ProxylineService, ProxylineError


class ProxysError(ProxylineError):
    pass


class ProxysService(ProxylineService):
    """Configurable adapter for a second proxy provider.

    Many projects use a Proxyline-compatible proxy purchase flow. If your Proxys
    endpoint differs, set PROXYS_API_BASE_URL to your adapter URL that exposes
    compatible endpoints: /ips-count/ and /new-order/.
    """

    def __init__(self, api_key: str):
        if not PROXYS_API_BASE_URL:
            raise ProxysError(
                "PROXYS_API_BASE_URL is empty. Add a compatible adapter/base URL or use Proxyline for this tariff."
            )
        self.BASE_URL = PROXYS_API_BASE_URL.rstrip("/")
        super().__init__(api_key)
