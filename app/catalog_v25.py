from __future__ import annotations

from sqlalchemy import select, func
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models import (
    ShopCategory,
    ShopProduct,
    ProductStockItem,
    CatalogDisplaySettings,
)

CURRENCIES = (
    "USDT",
    "TON",
    "BTC",
    "ETH",
    "LTC",
    "BNB",
    "TRX",
    "USDC",
    "USD",
    "EUR",
    "RUB",
    "UAH",
    "UZS",
)


def admin_reply_keyboard_v25() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Управление товарами")],
            [KeyboardButton(text="⚙️ Админ меню")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел администратора",
        selective=True,
    )


async def get_display_settings(session) -> CatalogDisplaySettings:
    row = await session.scalar(select(CatalogDisplaySettings).limit(1))
    if row is None:
        row = CatalogDisplaySettings(
            columns_count=1, sort_mode="position", search_enabled=True
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def admin_catalog_overview(session):
    categories = list(
        (
            await session.scalars(
                select(ShopCategory).order_by(ShopCategory.sort_order, ShopCategory.id)
            )
        ).all()
    )
    products = list(
        (
            await session.scalars(
                select(ShopProduct).where(ShopProduct.is_deleted.is_(False)).order_by(ShopProduct.sort_order, ShopProduct.id)
            )
        ).all()
    )
    return categories, products


def admin_catalog_text(categories, products) -> str:
    lines = ["💰 Управление товарами", "", "Список ваших категорий и товаров:"]
    if not categories and not products:
        lines.extend(["", "Категорий и товаров пока нет."])
        return "\n".join(lines)

    for category in categories:
        hidden = " (скрыто)" if not category.is_active else ""
        cat_products = [p for p in products if p.category_id == category.id]
        lines.append(f"\n{category.name} ({len(cat_products)}){hidden}")
        for product in cat_products[:8]:
            price = f"{product.price} {product.currency}" if getattr(product, "price", None) is not None else "без цены"
            lines.append(f"  • #{product.id} — {product.name} — {price}")

    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        lines.append(f"\n📁 Без категории ({len(uncategorized)})")
    return "\n".join(lines)


def admin_catalog_keyboard(categories, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category in categories:
        count = len([p for p in products if p.category_id == category.id])
        prefix = "🙈" if not category.is_active else "▫️"
        kb.button(
            text=f"{prefix} {category.name} ({count})",
            callback_data=f"v25:category:{category.id}",
        )

    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        kb.button(
            text=f"📁 Без категории ({len(uncategorized)})",
            callback_data="v28:uncategorized",
        )

    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Вид товаров", callback_data="v25:view_settings")
    kb.button(text="⬅️ Назад", callback_data="admin:panel", style="danger")
    kb.adjust(*([1] * (len(categories) + (1 if uncategorized else 0))), 2, 1, 1)
    return kb.as_markup()


def product_type_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="♾️ Статический товар", callback_data="v25:type:static")
    kb.button(text="📦 Количественный товар", callback_data="v25:type:quantity")
    kb.button(text="⬅️ Назад", callback_data="v25:wizard:back_name", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def currency_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code in CURRENCIES:
        kb.button(text=code, callback_data=f"v25:currency:{code}")
    kb.button(text="⬅️ Назад", callback_data="v25:wizard:back_type", style="danger")
    kb.adjust(3)
    return kb.as_markup()


def price_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="v25:wizard:back_currency", style="danger")
    return kb.as_markup()


def content_back_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="v25:wizard:back_price")
    kb.button(text="❌ Отмена", callback_data="v25:wizard:cancel")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def product_card_text(product: ShopProduct, stock_count: int = 0) -> str:
    type_label = "Статический" if product.product_type == "static" else "Количественный"
    payment = (
        "🟢 Покупка включена"
        if product.payment_enabled
        else "🔴 Покупка приостановлена"
    )
    visibility = "показывается" if product.is_active else "скрыт"

    lines = [
        f"📦 КАРТОЧКА ТОВАРА #{product.id}",
        "",
        "➖➖➖➖➖➖➖➖➖➖",
        "",
        f"📝 Название: {product.name}",
        f"{'♾️' if product.product_type == 'static' else '📦'} Тип: {type_label}",
        payment,
        f"👁 Товар: {visibility}",
        "",
        f"💰 Цена: {product.price or 0} {product.currency}",
        f"⚙️ Выдача: {product.fulfillment_type}",
    ]

    if product.old_price is not None:
        lines.append(f"🏷 Старая цена: {product.old_price} {product.currency}")
    if product.category_id:
        lines.append(f"📁 Категория ID: {product.category_id}")
    if product.description:
        lines.extend(["", f"📄 Описание: {product.description}"])
    if product.note:
        lines.append(f"🗒 Примечание: {product.note}")
    if product.product_type == "quantity":
        lines.append(f"📚 Доступно позиций: {stock_count}")

    lines.extend(
        [
            "",
            "➖➖➖➖➖➖➖➖➖➖",
            "",
            "🔗 Прямая ссылка:",
            f"/start product_{product.id}",
        ]
    )
    return "\n".join(lines)


