# MCS Bot V37 — исправления и новые функции

## Исправленные ошибки

- Починены `/restore_product`, `/archived_products`, `/set_provider_key`: больше нет `NameError: user_id` и голых `return`.
- Починен порядок аргументов `bind_product_provider()` для поставщика и Proxyline.
- Починен откат резерва склада при ошибке создания CryptoBot-счёта.
- `ShopProduct.fulfillment_type` теперь является главным источником способа выдачи, `ProductProvider` используется только как legacy fallback.
- Добавлена проверка владельца заказа для buyer-callback действий: выбор сервиса, подтверждение сервиса, запрос кода, успешное закрытие, жалобы на номер/код.
- Синхронизированы безопасные дефолты `.env.example` и `config.py`.
- Логирование входящих текстов больше не пишет текст сообщения целиком, только длину.
- `invoice_keyboard()` теперь принимает старый третий аргумент `product_id`, который уже передавался в коде.

## Добавлено

### 1. Автоматическая выдача номеров

Режим `fulfillment_type=number` теперь работает через склад уникальных позиций так же, как обычный one-time stock.

Команда загрузки номеров:

```text
/number_stock_add PRODUCT_ID номер_1
номер_2
номер_3
```

После оплаты покупатель получает следующую свободную позицию автоматически.

### 2. Автоматическая выдача прокси

Исправлена привязка Proxyline из админки и команд. Для складских прокси также можно использовать:

```text
/proxy_stock_add PRODUCT_ID proxy_1
proxy_2
```

Для Proxyline API остаются:

```text
/bind_proxyline PRODUCT_ID
/set_provider_key PRODUCT_ID {JSON}
```

### 3. Маркетплейс с модерацией

Любой пользователь может подать заявку:

```text
/market_apply Название | Цена | Валюта | Категория | Описание
```

Админ:

```text
/market_applications
/market_approve ID [CATEGORY_ID]
/market_reject ID причина
```

При одобрении создаётся скрытый товар. Админ должен настроить выдачу и включить продажи.

### 4. Права ГА

Добавлен `GA_IDS` в `.env.example`. `ADMIN_IDS` остаётся обязательным.

Команды:

```text
/my_id
/grant_ga TELEGRAM_ID Имя
```

Важно: `/grant_ga` выдаёт права администратора в БД. Для «главного ГА» после рестарта/миграций добавьте ID в `GA_IDS` или `ADMIN_IDS` в Render Environment.

### 5. Добавить / удалить товары

Команды:

```text
/product_add Название | Цена | Валюта | CATEGORY_ID | Контент
/product_delete PRODUCT_ID
/restore_product PRODUCT_ID
/stock_add PRODUCT_ID позиции_каждая_с_новой_строки
```

Старая визуальная админка создания товаров также сохранена.

### 6. Статистика

Команды:

```text
/stats_full
/stats_product PRODUCT_ID
/feature_stats
```

Считаются товары, категории, заявки маркета, выданные покупки, проблемные выдачи, выручка, промокоды и wallet-платежи.

### 7. Переработанная система КД

Добавлена таблица `cooldown_settings` и команды:

```text
/cooldowns
/set_cooldown ACTION SECONDS
```

Например:

```text
/set_cooldown problem 60
/set_cooldown button:buyer 2
```

### 8. Аватар

Telegram Bot API не позволяет боту самостоятельно менять свой аватар. Команда `/bot_avatar` объясняет путь через BotFather. Картинки категорий и карточек товаров уже поддерживаются через file_id в админке.

### 9. CryptoBot API для оплаты в шопе

CryptoBot уже интегрирован. В V37 добавлены промокоды поверх CryptoBot, исправлена выдача one-time stock и idempotency cleanup.

### 10. Автоматическая оплата через наш кошелёк

Добавлены настройки:

```env
WALLET_PAYMENT_ENABLED=1
WALLET_PAYMENT_ADDRESS=...
WALLET_PAYMENT_CURRENCY=USDT
WALLET_WEBHOOK_SECRET=...
```

Покупатель видит кнопку «Оплатить на кошелёк». Бот создаёт `WalletPayment` с memo. Ваш внешний монитор кошелька должен отправить signed webhook:

```http
POST /wallet/webhook
Header: x-wallet-signature: HMAC_SHA256(raw_body, WALLET_WEBHOOK_SECRET)
Body: {"payment_id": 1, "status": "paid", "tx_hash": "..."}
```

Также есть ручное подтверждение:

```text
/wallet_confirm PAYMENT_ID [TX_HASH]
/wallet_payments
```

### 11. Система «накрутки»

Не добавлялись функции для внешней накрутки соцсетей, спама или искусственной манипуляции. Вместо этого добавлена безопасная внутренняя система баллов/трофеев: `internal_reward_events`, `customer_trophies`.

### 12. Картинки к категориям и админ-панелям

Существующая поддержка `photo_file_id` для категорий и товаров сохранена. Покупательские карточки используют фото товара, фото категории или asset fallback.

### 13. Автоматическая работа мануалов

Добавлена таблица `manual_pages` и команды:

```text
/manual_add Заголовок | Текст мануала
/manuals
```

Для авто-выдачи конкретного мануала привязывайте его содержимое как цифровой контент товара или позицию склада.

### 14. Промокоды

Команды:

```text
/promo CODE
/promo_create CODE percent|fixed VALUE MAX_USES [YYYY-MM-DD] [PRODUCT_ID]
/promos
/promo_disable CODE
```

Промокод применяется к следующей покупке пользователя через CryptoBot или wallet-платёж.

### 15. Топ покупателей

```text
/top_buyers all
/top_buyers week
/top_buyers month
```

### 16. Трофеи

```text
/trophies
```

Трофеи выдаются после успешной доставки покупки: первая покупка, 5 покупок, 10 покупок, VIP-сумма.

## Проверка

- `python -m compileall -q app` — успешно.
- Полный `pytest` в текущей среде не выполнен, потому что в контейнере отсутствуют runtime-зависимости `aiogram`, `aiocryptopay`, `aiosqlite`. В проекте они указаны в `requirements.txt`.

## V38 proxy + visual hotfix

- Убран ложный стоп в прокси-каталоге: если нет товара с точным словом `premium/standard/residential`, бот использует любой активный товар с `fulfillment_type=proxyline`.
- Добавлена админ-команда `/proxy_autofix [PRICE] [CURRENCY]`, которая создаёт/обновляет 4 активных Proxyline-товара: MTProxy, Премиум, Стандарт, Резидентские.
- Страны в Proxyline-каталоге теперь показываются на русском языке с флагами.
- Добавлен поиск страны через кнопку `🔎 Найти страну`.
- Переработан визуал раздела `🌐 Прокси`: карточки, шаги выбора, оформление счёта.

Быстрый запуск после деплоя:

```text
/proxy_autofix 100 RUB
```

После этого покупательский путь:

```text
🌐 Прокси → тип → страна/поиск → срок → оплата CryptoBot → автовыдача
```
