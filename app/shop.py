from __future__ import annotations

import asyncio

from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.models import ShopCategory, ShopProduct, Order, ProductProvider
from app.config import PROXY_PACKAGE_PRODUCT_IDS


SHOP_SYNC_LOCK = asyncio.Lock()


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
    """
    Идемпотентно получает системную категорию.

    Сначала ищет именно категорию «Все товары». Если параллельная сессия
    успела создать её после SELECT, IntegrityError обрабатывается через
    rollback и повторное чтение.
    """
    row = await session.scalar(
        select(ShopCategory).where(ShopCategory.name == "Все товары")
    )
    if row is not None:
        return row

    row = ShopCategory(
        name="Все товары",
        emoji="🛍",
        sort_order=0,
        is_active=True,
    )
    session.add(row)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        row = await session.scalar(
            select(ShopCategory).where(ShopCategory.name == "Все товары")
        )
        if row is None:
            raise
        return row

    await session.refresh(row)
    return row



async def sync_products_from_orders(session) -> int:
    """
    Явная синхронизация каталога с заказами Admaker.

    Lock защищает от одновременного запуска внутри одного процесса Render.
    Уникальные ограничения дополнительно защищают базу.
    """
    async with SHOP_SYNC_LOCK:
        category = await ensure_default_category(session)

        rows = (await session.execute(
            select(
                Order.product_id,
                Order.product_name,
                func.max(Order.amount),
                func.max(Order.currency),
            )
            .where(Order.product_id.is_not(None))
            .group_by(Order.product_id, Order.product_name)
        )).all()

        created = 0

        for product_id, product_name, amount, currency in rows:
            if product_id is None:
                continue

            product_id = int(product_id)
            exists = await session.scalar(
                select(ShopProduct).where(
                    ShopProduct.internal_key == product_id
                )
            )

            if exists is not None:
                if not exists.name and product_name:
                    exists.name = product_name
                continue

            session.add(
                ShopProduct(
                    internal_key=product_id,
                    category_id=category.id,
                    name=product_name or f"Товар {product_id}",
                    description="Товар из Admaker Shop",
                    price=amount,
                    currency=currency or "RUB",
                    is_active=True,
                )
            )
            created += 1

        try:
            await session.commit()
        except IntegrityError:
            # Параллельная синхронизация могла успеть вставить тот же товар.
            # Откатываем текущую транзакцию: следующая синхронизация уже
            # увидит существующие записи и не продублирует их.
            await session.rollback()
            return 0

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



async def list_proxy_products(session):
    """Активные товары, явно назначенные на Proxyline."""
    stmt = (
        select(ShopProduct)
        .join(
            ProductProvider,
            ProductProvider.internal_key == ShopProduct.internal_key,
        )
        .where(
            ShopProduct.is_active.is_(True),
            ProductProvider.enabled.is_(True),
            ProductProvider.provider_type == "proxyline",
        )
        .order_by(ShopProduct.sort_order, ShopProduct.id)
    )
    return list((await session.scalars(stmt)).all())


async def list_number_products(session):
    rows = await list_products(session)
    providers = list((await session.scalars(
        select(ProductProvider).where(ProductProvider.enabled.is_(True))
    )).all())
    supplier_ids = {row.internal_key for row in providers if row.provider_type == "supplier"}
    proxy_ids = {row.internal_key for row in providers if row.provider_type in {"proxyline", "proxys"}}
    number_words = ("номер", "sms", "phone", "sim")
    proxy_words = ("proxy", "прокси", "mtproxy", "резидент", "rotation", "ротац")
    result = []
    for row in rows:
        name = (row.name or "").lower()
        if row.internal_key in proxy_ids:
            continue
        if any(word in name for word in proxy_words):
            continue
        if row.internal_key in supplier_ids or any(word in name for word in number_words):
            result.append(row)
    return result




PROXY_CATEGORY_DEFINITIONS = {
    "mtproxy": {
        "title": "🧩 MTProxy",
        "keywords": ("mtproxy", "mt proxy", "telegram proxy"),
    },
    "premium": {
        "title": "💎 Премиум прокси",
        "keywords": ("premium", "премиум"),
    },
    "standard": {
        "title": "📦 Стандарт",
        "keywords": ("standard", "стандарт"),
    },
    "residential": {
        "title": "🏠 Резидентские",
        "keywords": ("residential", "резидент", "резидентские"),
    },
}


def proxy_category_title(category_key: str) -> str:
    row = PROXY_CATEGORY_DEFINITIONS.get(category_key)
    return row["title"] if row else "🌐 Прокси"