def product_card_keyboard(product: ShopProduct) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Выдать товар", callback_data=f"v25:give:{product.id}")
    kb.button(
        text="📦 Изменить контент", callback_data=f"v25:edit_content:{product.id}"
    )

    kb.button(text="📝 Название", callback_data=f"v25:edit_name:{product.id}")
    kb.button(text="💰 Цена", callback_data=f"v25:edit_price:{product.id}")
    kb.button(text="📄 Описание", callback_data=f"v25:edit_description:{product.id}")
    kb.button(text="📁 Категория", callback_data=f"v25:edit_category:{product.id}")
    kb.button(text="💱 Валюта", callback_data=f"v25:edit_currency:{product.id}")
    kb.button(text="🗒 Примечание", callback_data=f"v25:edit_note:{product.id}")

    kb.button(text="🖼 Фото товара", callback_data=f"v25:edit_photo:{product.id}")
    kb.button(text="🎬 Видео товара", callback_data=f"v25:edit_video:{product.id}")

    if product.product_type == "quantity":
        kb.button(text="📦 Позиции товара", callback_data=f"v25:stock:{product.id}")

    kb.button(
        text=(
            "⏸ Приостановить оплату"
            if product.payment_enabled
            else "▶️ Включить оплату"
        ),
        callback_data=f"v25:toggle_payment:{product.id}",
    )
    kb.button(
        text="🙈 Скрыть товар" if product.is_active else "👁 Показать товар",
        callback_data=f"v25:toggle_visible:{product.id}",
    )

    kb.button(
        text="⚙️ Расширенные настройки", callback_data=f"v25:advanced:{product.id}"
    )
    kb.button(text="📊 Статистика товара", callback_data=f"v25:stats:{product.id}")
    kb.button(text="🗑 Удалить товар", callback_data=f"v25:delete_prompt:{product.id}")
    kb.button(text="⬅️ Назад", callback_data="v25:catalog", style="danger")
    kb.adjust(2, 2, 2, 2, 2, 1, 1, 1, 1)
    return kb.as_markup()


def fulfillment_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Статический контент", callback_data=f"v34:fulfillment:{product_id}:digital")
    kb.button(text="📦 Склад позиций", callback_data=f"v34:fulfillment:{product_id}:stock")
    kb.button(text="🌐 Proxyline", callback_data=f"v34:fulfillment:{product_id}:proxyline")
    kb.button(text="🚚 Поставщик", callback_data=f"v34:fulfillment:{product_id}:supplier")
    kb.button(text="📱 Номер", callback_data=f"v34:fulfillment:{product_id}:number")
    kb.button(text="⬅️ Назад", callback_data=f"v25:advanced:{product_id}", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def advanced_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="⚙️ Способ выдачи", callback_data=f"v34:fulfillment_menu:{product_id}"
    )
    kb.button(
        text="💳 Платежные системы", callback_data=f"v25:payment_systems:{product_id}"
    )
    kb.button(
        text="🧾 Описание платежа",
        callback_data=f"v25:payment_description:{product_id}",
    )
    kb.button(text="🏷 Старая цена", callback_data=f"v25:old_price:{product_id}")
    kb.button(text="↕️ Позиция в списке", callback_data=f"v25:position:{product_id}")
    kb.button(
        text="⬅️ Назад", callback_data=f"v25:product:{product_id}", style="danger"
    )
    kb.adjust(1)
    return kb.as_markup()


