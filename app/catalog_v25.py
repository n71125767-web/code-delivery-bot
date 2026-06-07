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
                select(ShopProduct).order_by(ShopProduct.sort_order, ShopProduct.id)
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
        count = len([p for p in products if p.category_id == category.id])
        lines.append(f"\n{category.emoji} {category.name} ({count}){hidden}")

    uncategorized = [p for p in products if not p.category_id]
    if uncategorized:
        lines.append(f"\n📁 Без категории ({len(uncategorized)})")
    return "\n".join(lines)


def admin_catalog_keyboard(categories, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category in categories:
        count = len([p for p in products if p.category_id == category.id])
        prefix = "🙈" if not category.is_active else category.emoji
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
    kb.button(text="⬅️ Назад", callback_data="v25:wizard:back_price", style="danger")
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


def advanced_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
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
        f"Название: {category.emoji} {category.name}\n"
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