async def list_proxy_products_by_category(session, category_key: str):
    """
    Возвращает только активные прокси-товары нужной категории.
    Категория определяется по названию товара.
    """
    rows = await list_proxy_products(session)
    definition = PROXY_CATEGORY_DEFINITIONS.get(category_key)
    if not definition:
        return rows

    keywords = definition["keywords"]
    result = []
    for row in rows:
        name = (row.name or "").lower()
        if any(keyword in name for keyword in keywords):
            result.append(row)
    return result


def proxy_categories_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧩 MTProxy", callback_data="buyer:proxycat:mtproxy")
    kb.button(text="💎 Премиум прокси", callback_data="buyer:proxycat:premium")
    kb.button(text="📦 Стандарт", callback_data="buyer:proxycat:standard")
    kb.button(text="🏠 Резидентские", callback_data="buyer:proxycat:residential")
    kb.button(text="⬅️ › Назад", callback_data="buyer:panel", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def proxy_categories_text() -> str:
    return (
        "🌐 Прокси\n\n"
        "Выберите тип прокси:\n\n"
        "├ 🧩 MTProxy\n"
        "├ 💎 Премиум прокси\n"
        "├ 📦 Стандарт\n"
        "└ 🏠 Резидентские"
    )


def special_catalog_text(title: str, count: int = 0) -> str:
    return title



def special_products_keyboard(products, back_callback: str = "buyer:panel") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in products:
        kb.button(
            text=f"📦 › {row.name} — {money(row.price, row.currency)}",
            callback_data=f"buyer:shopproduct:{row.id}",
            style="primary",
        )

    kb.button(
        text="⬅️ › Назад",
        callback_data=back_callback,
        style="danger",
    )
    kb.adjust(1)
    return kb.as_markup()


PROXY_PACKAGE_CATEGORIES = {
    "mtproxy": {
        "title": "🔐 MTProxy",
        "provider": "proxyline",
        "items": [
            ("mt_1m", "🔑 MTProxy [1 мес.] - 3.1 USD"),
            ("mt_3m", "🔑 MTProxy [3 мес.] - 9.3 USD"),
            ("mt_6m", "🔑 MTProxy [6 мес.] - 18.6 USD"),
            ("mt_9m", "🔑 MTProxy [9 мес.] - 27.90 USD"),
            ("mt_12m", "🔑 MTProxy [12 мес.] - 37.20 USD"),
        ],
    },
    "premium": {
        "title": "🏆 PREMIUM",
        "provider": "proxyline",
        "items": [
            ("premium_1m", "🪐 Прокси [1 мес.] - 3.1 USD"),
            ("premium_3m", "🪐 Прокси [3 мес.] - 9.3 USD"),
            ("premium_6m", "🪐 Прокси [6 мес.] - 18.6 USD"),
            ("premium_9m", "🪐 Прокси [9 мес.] - 27.90 USD"),
            ("premium_12m", "🪐 Прокси [12 мес.] - 37.20 USD"),
        ],
    },
    "standard": {
        "title": "💯 STANDART",
        "provider": "proxys",
        "items": [
            ("standard_1m", "🎲 Прокси [1 мес.] - 2 USD"),
            ("standard_2m", "🎲 Прокси [2 мес.] - 2.75 USD"),
            ("standard_3m", "🎲 Прокси [3 мес.] - 4 USD"),
        ],
    },
    "rotation": {
        "title": "🌋 ПРОКСИ С РОТАЦИЕЙ",
        "provider": "proxyline",
        "items": [
            ("rotation_1gb", "🌏 Прокси [1 GB] - 14.75 USD"),
            ("rotation_5gb", "🌏 Прокси [5 GB] - 61.50 USD"),
            ("rotation_15gb", "🌏 Прокси [15 GB] - 129 USD"),
        ],
    },
}


def proxy_main_text() -> str:
    return "🌐 Прокси"


def proxy_main_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key in ("mtproxy", "premium", "standard", "rotation"):
        group = PROXY_PACKAGE_CATEGORIES[key]
        kb.button(text=group["title"], callback_data=f"buyer:proxygroup:{key}")
    kb.button(text="⬅️ Назад", callback_data="buyer:panel", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def proxy_group_text(group_key: str) -> str:
    group = PROXY_PACKAGE_CATEGORIES.get(group_key)
    return group["title"] if group else "🌐 Прокси"


def proxy_group_keyboard(group_key: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    group = PROXY_PACKAGE_CATEGORIES.get(group_key)
    if group:
        for package_key, label in group["items"]:
            kb.button(text=label, callback_data=f"buyer:proxypackage:{group_key}:{package_key}")
    kb.button(text="⬅️ Назад", callback_data="buyer:proxy_catalog", style="danger")
    kb.adjust(1)
    return kb.as_markup()


def get_proxy_package(group_key: str, package_key: str):
    group = PROXY_PACKAGE_CATEGORIES.get(group_key)
    if not group:
        return None
    for key, label in group["items"]:
        if key == package_key:
            return {"key": key, "label": label, "provider": group["provider"], "group": group_key}
    return None


def proxy_package_keyboard(group_key: str, shop_username: str, package_key: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    product_id = PROXY_PACKAGE_PRODUCT_IDS.get(package_key or "")
    if product_id and shop_username:
        kb.button(
            text="✅ Купить",
            url=f"https://t.me/{shop_username.lstrip('@')}?start=product_{product_id}",
            style="success",
        )
    else:
        kb.button(text="⏳ Тариф не настроен", callback_data="buyer:noop")
    kb.button(text="⬅️ Назад", callback_data=f"buyer:proxygroup:{group_key}", style="danger")
    kb.adjust(1)
    return kb.as_markup()



async def list_general_products(session, category_id: int | None = None):
    rows = await list_products(session, category_id)
    providers = list((await session.scalars(
        select(ProductProvider).where(ProductProvider.enabled.is_(True))
    )).all())
    proxy_ids = {row.internal_key for row in providers if row.provider_type in {"proxyline", "proxys"}}
    proxy_words = ("proxy", "прокси", "mtproxy", "резидент", "rotation", "ротац")
    return [
        row for row in rows
        if row.internal_key not in proxy_ids
        and not any(word in (row.name or "").lower() for word in proxy_words)
    ]

def shop_main_text() -> str:
    return (
        "🛍 Добро пожаловать в MCS Shop\n\n"
        "Выберите нужный раздел на панели ниже."
    )



def category_text(category: ShopCategory, count: int = 0) -> str:
    description = getattr(category, "description", None)
    if description:
        return f"{category.emoji} {category.name}\n\n{description}"
    return f"{category.emoji} {category.name}"



def product_text(product: ShopProduct, provider_type: str | None = None) -> str:
    description = product.description or ""
    return f"{product.name}\n\n{description}\n\n{money(product.price, product.currency)}".strip()



def shop_main_keyboard(categories) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in categories:
        kb.button(text=f"{row.emoji} › {row.name}", callback_data=f"buyer:shopcat:{row.id}")
    kb.button(text="🧾 › Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 › Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def products_keyboard(
    products,
    category_id: int,
    columns_count: int = 1,
    page: int = 0,
    page_size: int = 12,
) -> InlineKeyboardMarkup:
    from app.catalog_runtime_v29 import paginate

    page_rows, page, pages = paginate(products, page, page_size)
    kb = InlineKeyboardBuilder()

    for row in page_rows:
        kb.button(
            text=f"📦 {row.name} — {money(row.price, row.currency)}",
            callback_data=f"buyer:shopproduct:{row.id}",
        )

    if not page_rows:
        kb.button(text="Товаров пока нет", callback_data="buyer:noop")

    columns = max(1, min(int(columns_count or 1), 3))
    kb.adjust(columns)

    if pages > 1:
        if page > 0:
            kb.button(
                text="⬅️ Назад",
                callback_data=f"buyer:shopcat:{category_id}:{page - 1}",
                style="danger",
            )
        kb.button(text=f"{page + 1}/{pages}", callback_data="buyer:noop")
        if page + 1 < pages:
            kb.button(
                text="Вперёд ➡️",
                callback_data=f"buyer:shopcat:{category_id}:{page + 1}",
                style="success",
            )

    kb.button(text="⬅️ К категориям", callback_data="buyer:shop", style="danger")
    return kb.as_markup()





def product_keyboard(product: ShopProduct, shop_username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if product.is_active and product.payment_enabled:
        kb.button(
            text="✅ Купить",
            callback_data=f"buyer:buy:{product.id}",
            style="success",
        )
    else:
        kb.button(text="⏸ Покупка недоступна", callback_data="buyer:noop")
    kb.button(
        text="⬅️ Назад",
        callback_data=f"buyer:shopcat:{product.category_id or 0}",
        style="danger",
    )
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
        row=await session.scalar(select(ShopProduct).where(ShopProduct.internal_key==admaker_id))
        if row is None:
            row=ShopProduct(internal_key=admaker_id, category_id=category_id, name=name, is_active=True)
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
        row=await session.scalar(select(ShopProduct).where(ShopProduct.internal_key==admaker_id))
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
        row=await session.scalar(select(ShopProduct).where(ShopProduct.internal_key==admaker_id))
        if not row: return "Товар не найден."
        row.is_active=not row.is_active
        await session.commit()
        return f"✅ Товар {'включён' if row.is_active else 'выключен'}."
    return None
