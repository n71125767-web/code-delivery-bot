# MCS Shop — Clean V33

Единая production-сборка Telegram-магазина.

Запуск:

```bash
python -m app.bot
```

Используется один модуль обработчиков:

```text
app/handlers.py
```

Второго приложения `app.main` и конфликтующей папки `app/handlers/` нет.

Функции:
- каталог и медиа-карточки V32;
- админ-панель;
- статические и количественные товары;
- Crypto Pay;
- Proxyline;
- номера и поставщики;
- Telegram Business;
- PostgreSQL;
- health-check с проверкой БД.

Обязательные переменные Render:

```text
BOT_TOKEN
ADMIN_IDS
DATABASE_URL
```

Маркер запуска:

```text
FIX_MARKER_MCS_CLEAN=v33 loaded
```
