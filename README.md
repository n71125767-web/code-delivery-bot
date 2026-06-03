# Code Delivery Bot — Admin Account Version

## Главное отличие

1. Все сообщения покупателю и поставщику уходят через **админ-аккаунт (Business Account)**.
2. Бот не пишет самому себе и не создаёт циклы сообщений.

## Настройка

В `.env` нужно добавить:

```
ADMIN_BUSINESS_CONNECTION_ID=<id_твоего_админ_аккаунта>
```

## Запуск на Render

- Build Command: `pip install -r requirements.txt`
- Start Command: `bash start.sh`
- Environment Variables: BOT_TOKEN, ADMIN_IDS, SUPPLIER_IDS, SHOP_BOT_USERNAME, ADMIN_BUSINESS_CONNECTION_ID
