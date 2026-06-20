# V74 Payment / Withdrawal Fix

Изменения:

- Кнопка оплаты CryptoBot теперь первая сверху: `🟢 Оплатить CryptoBot`.
- Ниже стоит `🔄 Проверить оплату`.
- Последней стоит `❌ Отмена`.
- Добавлен callback `payment:cancel:<purchase_id>` для отмены ожидающей оплаты.
- Суммы в оплате теперь форматируются до 2 знаков после точки без `0.10000000` и похожего мусора.
- Пополнения кошелька получили такую же структуру кнопок.
- Для вывода поставщика добавлен прямой fallback к Crypto Pay API `createCheck`, если библиотечный метод не сработал.
- Если автоматический чек создать не удалось, заявка получает статус `manual_review` и уходит на ручную модерацию.
- Добавлена переменная `CRYPTO_PAY_API_BASE_URL` — опционально, по умолчанию выбирается автоматически по `CRYPTO_PAY_NETWORK`.

Env:

```env
CRYPTO_PAY_TOKEN=...
CRYPTO_PAY_NETWORK=mainnet
CRYPTO_PAY_API_BASE_URL=
WITHDRAW_AUTO_CRYPTOBOT=1
WITHDRAW_PAYOUT_ASSET=USDT
WITHDRAWAL_FEE_USD=2.5
```

Проверка:

```bash
python -m compileall -q app
unzip -t code_delivery_bot_MCS_PROXYLINE_V74_PAYMENT_WITHDRAW_FIX.zip
```