def delete_confirm_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Удалить",
        callback_data=f"v25:delete_confirm:{product_id}",
        style="danger",
    )
    kb.button(
        text="⬅️ Отмена", callback_data=f"v25:product:{product_id}", style="danger"
    )
    kb.adjust(1)
    return kb.as_markup()


def category_card_text(category: ShopCategory, product_count: int) -> str:
    return (
        f"📁 КАТЕГОРИЯ #{category.id}\n\n"
        f"Название: {category.name}\n"
        f"Описание: {category.description or 'не задано'}\n"
        f"Товаров: {product_count}\n"
        f"Статус: {'показывается' if category.is_active else 'скрыта'}"
    )


def category_card_keyboard(category_id: int, active: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Название", callback_data=f"v25:category_name:{category_id}")
    kb.button(
        text="📄 Описание", callback_data=f"v25:category_description:{category_id}"
    )
    kb.button(text="🖼 Фото", callback_data=f"v25:category_photo:{category_id}")
    kb.button(
        text="🙈 Скрыть" if active else "👁 Показать",
        callback_data=f"v25:category_toggle:{category_id}",
    )
    kb.button(
        text="➕ Добавить товар",
        callback_data=f"v25:category_add_product:{category_id}",
    )
    kb.button(
        text="🗑 Удалить", callback_data=f"v25:category_delete_prompt:{category_id}"
    )
    kb.button(text="⬅️ Назад", callback_data="v25:catalog", style="danger")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def view_settings_text(settings: CatalogDisplaySettings) -> str:
    return (
        "⚙️ Настройки отображения\n\n"
        "Здесь вы можете настроить:\n"
        "📊 Количество столбцов\n"
        "🔄 Порядок сортировки\n"
        "🔍 Кнопку поиска для пользователей\n\n"
        f"Столбцов сейчас: {settings.columns_count}\n"
        f"Сортировка: {settings.sort_mode}\n"
        f"Поиск: {'включен' if settings.search_enabled else 'выключен'}\n\n"
        "Выберите нужную настройку ниже 👇"
    )


def view_settings_keyboard(settings: CatalogDisplaySettings) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for count in (1, 2, 3):
        prefix = "✅ " if settings.columns_count == count else ""
        kb.button(text=f"{prefix}{count}", callback_data=f"v25:columns:{count}")
    kb.button(text="🔄 Сортировка", callback_data="v25:sort")
    kb.button(
        text="🔍 Выключить поиск" if settings.search_enabled else "🔍 Включить поиск",
        callback_data="v25:search_toggle",
    )
    kb.button(text="⬅️ Назад", callback_data="v25:catalog", style="danger")
    kb.adjust(3, 2, 1)
    return kb.as_markup()


def sort_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↕️ По позиции", callback_data="v25:sort_set:position")
    kb.button(text="🔤 По названию", callback_data="v25:sort_set:name")
    kb.button(text="💰 По цене", callback_data="v25:sort_set:price")
    kb.button(text="🆕 Сначала новые", callback_data="v25:sort_set:newest")
    kb.button(text="⬅️ Назад", callback_data="v25:view_settings", style="danger")
    kb.adjust(1)
    return kb.as_markup()


async def stock_count(session, product_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(ProductStockItem.id)).where(
                ProductStockItem.product_id == product_id,
                ProductStockItem.status == "available",
            )
        )
        or 0
    )


