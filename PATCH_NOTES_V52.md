# V52 — UI roles, partners, orders, hard delete

## Critical
- Fixed Render crash: buyer main menu now includes `buyer:orders`, while paginated orders remain enabled.
- `python -m compileall -q app` passes.

## Partners and admin access
- Added admin menu item `🤝 Партнёры`.
- Partners/suppliers can be added and removed from buttons.
- Admins can give partners access to a product or category from buttons.
- Category access is stored as `cat:<category_id>` and is considered when assigning supplier orders.
- Admin capability management remains under `👥 Админы и права` / `🔐 Права админов`.

## Products and categories
- Product creation can use `📁 Без категории`.
- Product deletion now attempts physical removal.
- V52 migration makes `digital_purchases.product_id` nullable so products with old purchases can be deleted while purchase history remains.
- Cart entries, provider links and stock entries are removed with the product.
- Product issue prompt now supports Telegram ID or `@username`.

## Orders and cart
- Buyer orders use pages of up to 3 purchases with back/forward buttons.
- Cart quantity buttons are now simple `−`, current quantity, `+`.

## UI
- Added emoji-rich admin menu.
- Hidden, payments, settings and proxy admin areas are kept button-driven.
- Removed repeated spam of `🛠 Админ-панель` on admin Back buttons; the reply keyboard is sent once per admin-mode entry.
- Supplier panel buttons now clear broadcast/admin states before processing.
- `Я поставщик` is shown only to approved suppliers.
- Prices render as `0.00` format.

## Mirrors
- Added `🤖 Зеркала` help panel. Telegram bot tokens still must be created manually via BotFather; the panel explains how to run a second Render service with another token and the same database.
