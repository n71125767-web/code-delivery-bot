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

from decimal import Decimal


def _fmt_price_plain(value) -> str:
    try:
        q = Decimal(str(value)).quantize(Decimal("0.01"))
        out = format(q, "f")
        return out.rstrip("0").rstrip(".") if "." in out else out
    except Exception:
        return str(value or 0)


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
    total = len(products or [])
    cats = len(categories or [])
    lines = [
        "💰 Управление товарами",
        "",
        f"Категорий: {cats}",
        f"Товаров: {total}",
        "",
        "Выберите категорию или товар кнопкой ниже."
    ]
    if not categories and not products:
        lines.append("Категорий и товаров пока нет.")
    return "\n".join(lines)


def admin_catalog_keyboard(categories, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category in categories:
        count = len([p for p in products if p.category_id == category.id])
        icon = "📁" if category.is_active else "🙈"
        kb.button(text=f"{icon} {category.name} · {count}", callback_data=f"v25:category:{category.id}")
    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        kb.button(text=f"📂 Без категории · {len(uncategorized)}", callback_data="v28:uncategorized")
    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Настройки прокси", callback_data="admin:proxy")
    kb.button(text="⚙️ Вид", callback_data="v25:view_settings")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(2)
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
    kb.button(text="⬅️ Назад", callback_data="v25:catalog")
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
    kb.button(text="⬅️ Назад", callback_data="v25:catalog")
    kb.adjust(3, 2, 1)
    return kb.as_markup()


def sort_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↕️ По позиции", callback_data="v25:sort_set:position")
    kb.button(text="🔤 По названию", callback_data="v25:sort_set:name")
    kb.button(text="💰 По цене", callback_data="v25:sort_set:price")
    kb.button(text="🆕 Сначала новые", callback_data="v25:sort_set:newest")
    kb.button(text="⬅️ Назад", callback_data="v25:view_settings")
    kb.adjust(2)
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
        kb.button(text=f"{icon} {product.id} {product.name} · {_fmt_money_v53(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Вид", callback_data="v25:view_settings")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(2)
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
        kb.button(text=f"{icon} {product.id} {product.name} · {_fmt_money_v53(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data=f"v25:category_add_product:{category_id}")
    kb.button(text="📝 Название", callback_data=f"v25:category_name:{category_id}")
    kb.button(text="📄 Описание", callback_data=f"v25:category_description:{category_id}")
    kb.button(text="🖼 Фото", callback_data=f"v25:category_photo:{category_id}")
    kb.button(text="🙈 Скрыть" if active else "👁 Показать", callback_data=f"v25:category_toggle:{category_id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:category_delete_prompt:{category_id}")
    kb.button(text="⬅️ Назад", callback_data="v25:catalog")
    kb.adjust(2)
    return kb.as_markup()


def product_card_text(product: ShopProduct, stock_count: int = 0) -> str:
    type_label = "Статический" if product.product_type == "static" else "Количественный"
    lines = [
        f"📦 ТОВАР {product.id}",
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
        kb.button(text=f"{icon} {product.name} · {_fmt_money_v54(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Вид", callback_data="v25:view_settings")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(2)
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
        kb.button(text=f"{icon} {product.name} · {_fmt_money_v54(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data=f"v25:category_add_product:{category_id}")
    kb.button(text="📝 Название", callback_data=f"v25:category_name:{category_id}")
    kb.button(text="📝 Описание", callback_data=f"v25:category_description:{category_id}")
    kb.button(text="🖼 Фото", callback_data=f"v25:category_photo:{category_id}")
    kb.button(text="🙈 Скрыть" if active else "👁 Показать", callback_data=f"v25:category_toggle:{category_id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:category_delete_prompt:{category_id}")
    kb.button(text="🔙 Назад", callback_data="v25:catalog")
    kb.adjust(2)
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
        "📦 КАРТОЧКА ТОВАРА",
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
    kb.button(text="🚚 Поставщик", callback_data=f"admin:shop:product_supplier:{product.id}")
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
    kb.button(text="🎁 Выдать товар", callback_data=f"v25:give:{product_id}")
    kb.button(text="👁 Показать покупателю", callback_data=f"v25:preview:{product_id}")
    kb.button(text="📝 Платёжные системы", callback_data=f"v25:payment_systems:{product_id}")
    kb.button(text="📝 Описание платежа", callback_data=f"v25:payment_description:{product_id}")
    kb.button(text="🏷 Старая цена", callback_data=f"v25:old_price:{product_id}")
    kb.button(text="↕️ Позиция в списке", callback_data=f"v25:position:{product_id}")
    kb.button(text="📊 Статистика товара", callback_data=f"v25:stats:{product_id}")
    kb.button(text="⚙️ Способ выдачи", callback_data=f"v34:fulfillment_menu:{product_id}")
    kb.button(text="⬆️ Свернуть", callback_data=f"v25:product:{product_id}")
    kb.button(text="🔙 Назад", callback_data="v25:catalog")
    kb.adjust(2, 1, 2, 2, 1, 1)
    return kb.as_markup()


def delete_confirm_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"v25:delete_confirm:{product_id}")
    kb.button(text="🔙 Отмена", callback_data=f"v25:product:{product_id}")
    kb.adjust(2)
    return kb.as_markup()

# ---------------- V63 final clean catalog overrides ----------------
def admin_catalog_text(categories, products) -> str:
    total = len(products or [])
    cats = len(categories or [])
    if not categories and not products:
        return "💰 Управление товарами\n\nКатегорий и товаров пока нет."
    return f"💰 Управление товарами\n\nКатегорий: {cats}\nТоваров: {total}\n\nВыберите раздел кнопкой ниже."


def admin_catalog_keyboard(categories, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category in categories:
        count = len([p for p in products if p.category_id == category.id])
        icon = "📁" if category.is_active else "🙈"
        kb.button(text=f"{icon} {category.name} · {count}", callback_data=f"v25:category:{category.id}")
    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        kb.button(text=f"📂 Без категории · {len(uncategorized)}", callback_data="v28:uncategorized")
    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Настройки прокси", callback_data="admin:proxy")
    kb.button(text="⚙️ Вид", callback_data="v25:view_settings")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(2)
    return kb.as_markup()


def category_card_keyboard(category_id: int, active: bool, products=None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in list(products or [])[:30]:
        icon = "🟢" if product.is_active else "🙈"
        kb.button(text=f"{icon} {product.name} · {_fmt_money_v54(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    kb.button(text="➕ Товар", callback_data=f"v25:category_add_product:{category_id}")
    kb.button(text="📝 Название", callback_data=f"v25:category_name:{category_id}")
    kb.button(text="📝 Описание", callback_data=f"v25:category_description:{category_id}")
    kb.button(text="🖼 Фото", callback_data=f"v25:category_photo:{category_id}")
    kb.button(text="🙈 Скрыть" if active else "👁 Показать", callback_data=f"v25:category_toggle:{category_id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:category_delete_prompt:{category_id}")
    kb.button(text="🔙 Назад", callback_data="v25:catalog")
    kb.adjust(2)
    return kb.as_markup()

# ---------------- V65 compatibility hotfix: wizard keyboards restored ----------------
def product_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard used by the product creation wizard."""
    kb = InlineKeyboardBuilder()
    kb.button(text="♾️ Статический", callback_data="v25:type:static")
    kb.button(text="📦 Количественный", callback_data="v25:type:quantity")
    kb.button(text="🔙 Назад", callback_data="v25:wizard:back_name")
    kb.button(text="❌ Отмена", callback_data="v25:wizard:cancel")
    kb.adjust(2, 2)
    return kb.as_markup()


def currency_keyboard() -> InlineKeyboardMarkup:
    """Currency selector used by create/edit product flows."""
    kb = InlineKeyboardBuilder()
    preferred = ("USDT", "USD", "RUB", "TON")
    ordered = list(preferred) + [c for c in CURRENCIES if c not in preferred]
    for currency in ordered:
        kb.button(text=currency, callback_data=f"v25:currency:{currency}")
    kb.button(text="🔙 Назад", callback_data="v25:wizard:back_type")
    kb.button(text="❌ Отмена", callback_data="v25:wizard:cancel")
    kb.adjust(4, 4, 4, 2)
    return kb.as_markup()


def price_back_keyboard() -> InlineKeyboardMarkup:
    """Back/cancel controls for price input step."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="v25:wizard:back_currency")
    kb.button(text="❌ Отмена", callback_data="v25:wizard:cancel")
    kb.adjust(2)
    return kb.as_markup()


def content_back_keyboard() -> InlineKeyboardMarkup:
    """Generic cancel keyboard for text/photo/content input steps."""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="v25:wizard:cancel")
    kb.adjust(1)
    return kb.as_markup()


def fulfillment_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Fulfillment selector for product advanced settings."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Цифровой", callback_data=f"v34:fulfillment:{product_id}:digital")
    kb.button(text="📦 Склад", callback_data=f"v34:fulfillment:{product_id}:stock")
    kb.button(text="🌐 Прокси", callback_data=f"v34:fulfillment:{product_id}:proxyline")
    kb.button(text="🚚 Поставщик", callback_data=f"v34:fulfillment:{product_id}:supplier")
    kb.button(text="📱 Номер", callback_data=f"v34:fulfillment:{product_id}:number")
    kb.button(text="👤 Аккаунт", callback_data=f"v34:fulfillment:{product_id}:account")
    kb.button(text="🧩 Другое", callback_data=f"v34:fulfillment:{product_id}:manual")
    kb.button(text="🔙 Назад", callback_data=f"v25:product:{product_id}")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


# ---------------- V67 final catalog visual/navigation fixes ----------------
def admin_catalog_text(categories, products) -> str:
    if not categories and not products:
        return "💰 Управление товарами\n\nКатегорий и товаров пока нет."
    return "💰 Управление товарами\n\nВыберите категорию или товар кнопкой ниже."


def admin_catalog_keyboard(categories, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category in categories:
        count = len([p for p in products if p.category_id == category.id])
        suffix = f" · {count}" if count else ""
        kb.button(text=f"{category.name}{suffix}", callback_data=f"v25:category:{category.id}")
    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        kb.button(text=f"Без категории · {len(uncategorized)}", callback_data="v28:uncategorized")
    # Не дублируем товары из категорий в корне. На главной админки показываем категории + без категории.
    kb.button(text="➕ Товар", callback_data="v25:add_product")
    kb.button(text="➕ Категория", callback_data="v25:add_category")
    kb.button(text="⚙️ Вид", callback_data="v25:view_settings")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(2)
    return kb.as_markup()


def category_card_text(category: ShopCategory, product_count: int) -> str:
    if category.description:
        return f"{category.name}\n\n{category.description}\n\nВыберите товар кнопкой ниже."
    return f"{category.name}\n\nВыберите товар кнопкой ниже."


def category_card_keyboard(category_id: int, active: bool, products=None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in list(products or [])[:30]:
        kb.button(text=f"{product.name} · {_fmt_money_v54(product.price, product.currency)}", callback_data=f"v25:product:{product.id}")
    if not products:
        kb.button(text="Товаров пока нет", callback_data="v25:noop")
    kb.button(text="➕ Товар", callback_data=f"v25:category_add_product:{category_id}")
    kb.button(text="📝 Название", callback_data=f"v25:category_name:{category_id}")
    kb.button(text="📝 Описание", callback_data=f"v25:category_description:{category_id}")
    kb.button(text="🖼 Фото", callback_data=f"v25:category_photo:{category_id}")
    kb.button(text="Скрыть" if active else "Показать", callback_data=f"v25:category_toggle:{category_id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:category_delete_prompt:{category_id}")
    kb.button(text="🔙 Назад", callback_data="v25:catalog")
    kb.adjust(2)
    return kb.as_markup()


def product_card_text(product: ShopProduct, stock_count: int = 0) -> str:
    # Для прокси не показываем перегруженную логическую карточку — управление находится в разделе «Прокси».
    if (getattr(product, 'note', '') or '').startswith('proxy_autofix:'):
        return (
            f"{product.name}\n\n"
            f"Цена: {_fmt_money_v54(product.price, product.currency)}\n"
            f"Оплата: {'включена' if product.payment_enabled else 'выключена'}\n"
            f"Статус: {'показывается' if product.is_active else 'скрыт'}"
        )
    type_label = "Статический" if product.product_type == "static" else "Количественный"
    lines = [
        f"📦 Карточка товара",
        "",
        f"Название: {product.name}",
        f"Тип: {type_label}",
        f"Цена: {_fmt_money_v54(product.price, product.currency)}",
        f"Статус: {'показывается' if product.is_active else 'скрыт'}",
        f"Оплата: {'включена' if product.payment_enabled else 'выключена'}",
    ]
    if product.product_type == "quantity":
        lines.append(f"Остаток: {stock_count} шт.")
    if product.description:
        lines.extend(["", product.description])
    return "\n".join(lines)


def product_card_keyboard(product: ShopProduct) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    note = (getattr(product, 'note', '') or '')
    if note.startswith('proxy_autofix:'):
        kind = note.split(':', 1)[1]
        kb.button(text="💰 Цена", callback_data=f"admin:proxy:price:{kind}")
        kb.button(text="📈 Наценка", callback_data=f"admin:proxy:markup:{kind}")
        kb.button(text="📝 Текст", callback_data=f"admin:proxy:text:{kind}")
        kb.button(text=("Приостановить оплату" if product.payment_enabled else "Включить оплату"), callback_data=f"v25:toggle_payment:{product.id}")
        kb.button(text=("Скрыть товар" if product.is_active else "Показать товар"), callback_data=f"v25:toggle_visible:{product.id}")
        kb.button(text="🗑 Удалить", callback_data=f"v25:delete_prompt:{product.id}")
        kb.button(text="🔙 Назад", callback_data="admin:proxy")
        kb.adjust(2)
        return kb.as_markup()

    kb.button(text="🎁 Выдать товар", callback_data=f"v25:give:{product.id}")
    kb.button(text="🚚 Поставщик", callback_data=f"admin:shop:product_supplier:{product.id}")
    kb.button(text="✏️ Изменить товар", callback_data=f"v25:advanced:{product.id}")
    kb.button(text="👁 Показать товар", callback_data=f"v25:preview:{product.id}")
    kb.button(text="📝 Название", callback_data=f"v25:edit_name:{product.id}")
    kb.button(text="📝 Цена", callback_data=f"v25:edit_price:{product.id}")
    kb.button(text="📝 Описание", callback_data=f"v25:edit_description:{product.id}")
    kb.button(text="📝 Категория", callback_data=f"v25:edit_category:{product.id}")
    kb.button(text="📝 Валюта", callback_data=f"v25:edit_currency:{product.id}")
    kb.button(text="📝 Примечание", callback_data=f"v25:edit_note:{product.id}")
    kb.button(text=("Удалить фото" if getattr(product, 'photo_file_id', None) else "🖼 Добавить фото"), callback_data=(f"v25:photo_delete:{product.id}" if getattr(product, 'photo_file_id', None) else f"v25:edit_photo:{product.id}"))
    kb.button(text=("Приостановить оплату" if product.payment_enabled else "Включить оплату"), callback_data=f"v25:toggle_payment:{product.id}")
    kb.button(text="Расширенные настройки", callback_data=f"v25:advanced:{product.id}")
    if product.product_type == "quantity":
        kb.button(text="📦 Позиции товара", callback_data=f"v25:stock:{product.id}")
    kb.button(text=("Скрыть товар" if product.is_active else "Показать товар"), callback_data=f"v25:toggle_visible:{product.id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:delete_prompt:{product.id}")
    back = f"v25:category:{product.category_id}" if product.category_id else "v28:uncategorized"
    kb.button(text="🔙 Назад", callback_data=back)
    kb.adjust(2)
    return kb.as_markup()


# ---------------- V71 product card controls ----------------
def product_card_keyboard(product: ShopProduct) -> InlineKeyboardMarkup:
    """Final V71 product card buttons: clear preview vs buyer visibility + direct number fulfillment."""
    kb = InlineKeyboardBuilder()
    note = (getattr(product, 'note', '') or '')
    if note.startswith('proxy_autofix:'):
        kind = note.split(':', 1)[1]
        kb.button(text="💰 Цена", callback_data=f"admin:proxy:price:{kind}")
        kb.button(text="📈 Наценка", callback_data=f"admin:proxy:markup:{kind}")
        kb.button(text="📝 Текст", callback_data=f"admin:proxy:text:{kind}")
        kb.button(text=("⏸ Оплату" if product.payment_enabled else "▶️ Оплату"), callback_data=f"v25:toggle_payment:{product.id}")
        kb.button(text=("🙈 Скрыть покупателю" if product.is_active else "👁 Показать покупателю"), callback_data=f"v25:toggle_visible:{product.id}")
        kb.button(text="🗑 Удалить", callback_data=f"v25:delete_prompt:{product.id}")
        kb.button(text="🔙 Назад", callback_data="admin:proxy")
        kb.adjust(2)
        return kb.as_markup()

    kb.button(text="👁 Предпросмотр", callback_data=f"v25:preview:{product.id}")
    kb.button(text=("🙈 Скрыть покупателю" if product.is_active else "👁 Показать покупателю"), callback_data=f"v25:toggle_visible:{product.id}")
    kb.button(text="🎁 Выдать товар", callback_data=f"v25:give:{product.id}")
    kb.button(text="🚚 Поставщик", callback_data=f"admin:shop:product_supplier:{product.id}")
    kb.button(text="📱 Номер", callback_data=f"v34:fulfillment:{product.id}:number")
    kb.button(text="👤 Аккаунт", callback_data=f"v34:fulfillment:{product.id}:account")
    kb.button(text="⚙️ Выдача", callback_data=f"v34:fulfillment_menu:{product.id}")
    kb.button(text="📝 Название", callback_data=f"v25:edit_name:{product.id}")
    kb.button(text="📝 Цена", callback_data=f"v25:edit_price:{product.id}")
    kb.button(text="📝 Описание", callback_data=f"v25:edit_description:{product.id}")
    kb.button(text="📝 Категория", callback_data=f"v25:edit_category:{product.id}")
    kb.button(text="📝 Валюта", callback_data=f"v25:edit_currency:{product.id}")
    kb.button(text="📝 Примечание", callback_data=f"v25:edit_note:{product.id}")
    kb.button(text=("🖼 Удалить фото" if getattr(product, 'photo_file_id', None) else "🖼 Добавить фото"), callback_data=(f"v25:photo_delete:{product.id}" if getattr(product, 'photo_file_id', None) else f"v25:edit_photo:{product.id}"))
    kb.button(text=("⏸ Оплату" if product.payment_enabled else "▶️ Оплату"), callback_data=f"v25:toggle_payment:{product.id}")
    kb.button(text="⬆️ Расширенные", callback_data=f"v25:advanced:{product.id}")
    if product.product_type == "quantity":
        kb.button(text="📦 Позиции", callback_data=f"v25:stock:{product.id}")
    kb.button(text="🗑 Удалить", callback_data=f"v25:delete_prompt:{product.id}")
    back = f"v25:category:{product.category_id}" if product.category_id else "v28:uncategorized"
    kb.button(text="🔙 Назад", callback_data=back)
    kb.adjust(2)
    return kb.as_markup()


def advanced_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Final V71 advanced buttons appended below the normal product card when requested."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Выдать товар", callback_data=f"v25:give:{product_id}")
    kb.button(text="📱 Номер", callback_data=f"v34:fulfillment:{product_id}:number")
    kb.button(text="👤 Аккаунт", callback_data=f"v34:fulfillment:{product_id}:account")
    kb.button(text="⚙️ Способ выдачи", callback_data=f"v34:fulfillment_menu:{product_id}")
    kb.button(text="📝 Платёжные системы", callback_data=f"v25:payment_systems:{product_id}")
    kb.button(text="📝 Описание платежа", callback_data=f"v25:payment_description:{product_id}")
    kb.button(text="🏷 Старая цена", callback_data=f"v25:old_price:{product_id}")
    kb.button(text="↕️ Позиция", callback_data=f"v25:position:{product_id}")
    kb.button(text="📊 Статистика", callback_data=f"v25:stats:{product_id}")
    kb.button(text="⬇️ Свернуть", callback_data=f"v25:product:{product_id}")
    kb.adjust(2)
    return kb.as_markup()
