# MCS Proxyline Bot — V56 Clean

Готовая версия бота после чистки интерфейса и исправлений запуска.

## Запуск на Render

Build command:

```bash
python -m pip install --no-cache-dir -r requirements.txt
```

Start command:

```bash
python -m app.bot
```

Обязательные переменные:

```env
BOT_TOKEN=...
ADMIN_IDS=123456
GA_IDS=123456
DATABASE_URL=postgresql+asyncpg://...
ALLOW_SQLITE_ON_RENDER=0
BOT_SINGLE_INSTANCE_LOCK=1
```

Для Proxyline:

```env
PROXYLINE_ENABLED=1
PROXYLINE_API_KEY=...
```

## Важно про TelegramConflictError

В V56 добавлен PostgreSQL advisory-lock: если второй процесс с тем же `BOT_TOKEN` и той же базой попытается запустить polling, он не вызовет `getUpdates`.

Если ошибка всё равно появляется, значит где-то запущен второй бот с тем же токеном, но другой базой или без этого кода. Такой сервис нужно выключить в Render или локально.