async def add_text_stock(session, product_id: int, raw: str) -> int:
    rows = [line.strip() for line in raw.splitlines() if line.strip()]
    for row in rows:
        session.add(
            ProductStockItem(
                product_id=product_id, content_type="text", content_text=row
            )
        )
    await session.commit()
    return len(rows)


async def next_stock_item(session, product_id: int):
    row = await session.scalar(
        select(ProductStockItem)
        .where(
            ProductStockItem.product_id == product_id,
            ProductStockItem.status == "available",
        )
        .order_by(ProductStockItem.id)
        .limit(1)
    )
    return row


# ---------------- V53 clean catalog/admin visual overrides ----------------
def _fmt_money_v53(value, currency: str | None = None) -> str:
    from decimal import Decimal, InvalidOperation
    if value is None:
        rendered = "0"
    else:
        try:
            rendered = f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}".rstrip('0').rstrip('.')
        except (InvalidOperation, ValueError):
            rendered = str(value)
    return f"{rendered} {currency}" if currency else rendered


def admin_catalog_text(categories, products) -> str:
    total_categories = len(categories or [])
    total_products = len(products or [])
    return (
        "📦 Управление товарами\n\n"
        f"📁 Категорий: {total_categories}\n"
        f"🛍 Товаров: {total_products}\n\n"
        "Выберите категорию или товар кнопкой ниже."
    )


