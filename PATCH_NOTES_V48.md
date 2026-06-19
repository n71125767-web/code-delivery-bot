# V48 — Proxyline API mode for Telegram/MTProxy button

## What changed

- The Telegram/MTProxy tariff now buys through Proxyline API by default again.
- Removed the forced stock-only behavior from V47 unless `PROXYLINE_MTPROXY_MODE=stock` is set.
- Existing old provider keys with `type=mtproxy` are normalized to a valid Proxyline API type before `ips-count`/`new-order`.
- Default API type for the Telegram/MTProxy button is `dedicated` because Proxyline public `new-order` supports `dedicated` / `shared`.
- If a provider adapter returns real MTProxy fields (`secret`, `secret_key`, etc.), the bot formats `IP / port / secret / tg://proxy`.
- If Proxyline returns regular HTTP/SOCKS5 proxy fields, the bot delivers HTTP/SOCKS5 format and labels it as Telegram-proxy, not a fake MTProxy secret.

## New env vars

```env
PROXYLINE_MTPROXY_MODE=api
PROXYLINE_MTPROXY_API_TYPE=dedicated
```

Use `PROXYLINE_MTPROXY_MODE=stock` only if you want manual real MTProxy stock lines again.

## After deploy

Run:

```text
/proxy_autofix 100 RUB
/proxy_markup 1.77
```

This refreshes existing DB rows so the Telegram-proxy product points to Proxyline API with a valid `type`.
