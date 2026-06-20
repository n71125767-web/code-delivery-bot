from __future__ import annotations
from decimal import Decimal

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from app.models import ShopCategory, ShopProduct, ProductStockItem
from app.repositories.product_providers import (
    get_product_provider,
    unbind_product_provider,
)


async def all_categories(session):
    return list(
        (
            await session.scalars(
                select(ShopCategory).order_by(ShopCategory.sort_order, ShopCategory.id)
            )
        ).all()
    )


async def all_products(session, category_id: int | None = None):
    stmt = select(ShopProduct).where(ShopProduct.is_deleted.is_(False))
    if category_id is not None:
        stmt = stmt.where(ShopProduct.category_id == category_id)
    return list(
        (
            await session.scalars(stmt.order_by(ShopProduct.sort_order, ShopProduct.id))
        ).all()
    )


async def category_counts(session, category_id: int) -> tuple[int, int]:
    products = await session.scalar(
        select(func.count(ShopProduct.id)).where(
            ShopProduct.category_id == category_id,
            ShopProduct.is_deleted.is_(False),
        )
    )
    return int(products or 0), 0


def customer_home_text() -> str:
    return (
        "Выберите товар:"
    )


def customer_home_keyboard(
    categories,
    is_admin: bool = False,
    columns_count: int = 1,
    search_enabled: bool = True,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    visible = []

    for row in categories:
        if row.name.strip().lower() in {"все товары", "товары"}:
            continue
        if not row.is_active:
            continue
        visible.append(row)
        kb.button(
            text=f"{row.name}",
            callback_data=f"buyer:shopcat:{row.id}:0",
        )

    # Товары без категории доступны отдельной кнопкой, чтобы добавленный
    # «на главную» товар не пропадал из витрины.
    kb.button(text="📂 Без категории", callback_data="buyer:shopcat:0:0")

    if not visible:
        # Оставляем кнопку «Без категории», даже если категорий ещё нет.
        pass

    columns = max(1, min(int(columns_count or 1), 3))
    kb.adjust(columns)

    if search_enabled:
        kb.button(text="🔍 Поиск товара", callback_data="buyer:search")

    return kb.as_markup()


def category_customer_text(
    category, product_count: int, subcategory_count: int = 0
) -> str:
    if category.description:
        return f"{category.name}\n\n{category.description}\n\nВыберите товар 👇"
    return f"{category.name}\n\nВыберите товар 👇"


def admin_shop_text() -> str:
    return (
        "💰 Управление товарами\n\n"
        "Здесь можно создавать категории и товары, "
        "настраивать цену, валюту и способ выдачи."
    )


def admin_shop_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Категории и товары", callback_data="admin:shop:categories")
    kb.button(text="📋 Все товары", callback_data="admin:shop:products")
    kb.button(text="➕ Товар", callback_data="admin:shop:add_product")
    kb.button(text="➕ Категория", callback_data="admin:shop:add_category")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def admin_categories_text(rows) -> str:
    return "Список ваших категорий и товаров:\n\n" + (
        "\n".join(
            f"{'(скрыто) ' if not row.is_active else ''}{row.name}"
            for row in rows
        )
        or "Категорий пока нет."
    )


def admin_categories_keyboard(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in rows:
        prefix = "🙈" if not row.is_active else "▫️"
        kb.button(
            text=f"{prefix} {row.name}", callback_data=f"admin:shop:category:{row.id}"
        )
    kb.button(text="➕ Товар", callback_data="admin:shop:add_product")
    kb.button(text="➕ Категория", callback_data="admin:shop:add_category")
    kb.button(text="⚙️ Вид товаров", callback_data="admin:shop")
    kb.button(text="⬅️ Назад", callback_data="admin:shop")
    kb.adjust(2)
    return kb.as_markup()


def admin_category_text(category, product_count: int) -> str:
    return (
        f"🏷 Категория: {category.name}\n\n"
        "📝 Описание:\n"
        f"{getattr(category, 'description', None) or 'Не установлено'}\n\n"
        "📦 Содержимое категории:\n"
        f"├ Тарифы и услуги — {product_count}\n"
        "└ Подкатегории — 0"
    )


def admin_category_keyboard(category, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in products:
        icon = "✅" if row.is_active else "🙈"
        kb.button(
            text=f"{icon} {row.name}",
            callback_data=f"admin:shop:product:{row.id}",
        )
    kb.button(
        text="📝 Название категории",
        callback_data=f"admin:shop:category_name:{category.id}",
    )
    kb.button(
        text="📝 Описание категории",
        callback_data=f"admin:shop:category_desc:{category.id}",
    )
    kb.button(
        text="🙈 Скрыть категорию" if category.is_active else "👁 Показать категорию",
        callback_data=f"admin:shop:category_toggle:{category.id}",
    )
    kb.button(
        text="⬆️ Позиция выше", callback_data=f"admin:shop:category_up:{category.id}"
    )
    kb.button(
        text="⬇️ Позиция ниже", callback_data=f"admin:shop:category_down:{category.id}"
    )
    kb.button(text="➕ Товар", callback_data=f"admin:shop:add_product_to:{category.id}")
    kb.button(
        text="🗑 Удалить категорию",
        callback_data=f"admin:shop:category_delete_prompt:{category.id}",
    )
    kb.button(text="⬅️ Назад", callback_data="admin:shop:categories")
    kb.adjust(1, 2, 1, 2, 1, 1)
    return kb.as_markup()


def admin_products_text(rows) -> str:
    return "📦 Все товары\n\n" + (
        "\n".join(
            f"{'✅' if row.is_active else '🙈'} {row.id}. {row.name} — ID {row.internal_key}"
            for row in rows
        )
        or "Товаров пока нет."
    )


def admin_products_keyboard(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.button(
            text=f"{'✅' if row.is_active else '🙈'} {row.name}",
            callback_data=f"admin:shop:product:{row.id}",
        )
    kb.button(text="➕ Товар", callback_data="admin:shop:add_product")
    kb.button(text="⬅️ Назад", callback_data="admin:shop")
    kb.adjust(2)
    return kb.as_markup()


async def product_admin_text(session, product) -> str:
    provider = await get_product_provider(session, product.internal_key)
    provider_label = "Не назначен"
    if provider:
        provider_label = (
            "Proxyline API"
            if provider.provider_type == "proxyline"
            else f"Поставщик {provider.provider_key}"
        )
    return (
        f"📦 Товар: {product.name}\n\n"
        f"ID в каталоге: {product.id}\n"
        f"Внутренний ID: {product.internal_key}\n"
        f"Цена: {product.price or 'не указана'} {product.currency}\n"
        f"Статус: {'показывается' if product.is_active else 'скрыт'}\n"
        f"Выдача: {provider_label}\n\n"
        f"Описание:\n{product.description or 'Не установлено'}"
    )


def admin_product_keyboard(product) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Название", callback_data=f"admin:shop:product_name:{product.id}")
    kb.button(text="💵 Цена", callback_data=f"admin:shop:product_price:{product.id}")
    kb.button(text="📄 Описание", callback_data=f"admin:shop:product_desc:{product.id}")
    kb.button(
        text="🙈 Скрыть" if product.is_active else "👁 Показать",
        callback_data=f"admin:shop:product_toggle:{product.id}",
    )
    kb.button(
        text="🌐 Автовыдача", callback_data=f"admin:shop:product_proxy:{product.id}"
    )
    kb.button(
        text="🚚 Поставщик", callback_data=f"admin:shop:product_supplier:{product.id}"
    )
    kb.button(
        text="🔗 Убрать выдачу", callback_data=f"admin:shop:product_unbind:{product.id}"
    )
    kb.button(
        text="🗑 Удалить", callback_data=f"admin:shop:product_delete_prompt:{product.id}"
    )
    kb.button(
        text="⬅️ Назад",
        callback_data=f"admin:shop:category:{product.category_id or 0}",
    )
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


async def toggle_category(session, category_id: int):
    row = await session.get(ShopCategory, category_id)
    if row:
        row.is_active = not row.is_active
        await session.commit()
    return row


async def move_category(session, category_id: int, delta: int):
    row = await session.get(ShopCategory, category_id)
    if row:
        row.sort_order = int(row.sort_order or 0) + delta
        await session.commit()
    return row


async def delete_category(session, category_id: int) -> tuple[bool, str]:
    row = await session.get(ShopCategory, category_id)
    if not row:
        return False, "Категория не найдена."
    count = await session.scalar(
        select(func.count(ShopProduct.id)).where(ShopProduct.category_id == category_id)
    )
    if count:
        return False, "Сначала переместите или удалите товары из категории."
    await session.delete(row)
    await session.commit()
    return True, "Категория удалена."


async def toggle_product(session, product_id: int):
    row = await session.get(ShopProduct, product_id)
    if row:
        row.is_active = not row.is_active
        await session.commit()
    return row


async def delete_product(session, product_id: int):
    row = await session.get(ShopProduct, product_id)
    if row:
        from app.v51_features import hard_delete_product
        await hard_delete_product(session, product_id)
    return row


async def create_category(session, raw: str):
    raw = raw.strip()
    name = raw
    row = ShopCategory(name=name[:120], emoji="", is_active=True)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def create_product(session, raw: str, category_id: int | None = None):
    # Формат: INTERNAL_ID | Название | Цена | Валюта
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) < 2:
        raise ValueError("Формат: INTERNAL_ID | Название | Цена | Валюта")
    internal_id = int(parts[0])
    name = parts[1]
    price = None
    if len(parts) >= 3 and parts[2]:
        price = Decimal(parts[2].replace(",", "."))
    currency = parts[3].upper() if len(parts) >= 4 and parts[3] else "RUB"
    row = await session.scalar(
        select(ShopProduct).where(ShopProduct.internal_key == internal_id)
    )
    if row is None:
        row = ShopProduct(
            internal_key=internal_id,
            category_id=category_id,
            name=name,
            price=price,
            currency=currency,
            is_active=True,
        )
        session.add(row)
    else:
        row.name = name
        row.price = price
        row.currency = currency
        if category_id:
            row.category_id = category_id
        row.is_active = True
    await session.commit()
    await session.refresh(row)
    return row


# ---------------- V53 clean product/category lists ----------------
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


def admin_products_text(rows) -> str:
    return "📦 Товары\n\nВыберите товар кнопкой ниже." if rows else "📦 Товары\n\nТоваров пока нет."


def admin_products_keyboard(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in rows:
        icon = "✅" if row.is_active else "🙈"
        kb.button(text=f"{icon} #{row.id} {row.name} · {_fmt_money_v53(row.price, row.currency)}", callback_data=f"admin:shop:product:{row.id}")
    kb.button(text="➕ Товар", callback_data="admin:shop:add_product")
    kb.button(text="⬅️ Назад", callback_data="admin:shop")
    kb.adjust(2)
    return kb.as_markup()


def admin_category_text(category, product_count: int) -> str:
    return (
        f"📁 КАТЕГОРИЯ {category.name}\n\n"
        f"Название: {category.name}\n"
        f"Описание: {getattr(category, 'description', None) or 'не задано'}\n"
        f"Товаров: {product_count}\n"
        f"Статус: {'показывается' if category.is_active else 'скрыта'}\n\n"
        "Товары:"
    )


def admin_category_keyboard(category, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in products:
        icon = "✅" if row.is_active else "🙈"
        kb.button(text=f"{icon} #{row.id} {row.name} · {_fmt_money_v53(row.price, row.currency)}", callback_data=f"admin:shop:product:{row.id}")
    kb.button(text="➕ Товар", callback_data=f"admin:shop:add_product_to:{category.id}")
    kb.button(text="📝 Название", callback_data=f"admin:shop:category_name:{category.id}")
    kb.button(text="📄 Описание", callback_data=f"admin:shop:category_desc:{category.id}")
    kb.button(text="🙈 Скрыть" if category.is_active else "👁 Показать", callback_data=f"admin:shop:category_toggle:{category.id}")
    kb.button(text="⬆️ Выше", callback_data=f"admin:shop:category_up:{category.id}")
    kb.button(text="⬇️ Ниже", callback_data=f"admin:shop:category_down:{category.id}")
    kb.button(text="🗑 Удалить", callback_data=f"admin:shop:category_delete_prompt:{category.id}")
    kb.button(text="⬅️ Назад", callback_data="admin:shop:categories")
    kb.adjust(2)
    return kb.as_markup()


# ---------------- V54 legacy shop-admin visual overrides ----------------
def _fmt_money_v54(value, currency: str | None = None) -> str:
    from decimal import Decimal, InvalidOperation
    if value is None:
        rendered = "0"
    else:
        try:
            rendered = f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}".rstrip('0').rstrip('.')
        except (InvalidOperation, ValueError):
            rendered = str(value)
    return f"{rendered} {currency}" if currency else rendered


def admin_products_text(rows) -> str:
    return "💰 Управление товарами\n\nВыберите товар кнопкой ниже." if rows else "💰 Управление товарами\n\nТоваров пока нет."


def admin_products_keyboard(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in rows:
        icon = "🟢" if row.is_active else "🙈"
        kb.button(text=f"{icon} {row.id} {row.name} · {_fmt_money_v54(row.price, row.currency)}", callback_data=f"admin:shop:product:{row.id}")
    kb.button(text="➕ Товар", callback_data="admin:shop:add_product")
    kb.button(text="🔙 Назад", callback_data="admin:shop")
    kb.adjust(2)
    return kb.as_markup()


def admin_category_text(category, product_count: int) -> str:
    return (
        f"📁 КАТЕГОРИЯ {category.name}\n\n"
        f"Название: {category.name}\n"
        f"Описание: {getattr(category, 'description', None) or 'не задано'}\n"
        f"Товаров: {product_count}\n"
        f"Статус: {'показывается' if category.is_active else 'скрыта'}\n\n"
        "Товары открываются кнопками ниже."
    )


def admin_category_keyboard(category, products) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in products:
        icon = "🟢" if row.is_active else "🙈"
        kb.button(text=f"{icon} {row.id} {row.name} · {_fmt_money_v54(row.price, row.currency)}", callback_data=f"admin:shop:product:{row.id}")
    kb.button(text="➕ Товар", callback_data=f"admin:shop:add_product_to:{category.id}")
    kb.button(text="📝 Название", callback_data=f"admin:shop:category_name:{category.id}")
    kb.button(text="📝 Описание", callback_data=f"admin:shop:category_desc:{category.id}")
    kb.button(text="🙈 Скрыть" if category.is_active else "👁 Показать", callback_data=f"admin:shop:category_toggle:{category.id}")
    kb.button(text="⬆️ Выше", callback_data=f"admin:shop:category_up:{category.id}")
    kb.button(text="⬇️ Ниже", callback_data=f"admin:shop:category_down:{category.id}")
    kb.button(text="🗑 Удалить", callback_data=f"admin:shop:category_delete_prompt:{category.id}")
    kb.button(text="🔙 Назад", callback_data="admin:shop:categories")
    kb.adjust(2)
    return kb.as_markup()


async def product_admin_text(session, product) -> str:
    stock_count = 0
    if getattr(product, 'product_type', None) == 'quantity':
        stock_count = int(await session.scalar(select(func.count(ProductStockItem.id)).where(ProductStockItem.product_id == product.id, ProductStockItem.status == 'available')) or 0)
    type_label = "Статический" if product.product_type == "static" else "Количественный"
    photo_line = "🖼 Фото: установлено" if getattr(product, 'photo_file_id', None) else "🖼 Фото: не установлено"
    desc_line = "📝 Описание: установлено" if product.description else "📝 Описание: не установлено"
    category_line = "📂 Категория установлена" if product.category_id else "📂 Без категории"
    bot_username = __import__('os').getenv('BOT_USERNAME', '').strip().lstrip('@')
    direct = f"https://t.me/{bot_username}?start=admproduct_{product.internal_key}" if bot_username else f"/start admproduct_{product.internal_key}"
    lines = [
        f"📦 КАРТОЧКА ТОВАРА {product.id}", "", "➖➖➖➖➖➖➖➖➖➖", "",
        f"📝 Название: {product.name}",
        f"{'♾️' if product.product_type == 'static' else '📦'} Тип: {type_label}",
        "🟢 Покупка включена" if product.payment_enabled else "🔴 Покупка приостановлена",
        "", f"💰 Цена: {_fmt_money_v54(product.price, product.currency)}",
    ]
    if product.product_type == 'quantity':
        lines.extend(["", f"📊 Остаток позиций: {stock_count} шт."])
        if stock_count <= 3:
            lines.append("⚠️ Мало позиций — рекомендуем пополнить")
    lines.extend(["➖➖➖➖➖➖➖➖➖➖", "", photo_line, "", desc_line, "➖➖➖➖➖➖➖➖➖➖", "", category_line, "➖➖➖➖➖➖➖➖➖➖", "", "🔗 Прямая ссылка:", direct])
    return "\n".join(lines)


def admin_product_keyboard(product) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Выдать товар", callback_data=f"v25:give:{product.id}")
    kb.button(text="✏️ Изменить товар", callback_data=f"v25:advanced:{product.id}")
    kb.button(text="👁 Показать товар", callback_data=f"v25:preview:{product.id}")
    kb.button(text="📝 Название", callback_data=f"admin:shop:product_name:{product.id}")
    kb.button(text="📝 Цена", callback_data=f"admin:shop:product_price:{product.id}")
    kb.button(text="📝 Описание", callback_data=f"admin:shop:product_desc:{product.id}")
    kb.button(text=("⏸ Приостановить оплату" if product.payment_enabled else "▶️ Включить оплату"), callback_data=f"v25:toggle_payment:{product.id}")
    kb.button(text="🙈 Скрыть товар" if product.is_active else "👁 Показать товар", callback_data=f"admin:shop:product_toggle:{product.id}")
    kb.button(text="🗑 Удалить", callback_data=f"admin:shop:product_delete_prompt:{product.id}")
    kb.button(text="🔙 Назад", callback_data=f"admin:shop:category:{product.category_id or 0}")
    kb.adjust(3, 2, 2, 1, 1)
    return kb.as_markup()
