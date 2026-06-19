# PATCH V45 — MTProxy delivery format

## Что добавлено

- Для категории `mtproxy` включён отдельный формат выдачи:
  - IP
  - порт
  - секретный ключ
  - ссылка подключения `tg://proxy?server=...&port=...&secret=...`
- Обычные прокси по-прежнему выдаются отдельными блоками SOCKS5 и HTTP.
- Форматтер понимает разные ответы провайдера:
  - `server/ip/host + port + secret`
  - `secret_key`, `mt_secret`, `mtproxy_secret`, `telegram_secret`
  - готовые `tg://proxy?...` и `https://t.me/proxy?...` ссылки
  - строки вида `ip:port:secret`
- `/proxy_autofix` теперь помечает MTProxy-товар как `category=mtproxy` и `proxy_kind=mtproxy`.
- Добавлена env-переменная `PROXYLINE_MTPROXY_TYPE`.

## Настройка

По умолчанию:

```env
PROXYLINE_MTPROXY_TYPE=mtproxy
```

Если ваш Proxyline/API-адаптер использует другое значение типа товара для MTProxy, поменяйте переменную на Render, например:

```env
PROXYLINE_MTPROXY_TYPE=mtproto
```

После деплоя выполните от админа:

```text
/proxy_autofix 100 RUB
/proxy_markup 1.77
```

Это обновит provider_key у MTProxy-товара.
