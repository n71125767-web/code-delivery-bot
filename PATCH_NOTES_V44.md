# V44 — формат выдачи прокси HTTP + SOCKS5

Исправлена выдача прокси после покупки.

## Что изменено

- `format_proxyline_result()` теперь не отдаёт сырой JSON/строку от провайдера.
- Покупатель получает понятный формат:

```text
🌐 Прокси

🔌 SOCKS5
IP: 1.2.3.4
Порт: 1080
Логин: user
Пароль: pass
Строка: socks5://user:pass@1.2.3.4:1080

🌍 HTTP
IP: 1.2.3.4
Порт: 8080
Логин: user
Пароль: pass
Строка: http://user:pass@1.2.3.4:8080
```

- Добавлена нормализация разных ответов Proxyline/Proxys:
  - `ip`, `host`, `server`, `address`;
  - `port`, `port_http`, `http_port`, `port_socks5`, `socks5_port`;
  - `login`, `username`, `user`;
  - `password`, `pass`, `passwd`;
  - строки вида `ip:port:login:password`;
  - строки вида `socks5://login:password@ip:port` и `http://login:password@ip:port`;
  - списки нескольких прокси.

## Проверка

```bash
BOT_TOKEN=123:ABC ADMIN_IDS=1 python -m compileall -q app
```
