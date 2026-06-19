# PATCH V42 — DigitalPurchase migration fix

Исправлена ошибка Render/PostgreSQL:

```text
UndefinedColumnError: column digital_purchases.quantity does not exist
```

Причина: в модели `DigitalPurchase` появились поля `quantity` и `updated_at`, но в существующей PostgreSQL-базе они не добавлялись автоматической миграцией.

Что изменено:

- в `app/database.py` добавлена idempotent-миграция для `digital_purchases.quantity`;
- добавлена idempotent-миграция для `digital_purchases.updated_at`;
- новые колонки добавляются автоматически при старте приложения;
- для существующих строк `quantity` получает значение `1`, а `updated_at` — текущий timestamp.

После деплоя достаточно перезапустить сервис Render. Отдельный SQL вручную выполнять не нужно.