def admin_catalog_keyboard(categories, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category in categories:
        count = len([p for p in products if p.category_id == category.id])
        icon = "👁" if category.is_active else "🙈"
        kb.button(text=f"📁 {category.name} · {count}", callback_data=f"v25:category:{category.id}")
    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        kb.button(text=f"📂 Без категории · {len(uncategorized)}", callback_data="v28:uncategorized")
    for product in [p for p in products if not p.category_id][:20]:
        icon = "✅" if product.is_active else "🙈"
        kb.button(text=f"{icon} #{product.id} {product.name} · {_fmt_money_v53(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Вид", callback_data="v25:view_settings")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def category_card_text(category: ShopCategory, product_count: int) -> str:
    return (
        f"📁 КАТЕГОРИЯ {category.name}\n\n"
        f"Название: {category.name}\n"
        f"Описание: {category.description or 'не задано'}\n"
        f"Товаров: {product_count}\n"
        f"Статус: {'показывается' if category.is_active else 'скрыта'}\n\n"
        "Товары:"
    )


def category_card_keyboard(category_id: int, active: bool, products=None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in list(products or [])[:30]:
        icon = "✅" if product.is_active else "🙈"
        kb.button(text=f"{icon} #{product.id} {product.name} · {_fmt_money_v53(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data=f"v25:category_add_product:{category_id}")
    kb.button(text="📝 Название", callback_data=f"v25:category_name:{category_id}")
    kb.button(text="📄 Описание", callback_data=f"v25:category_description:{category_id}")
    kb.button(text="🖼 Фото", callback_data=f"v25:category_photo:{category_id}")
    kb.button(text="🙈 Скрыть" if active else "👁 Показать", callback_data=f"v25:category_toggle:{category_id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:category_delete_prompt:{category_id}")
    kb.button(text="⬅️ Назад", callback_data="v25:catalog")
    kb.adjust(1)
    return kb.as_markup()


def product_card_text(product: ShopProduct, stock_count: int = 0) -> str:
    type_label = "Статический" if product.product_type == "static" else "Количественный"
    lines = [
        f"📦 ТОВАР #{product.id}",
        "",
        f"Название: {product.name}",
        f"Тип: {type_label}",
        f"Цена: {_fmt_money_v53(product.price, product.currency)}",
        f"Статус: {'показывается' if product.is_active else 'скрыт'}",
        f"Оплата: {'включена' if product.payment_enabled else 'выключена'}",
        f"Выдача: {product.fulfillment_type}",
    ]
    if product.category_id:
        lines.append(f"Категория ID: {product.category_id}")
    if product.description:
        lines += ["", f"Описание: {product.description}"]
    if product.note:
        lines.append(f"Примечание: {product.note}")
    if product.product_type == "quantity":
        lines.append(f"Доступно позиций: {stock_count}")
    lines += ["", f"Ссылка: /start product_{product.id}"]
    return "\n".join(lines)


# ---------------- V54 final catalog/card visual overrides ----------------
def _fmt_money_v54(value, currency: str | None = None) -> str:
    from decimal import Decimal, InvalidOperation
    if value is None:
        rendered = "0"
    else:
        try:
            rendered = f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}".rstrip('0').rstrip('.')
        except (InvalidOperation, ValueError):
            rendered = str(value).rstrip('0').rstrip('.') if '.' in str(value) else str(value)
    return f"{rendered} {currency}" if currency else rendered


def admin_catalog_text(categories, products) -> str:
    if not categories and not products:
        return "💰 Управление товарами\n\nКатегорий и товаров пока нет."
    return "💰 Управление товарами\n\nВыберите категорию или товар кнопкой ниже."


def admin_catalog_keyboard(categories, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category in categories:
        count = len([p for p in products if p.category_id == category.id])
        icon = "📁" if category.is_active else "🙈"
        kb.button(text=f"{icon} {category.name} · {count}", callback_data=f"v25:category:{category.id}")
    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        kb.button(text=f"📂 Без категории · {len(uncategorized)}", callback_data="v28:uncategorized")
    for product in uncategorized[:20]:
        icon = "🟢" if product.is_active else "🙈"
        kb.button(text=f"{icon} #{product.id} {product.name} · {_fmt_money_v54(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Вид", callback_data="v25:view_settings")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def category_card_text(category: ShopCategory, product_count: int) -> str:
    return (
        f"📁 КАТЕГОРИЯ {category.name}\n\n"
        f"Название: {category.name}\n"
        f"Описание: {category.description or 'не задано'}\n"
        f"Товаров: {product_count}\n"
        f"Статус: {'показывается' if category.is_active else 'скрыта'}\n\n"
        "Товары открываются кнопками ниже."
    )


def category_card_keyboard(category_id: int, active: bool, products=None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in list(products or [])[:30]:
        icon = "🟢" if product.is_active else "🙈"
        kb.button(text=f"{icon} #{product.id} {product.name} · {_fmt_money_v54(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data=f"v25:category_add_product:{category_id}")
    kb.button(text="📝 Название", callback_data=f"v25:category_name:{category_id}")
    kb.button(text="📝 Описание", callback_data=f"v25:category_description:{category_id}")
    kb.button(text="🖼 Фото", callback_data=f"v25:category_photo:{category_id}")
    kb.button(text="🙈 Скрыть" if active else "👁 Показать", callback_data=f"v25:category_toggle:{category_id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:category_delete_prompt:{category_id}")
    kb.button(text="🔙 Назад", callback_data="v25:catalog")
    kb.adjust(1)
    return kb.as_markup()


def product_card_text(product: ShopProduct, stock_count: int = 0) -> str:
    type_label = "Статический" if product.product_type == "static" else "Количественный"
    payment_line = "🟢 Покупка включена" if product.payment_enabled else "🔴 Покупка приостановлена"
    photo_line = "🖼 Фото: установлено" if getattr(product, 'photo_file_id', None) else "🖼 Фото: не установлено"
    desc_line = "📝 Описание: установлено" if product.description else "📝 Описание: не установлено"
    category_line = "📂 Категория установлена" if product.category_id else "📂 Без категории"
    bot_username = __import__('os').getenv('BOT_USERNAME', '').strip().lstrip('@')
    direct = f"https://t.me/{bot_username}?start=admproduct_{product.internal_key}" if bot_username else f"/start admproduct_{product.internal_key}"
    lines = [
        f"📦 КАРТОЧКА ТОВАРА #{product.id}",
        "",
        "➖➖➖➖➖➖➖➖➖➖",
        "",
        f"📝 Название: {product.name}",
        f"{'♾️' if product.product_type == 'static' else '📦'} Тип: {type_label}",
        payment_line,
        "",
        f"💰 Цена: {_fmt_money_v54(product.price, product.currency)}",
    ]
    if product.product_type == "quantity":
        lines.extend(["", f"📊 Остаток позиций: {stock_count} шт."])
        if stock_count <= 3:
            lines.append("⚠️ Мало позиций — рекомендуем пополнить")
    lines.extend([
        "➖➖➖➖➖➖➖➖➖➖",
        "",
        photo_line,
        "",
        desc_line,
        "➖➖➖➖➖➖➖➖➖➖",
        "",
        category_line,
        "➖➖➖➖➖➖➖➖➖➖",
        "",
        "🔗 Прямая ссылка:",
        direct,
    ])
    return "\n".join(lines)


def product_card_keyboard(product: ShopProduct) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Выдать товар", callback_data=f"v25:give:{product.id}")
    kb.button(text="✏️ Изменить товар", callback_data=f"v25:advanced:{product.id}")
    kb.button(text="👁 Показать товар", callback_data=f"v25:preview:{product.id}")
    kb.button(text="📝 Название", callback_data=f"v25:edit_name:{product.id}")
    kb.button(text="📝 Цена", callback_data=f"v25:edit_price:{product.id}")
    kb.button(text="📝 Описание", callback_data=f"v25:edit_description:{product.id}")
    kb.button(text="📝 Категория", callback_data=f"v25:edit_category:{product.id}")
    kb.button(text="📝 Валюта", callback_data=f"v25:edit_currency:{product.id}")
    kb.button(text="📝 Примечание", callback_data=f"v25:edit_note:{product.id}")
    kb.button(text=("🗑 Удалить фото товара" if getattr(product, 'photo_file_id', None) else "🖼 Добавить фото товара"), callback_data=(f"v25:photo_delete:{product.id}" if getattr(product, 'photo_file_id', None) else f"v25:edit_photo:{product.id}"))
    kb.button(text=("⏸ Приостановить оплату" if product.payment_enabled else "▶️ Включить оплату"), callback_data=f"v25:toggle_payment:{product.id}")
    kb.button(text="⬇️ Расширенные настройки", callback_data=f"v25:advanced:{product.id}")
    if product.product_type == "quantity":
        kb.button(text="📦 Позиции товара", callback_data=f"v25:stock:{product.id}")
    kb.button(text=("🙈 Скрыть товар" if product.is_active else "👁 Показать товар"), callback_data=f"v25:toggle_visible:{product.id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:delete_prompt:{product.id}")
    kb.button(text="🔙 Назад", callback_data="v25:catalog")
    kb.adjust(3, 2, 2, 2, 1, 1, 1, 1)
    return kb.as_markup()


def advanced_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Платёжные системы", callback_data=f"v25:payment_systems:{product_id}")
    kb.button(text="📝 Описание платежа", callback_data=f"v25:payment_description:{product_id}")
    kb.button(text="🏷 Старая цена", callback_data=f"v25:old_price:{product_id}")
    kb.button(text="↕️ Позиция в списке", callback_data=f"v25:position:{product_id}")
    kb.button(text="📊 Статистика товара", callback_data=f"v25:stats:{product_id}")
    kb.button(text="⚙️ Способ выдачи", callback_data=f"v34:fulfillment_menu:{product_id}")
    kb.button(text="⬆️ Свернуть", callback_data=f"v25:product:{product_id}")
    kb.adjust(1)
    return kb.as_markup()


def delete_confirm_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"v25:delete_confirm:{product_id}")
    kb.button(text="🔙 Отмена", callback_data=f"v25:product:{product_id}")
    kb.adjust(1)
    return kb.as_markup()
