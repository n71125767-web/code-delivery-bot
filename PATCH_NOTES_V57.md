# V57 — PROXYS.IO native API adapter

Added native `PROXYS_PROVIDER_MODE=proxys_io` mode for standard/default proxies.

## What changed

- Standard/default proxies can now use the common PROXYS.IO API key directly.
- `PROXYS_API_BASE_URL` is no longer required for `proxys_io` mode.
- Added PROXYS.IO v2 calls:
  - `GET /balance`
  - `GET /overs/check-available-proxies-count`
  - `POST /buy`
  - `GET /ip`
- Normalizes PROXYS.IO `list_ip` response into the existing delivery formatter.
- Premium and MTProxy remain on Proxyline.
- Standard/default remains on Proxys.

## Render env

```env
PROXYS_ENABLED=1
PROXYS_PROVIDER_MODE=proxys_io
PROXYS_API_KEY=your_common_proxys_io_api_key
PROXYS_IO_BASE_URL=https://proxys.io/ru/api/v2
PROXYS_IO_SERVICE_ID=1
PROXYS_IO_PROXY_POOL_ID=S1
PROXYS_IO_USE_NEW_USER=0
```

## Separate prices

Set different prices in admin UI for each proxy product, or use SQL:

```sql
UPDATE shop_products SET price = 250, currency = 'RUB', updated_at = NOW() WHERE note = 'proxy_autofix:premium';
UPDATE shop_products SET price = 120, currency = 'RUB', updated_at = NOW() WHERE note = 'proxy_autofix:standard';
UPDATE shop_products SET price = 200, currency = 'RUB', updated_at = NOW() WHERE note = 'proxy_autofix:mtproxy';
```
