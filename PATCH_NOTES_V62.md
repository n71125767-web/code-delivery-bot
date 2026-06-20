# V62 — unified buttons, hard-delete fix, proxy text editing

## Исправлено

- Единые названия и эмодзи прокси в покупательском и админском интерфейсе:
  - 🔐 MTProxy
  - 🏆 PREMIUM
  - 💯 STANDART
  - 🏠 RESIDENTIAL
- Админский раздел прокси больше не использует разные синие/фиолетовые эмодзи для тех же действий.
- В карточке каждого прокси добавлена кнопка `📝 Текст`.
- Текст прокси теперь можно менять кнопкой: `⚙️ Админ меню → 🌐 Прокси → нужный тип → 📝 Текст`.
- Исправлено физическое удаление товаров: перед удалением чистятся/отвязываются все известные ссылки из `marketplace_applications`, `promo_codes`, `wallet_payments`, `digital_purchases`, `cart_items`, `product_stock_items`, `product_providers`.
- Добавлен дополнительный PostgreSQL-safe cleanup: если появятся новые таблицы с FK на `shop_products`, бот попробует отвязать их перед удалением.
- Добавлена миграция PostgreSQL для FK на `shop_products(id)` с `ON DELETE SET NULL`, чтобы история не блокировала удаление товара.
- Старый прямой `session.delete(row)` для товара в `shop_admin_v20.py` заменён на общий safe hard-delete.

## По анимированным эмодзи

Telegram Bot API принимает текст кнопки как обычную строку. Поэтому в inline/reply keyboard можно использовать обычные Unicode-эмодзи, но нельзя полноценно передать custom animated emoji как entity внутри кнопки. Для кнопок используйте обычный эмодзи в названии товара/кнопки. Custom animated emoji можно показывать в тексте сообщения только через `custom_emoji_id`, но не как анимированную entity внутри кнопки.
