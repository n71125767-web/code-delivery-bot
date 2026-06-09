# MCS Shop V34 — настройки

Полный список переменных находится в `.env.example`.

Обязательные:
- BOT_TOKEN
- ADMIN_IDS
- DATABASE_URL

Crypto Pay:
- CRYPTO_PAY_TOKEN
- CRYPTO_PAY_NETWORK
- CRYPTO_PAY_WEBHOOK_SECRET
- CRYPTO_PAY_ACCEPTED_ASSETS
- CRYPTO_PAY_INVOICE_EXPIRES_SECONDS
- CRYPTO_PAY_RECOVERY_INTERVAL_SECONDS

Proxyline:
- PROXYLINE_ENABLED=1
- PROXYLINE_API_KEY

Для каждого Proxyline-товара:
1. В админке выберите способ выдачи «Proxyline».
2. Выполните:
   `/set_provider_key PRODUCT_ID {"country":"ru","period":30,"count":1,"ip_version":4,"type":"dedicated"}`

Для поставщика:
1. Выберите способ выдачи «Поставщик» или «Номер».
2. Выполните:
   `/set_provider_key PRODUCT_ID TELEGRAM_ID_ПОСТАВЩИКА`


## Админ-команды обслуживания

```text
/archived_products
/restore_product PRODUCT_ID
/set_provider_key PRODUCT_ID VALUE
```

## Проверка перед публикацией товара

Бот теперь не разрешит включить оплату или показать товар, пока не выполнено:
- задана цена и валюта;
- настроен Crypto Pay;
- выбран явный способ выдачи;
- для digital загружен контент;
- для stock есть позиция;
- для proxyline включён API и задан полный JSON;
- для supplier/number указан Telegram ID поставщика.


## Поставщики

`SUPPLIER_IDS` в Render больше не нужен.

Добавление:
```text
Админ меню
→ Поставщики
→ Добавить поставщика
→ отправить Telegram ID и имя
```

Удаление:
```text
Админ меню
→ Поставщики
→ Удалить поставщика
→ отправить Telegram ID
```

Привязка товара:
```text
Админ меню
→ Поставщики
→ Привязать товар
→ отправить: TELEGRAM_ID_ПОСТАВЩИКА ID_ТОВАРА
```
