# code-delivery-bot fixed

## Что исправлено

1. Убрана ошибка `message.bot["db"]()`.
2. База берётся через `SessionLocal`.
3. Business-сообщения теперь делятся на:
   - shop-бот Admaker;
   - админ-команды;
   - поставщика;
   - покупателя.
4. Для Business-ответов используется `business_connection_id`.
5. Сохраняется связь покупатель -> заказ -> business_connection_id.
6. Поставщик получает заявку, отвечает номером, потом кодом.
7. Бот отправляет номер/код покупателю.

## Установка Windows

```bat
cd C:\Users\Admin\Documents\code-delivery-bot
.venv\Scripts\activate.bat
pip install -r requirements.txt
python -m app.bot
```

## Если старая база ломается

Для разработки можно удалить старую SQLite-базу:

```bat
del bot.db
python -m app.bot
```

Если удалять нельзя, оставь базу, бот попробует добавить новые колонки сам.

## Проверка

1. Напиши боту `/ping`.
2. Должен ответить: `pong OK`.
3. Напиши `/status`.
4. От покупателя напиши название сервиса.
5. Поставщик должен получить сообщение.
