from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from app.models import ShopCategory, ShopProduct, Order


def money(value, currency: str = "RUB") -> str:
    if value is None:
        return "Цена уточняется"
    try:
        number = Decimal(str(value))
        rendered = f"{number:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
    except (InvalidOperation, ValueError):
        rendered = str(value)
    return f"{rendered} {currency}"


async def ensure_default_category(session) -> ShopCategory:
    row = await session.scalar(select(ShopCategory).order_by(ShopCategory.id).limit(1))
    if row:
        return row
    row = ShopCategory(name="Все товары", emoji="🛍", sort_order=0, is_active=True)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def sync_products_from_orders(session) -> int:
    category = await ensure_default_category(session)
    rows = (await session.execute(
        select(Order.product_id, Order.product_name, func.max(Order.amount), func.max(Order.currency))
        .where(Order.product_id.is_not(None))
        .group_by(Order.product_id, Order.product_name)
    )).all()
    created = 0
    for product_id, product_name, amount, currency in rows:
        exists = await session.scalar(select(ShopProduct).where(ShopProduct.admaker_product_id == product_id))
        if exists:
            if not exists.name and product_name:
                exists.name = product_name
            continue
        session.add(ShopProduct(
            admaker_product_id=int(product_id),
            category_id=category.id,
            name=product_name or f"Товар {product_id}",
            description="Товар из Admaker Shop",
            price=amount,
            currency=currency or "RUB",
            is_active=True,
        ))
        created += 1
    await session.commit()
    return created


async def list_categories(session):
    return list((await session.scalars(
        select(ShopCategory).where(ShopCategory.is_active.is_(True)).order_by(ShopCategory.sort_order, ShopCategory.id)
    )).all())


async def list_products(session, category_id: int | None = None):
    stmt = select(ShopProduct).where(ShopProduct.is_active.is_(True))
    if category_id is not None:
        stmt = stmt.where(ShopProduct.category_id == category_id)
    return list((await session.scalars(stmt.order_by(ShopProduct.sort_order, ShopProduct.id))).all())


async def get_product(session, product_id: int):
    return await session.scalar(select(ShopProduct).where(ShopProduct.id == product_id))


def shop_main_text() -> str:
    return (
        "🛍 Магазин\n\n"
        "Выберите товар или категорию из списка ниже 👇"
    )


def category_text(category: ShopCategory, count: int) -> str:
    description = getattr(category, "description", None) or "Не установлено"
    return (
        f"🏷 Категория: {category.emoji} {category.name}\n\n"
        "📝 Описание:\n"
        f"{description}\n\n"
        "📦 Содержимое категории:\n"
        f"├ Тарифы и услуги — {count}\n"
        "└ Подкатегории — 0\n\n"
        "Выберите товар:"
    )


def product_text(product: ShopProduct, provider_type: str | None = None) -> str:
    provider = "Автоматическая выдача Proxyline" if provider_type == "proxyline" else "Выдача через поставщика"
    return (
        f"📦 › {product.name}\n\n"
        f"{product.description or 'Описание пока не добавлено.'}\n\n"
        f"Цена: {money(product.price, product.currency)}\n"
        f"├ ID товара Admaker — {product.admaker_product_id}\n"
        f"└ Получение — {provider}"
    )


def shop_main_keyboard(categories) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in categories:
        kb.button(text=f"{row.emoji} › {row.name}", callback_data=f"buyer:shopcat:{row.id}")
    kb.button(text="🧾 › Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def products_keyboard(products, category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in products:
        kb.button(text=f"📦 › {row.name} — {money(row.price, row.currency)}", callback_data=f"buyer:shopproduct:{row.id}")
    kb.button(text="⬅️ › К категориям", callback_data="buyer:shop")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def product_keyboard(product: ShopProduct, shop_username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    url = product.buy_url
    if not url and shop_username:
        url = f"https://t.me/{shop_username.lstrip('@')}"
    if url:
        kb.button(text="🛒 › Купить в Admaker Shop", url=url)
    kb.button(text="⬅️ › Назад к товарам", callback_data=f"buyer:shopcat:{product.category_id or 0}")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


async def process_admin_shop_command(session, text: str) -> str | None:
    parts = text.split(maxsplit=3)
    cmd = parts[0].lower()
    if cmd == "/shop_sync":
        count = await sync_products_from_orders(session)
        return f"✅ Каталог синхронизирован. Добавлено товаров: {count}."
    if cmd == "/shop_categories":
        rows = await list_categories(session)
        return "📚 Категории\n\n" + ("\n".join(f"{x.id}. {x.emoji} {x.name}" for x in rows) or "Категорий нет")
    if cmd == "/shop_add_category":
        if len(parts) < 2:
            return "Формат: /shop_add_category Название"
        name = text.split(maxsplit=1)[1].strip()
        if await session.scalar(select(ShopCategory).where(ShopCategory.name == name)):
            return "Такая категория уже существует."
        session.add(ShopCategory(name=name, emoji="📦", is_active=True))
        await session.commit()
        return f"✅ Категория «{name}» добавлена."
    if cmd == "/shop_set_product":
        if len(parts) < 4:
            return "Формат: /shop_set_product ADMAKER_ID CATEGORY_ID Название"
        try:
            admaker_id=int(parts[1]); category_id=int(parts[2])
        except ValueError:
            return "ADMAKER_ID и CATEGORY_ID должны быть числами."
        name=parts[3].strip()
        row=await session.scalar(select(ShopProduct).where(ShopProduct.admaker_product_id==admaker_id))
        if row is None:
            row=ShopProduct(admaker_product_id=admaker_id, category_id=category_id, name=name, is_active=True)
            session.add(row)
        else:
            row.category_id=category_id; row.name=name; row.is_active=True
        await session.commit()
        return f"✅ Товар {admaker_id} сохранён в каталоге."
    if cmd == "/shop_set_price":
        if len(parts) < 3:
            return "Формат: /shop_set_price ADMAKER_ID PRICE [CURRENCY]"
        try:
            admaker_id=int(parts[1]); price=Decimal(parts[2])
        except (ValueError, InvalidOperation):
            return "Некорректный ID или цена."
        currency=parts[3].strip().upper() if len(parts)>3 else "RUB"
        row=await session.scalar(select(ShopProduct).where(ShopProduct.admaker_product_id==admaker_id))
        if not row:
            return "Товар не найден. Сначала /shop_sync или /shop_set_product."
        row.price=price; row.currency=currency
        await session.commit()
        return "✅ Цена обновлена."
    if cmd == "/shop_toggle":
        if len(parts)<2:
            return "Формат: /shop_toggle ADMAKER_ID"
        try: admaker_id=int(parts[1])
        except ValueError: return "ID должен быть числом."
        row=await session.scalar(select(ShopProduct).where(ShopProduct.admaker_product_id==admaker_id))
        if not row: return "Товар не найден."
        row.is_active=not row.is_active
        await session.commit()
        return f"✅ Товар {'включён' if row.is_active else 'выключен'}."
    return None
