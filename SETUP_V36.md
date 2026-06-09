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


# Выбор страны и срока Proxyline

Покупатель проходит:

```text
Прокси
→ тип прокси
→ страна
→ 1 / 3 / 6 / 9 / 12 месяцев
→ CryptoBot
→ автоматическая выдача
```

Цена активного Proxyline-товара считается месячной:

```text
итоговая цена = цена товара × количество месяцев
```

Пример: если цена товара 3.10 USD:
- 1 месяц — 3.10 USD
- 3 месяца — 9.30 USD
- 6 месяцев — 18.60 USD
- 9 месяцев — 27.90 USD
- 12 месяцев — 37.20 USD

Страны бот пытается получить через Proxyline API и кэширует на 10 минут.
Fallback можно задать в Render:

```env
PROXYLINE_COUNTRIES_JSON={"ru":"Россия","us":"США","de":"Германия"}
```
