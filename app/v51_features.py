from __future__ import annotations

import json
from decimal import Decimal
from typing import Iterable

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdminUser,
    BotUser,
    CryptoPayment,
    DigitalPurchase,
    ProductProvider,
    ProductStockItem,
    ShopProduct,
    TextTemplate,
    UserWallet,
    CartItem,
    MarketplaceApplication,
    PromoCode,
    WalletPayment,
)
from app.database import SessionLocal

ORDER_PAGE_SIZE = 3
ADMIN_CAPS = {
    "catalog": "📦 Товары",
    "payments": "💳 Оплата",
    "settings": "⚙️ Настройки",
    "broadcast": "📢 Рассылка",
    "proxy": "🧩 Прокси",
    "stats": "📊 Статистика",
    "admins": "👥 Админы",
    "hidden": "👁 Скрытые",
    "suppliers": "🚚 Поставщики",
}
DEFAULT_ADMIN_CAPS = set(ADMIN_CAPS.keys()) - {"admins"}


def _money(value, currency: str | None = None) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        amount = Decimal("0.00")
    text = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{text} {currency}" if currency else text


def _safe_name(value: str | None, default: str = "Товар") -> str:
    text = (value or default).strip()
    return text if len(text) <= 42 else text[:41] + "…"


async def find_user_id_by_username_or_id(session: AsyncSession, raw: str) -> tuple[int | None, str | None]:
    clean = (raw or "").strip().replace("@", "")
    if not clean:
        return None, "Укажите Telegram ID или username."
    if clean.isdigit():
        return int(clean), None
    user = await session.scalar(
        select(BotUser).where(func.lower(BotUser.username) == clean.lower()).limit(1)
    )
    if not user:
        return None, "Пользователь с таким username ещё не найден. Он должен хотя бы один раз открыть бота."
    return int(user.telegram_id), None


async def buyer_orders_page(user_id: int, username: str | None, page: int = 0):
    async with SessionLocal() as session:
        clean_username = (username or "").replace("@", "").lower()
        stmt = select(DigitalPurchase).where(DigitalPurchase.buyer_id == user_id)
        if clean_username:
            stmt = select(DigitalPurchase).where(
                or_(
                    DigitalPurchase.buyer_id == user_id,
                    func.lower(DigitalPurchase.buyer_username) == clean_username,
                )
            )
        total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        max_page = max(0, (total - 1) // ORDER_PAGE_SIZE) if total else 0
        page = max(0, min(int(page or 0), max_page))
        rows = list((await session.scalars(stmt.order_by(DigitalPurchase.id.desc()).offset(page * ORDER_PAGE_SIZE).limit(ORDER_PAGE_SIZE))).all())
        product_ids = [r.product_id for r in rows]
        products = {}
        if product_ids:
            products = {p.id: p for p in (await session.scalars(select(ShopProduct).where(ShopProduct.id.in_(product_ids)))).all()}
        payment_map = {}
        if rows:
            payment_map = {p.purchase_id: p for p in (await session.scalars(select(CryptoPayment).where(CryptoPayment.purchase_id.in_([r.id for r in rows])))).all()}

    labels = {
        "new": "создан",
        "creating_invoice": "создаётся счёт",
        "pending_payment": "ожидает оплату",
        "paid": "оплачен",
        "delivering": "выдаётся",
        "delivered": "выдан",
        "delivery_failed": "ошибка выдачи",
        "invoice_failed": "ошибка счёта",
        "awaiting_supplier": "у поставщика",
        "fulfillment_problem": "проблема выдачи",
    }
    if not rows:
        text = "🧾 Мои заказы\n\nПока заказов нет."
    else:
        text = f"🧾 Мои заказы\n\nСтраница {page + 1}/{max_page + 1}. Выберите заказ кнопкой ниже."

    kb = InlineKeyboardBuilder()
    for row in rows:
        p = products.get(row.product_id)
        kb.button(text=f"🔎 Заказ #{row.id} · {_safe_name(p.name if p else None, 'Товар')}", callback_data=f"buyer:order:{row.id}")
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"buyer:orders_page:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Вперёд", callback_data=f"buyer:orders_page:{page + 1}")
    kb.button(text="🏠 Главная", callback_data="buyer:panel")
    kb.adjust(2)
    return text, kb.as_markup()


async def hard_delete_product(session: AsyncSession, product_id: int) -> bool:
    """Physically delete product and clean every known FK safely.

    PostgreSQL aborts the whole transaction after a failed statement, so this
    function avoids blind try/except DDL/DML. It discovers FK columns first and
    then either NULLs nullable references or deletes rows that cannot be NULL.
    """
    product = await session.get(ShopProduct, int(product_id))
    if not product:
        return False
    pid = int(product_id)
    internal_key = product.internal_key

    bind = session.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    def safe_ident(value: str) -> str:
        value = str(value)
        if not value.replace("_", "").isalnum():
            raise ValueError("unsafe identifier")
        return value

    if dialect == "postgresql":
        # Provider binding is not an FK to shop_products.id.
        if internal_key is not None:
            await session.execute(text("DELETE FROM product_providers WHERE internal_key = :ikey"), {"ikey": internal_key})

        rows = (await session.execute(text("""
            SELECT tc.table_name, kcu.column_name, cols.is_nullable
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            JOIN information_schema.columns AS cols
              ON cols.table_schema = kcu.table_schema
             AND cols.table_name = kcu.table_name
             AND cols.column_name = kcu.column_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = 'shop_products'
              AND ccu.column_name = 'id'
              AND tc.table_schema = 'public'
        """))).all()

        delete_tables = {
            "cart_items",
            "product_stock_items",
            "product_providers",
            "marketplace_applications",
        }
        for table_name, column_name, is_nullable in rows:
            table = safe_ident(table_name)
            column = safe_ident(column_name)
            if table in delete_tables or str(is_nullable).upper() != "YES":
                await session.execute(text(f"DELETE FROM {table} WHERE {column} = :pid"), {"pid": pid})
            else:
                await session.execute(text(f"UPDATE {table} SET {column} = NULL WHERE {column} = :pid"), {"pid": pid})

        # Legacy direct relations that might not have declared FKs.
        await session.execute(text("DELETE FROM cart_items WHERE product_id = :pid"), {"pid": pid})
        await session.execute(text("DELETE FROM product_stock_items WHERE product_id = :pid"), {"pid": pid})
        await session.execute(text("DELETE FROM marketplace_applications WHERE product_id = :pid"), {"pid": pid})
        await session.execute(text("UPDATE digital_purchases SET product_id = NULL, stock_item_id = NULL WHERE product_id = :pid"), {"pid": pid})
        await session.execute(text("UPDATE promo_codes SET product_id = NULL WHERE product_id = :pid"), {"pid": pid})
        await session.execute(text("UPDATE wallet_payments SET product_id = NULL WHERE product_id = :pid"), {"pid": pid})
    else:
        # SQLite/local fallback. If a table is absent, ignore after rollback and continue.
        statements = [
            ("DELETE FROM product_providers WHERE internal_key = :ikey", {"ikey": internal_key}) if internal_key is not None else None,
            ("DELETE FROM cart_items WHERE product_id = :pid", {"pid": pid}),
            ("DELETE FROM product_stock_items WHERE product_id = :pid", {"pid": pid}),
            ("DELETE FROM marketplace_applications WHERE product_id = :pid", {"pid": pid}),
            ("UPDATE digital_purchases SET product_id = NULL, stock_item_id = NULL WHERE product_id = :pid", {"pid": pid}),
            ("UPDATE promo_codes SET product_id = NULL WHERE product_id = :pid", {"pid": pid}),
            ("UPDATE wallet_payments SET product_id = NULL WHERE product_id = :pid", {"pid": pid}),
        ]
        for item in statements:
            if not item:
                continue
            sql, params = item
            try:
                await session.execute(text(sql), params)
            except Exception:
                await session.rollback()

    await session.execute(text("DELETE FROM shop_products WHERE id = :pid"), {"pid": pid})
    await session.commit()
    return True


async def get_admin_caps(session: AsyncSession, telegram_id: int) -> set[str]:
    if not telegram_id:
        return set()
    row = await session.scalar(select(TextTemplate).where(TextTemplate.key == f"admin_caps:{telegram_id}"))
    if not row or not row.value:
        return set(DEFAULT_ADMIN_CAPS)
    try:
        data = json.loads(row.value)
        if isinstance(data, list):
            return {str(x) for x in data if str(x) in ADMIN_CAPS}
    except Exception:
        pass
    return set(DEFAULT_ADMIN_CAPS)


async def set_admin_caps(session: AsyncSession, telegram_id: int, caps: Iterable[str]) -> None:
    key = f"admin_caps:{telegram_id}"
    value = json.dumps(sorted({c for c in caps if c in ADMIN_CAPS}), ensure_ascii=False)
    row = await session.scalar(select(TextTemplate).where(TextTemplate.key == key))
    if row:
        row.value = value
    else:
        session.add(TextTemplate(key=key, value=value))
    await session.commit()


async def has_admin_capability(user_id: int | None, cap: str, is_owner: bool = False) -> bool:
    if is_owner:
        return True
    if not user_id:
        return False
    async with SessionLocal() as session:
        caps = await get_admin_caps(session, user_id)
    return cap in caps


async def admin_capabilities_text(session: AsyncSession) -> str:
    admins = list((await session.scalars(select(AdminUser).where(AdminUser.is_active.is_(True)).order_by(AdminUser.created_at.desc()))).all())
    lines = ["👥 Права администраторов", "", "Выберите администратора, затем включите или выключите разделы."]
    if not admins:
        lines += ["", "Дополнительных админов пока нет."]
    return "\n".join(lines)


def admin_capabilities_keyboard(admins) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for admin in admins:
        kb.button(text=f"👤 {admin.telegram_id} · {_safe_name(admin.name, 'админ')}", callback_data=f"admin:caps:user:{admin.telegram_id}")
    kb.button(text="➕ Добавить админа", callback_data="admin:add_admin_prompt")
    kb.button(text="⬅️ Назад", callback_data="admin:admins")
    kb.adjust(2)
    return kb.as_markup()


async def admin_capability_user_text(session: AsyncSession, telegram_id: int) -> str:
    admin = await session.scalar(select(AdminUser).where(AdminUser.telegram_id == telegram_id))
    caps = await get_admin_caps(session, telegram_id)
    name = admin.name if admin else "админ"
    lines = [f"👤 Администратор {telegram_id}", f"Имя: {name or '—'}", "", "Доступы:"]
    for key, label in ADMIN_CAPS.items():
        lines.append(f"{'✅' if key in caps else '▫️'} {label}")
    return "\n".join(lines)


async def admin_capability_user_keyboard(session: AsyncSession, telegram_id: int) -> InlineKeyboardMarkup:
    caps = await get_admin_caps(session, telegram_id)
    kb = InlineKeyboardBuilder()
    for key, label in ADMIN_CAPS.items():
        kb.button(text=f"{'✅' if key in caps else '▫️'} {label}", callback_data=f"admin:caps:toggle:{telegram_id}:{key}")
    kb.button(text="⬅️ К списку", callback_data="admin:caps")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


async def category_products_text_admin(session: AsyncSession, category_id: int) -> str:
    from app.catalog_v25 import category_card_text
    from app.models import ShopCategory
    category = await session.get(ShopCategory, category_id)
    rows = list((await session.scalars(select(ShopProduct).where(ShopProduct.category_id == category_id, ShopProduct.is_deleted.is_(False)).order_by(ShopProduct.sort_order, ShopProduct.id))).all())
    if not category:
        return "Категория не найдена."
    return category_card_text(category, len(rows))


async def admin_settings_visual_text() -> str:
    async with SessionLocal() as session:
        main = await session.scalar(select(TextTemplate).where(TextTemplate.key == "main_page_text"))
        faq = await session.scalar(select(TextTemplate).where(TextTemplate.key == "faq_text"))
    return (
        "⚙️ Настройки магазина\n\n"
        "Здесь меняется визуал главной страницы, FAQ, сервисы номеров и отображение каталога.\n\n"
        "🏠 Главная:\n"
        f"{(main.value if main else 'стандартная')[:350]}\n\n"
        "📕 FAQ:\n"
        f"{(faq.value if faq else 'стандартный')[:350]}"
    )


def admin_settings_visual_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Изменить главную", callback_data="admin:edit_main_page")
    kb.button(text="📕 Изменить FAQ", callback_data="admin:edit_faq")
    kb.button(text="📱 Сервисы номеров", callback_data="admin:number_settings")
    kb.button(text="🧩 Вид каталога", callback_data="v25:view_settings")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


async def admin_statistics_visual_text(session: AsyncSession) -> str:
    purchases = int(await session.scalar(select(func.count(DigitalPurchase.id))) or 0)
    delivered = int(await session.scalar(select(func.count(DigitalPurchase.id)).where(DigitalPurchase.status == "delivered")) or 0)
    products = int(await session.scalar(select(func.count(ShopProduct.id)).where(ShopProduct.is_deleted.is_(False))) or 0)
    users = int(await session.scalar(select(func.count(BotUser.telegram_id))) or 0)
    wallets = await session.scalar(select(func.coalesce(func.sum(UserWallet.balance), 0)))
    revenue_rows = (await session.execute(
        select(DigitalPurchase.currency, func.coalesce(func.sum(DigitalPurchase.amount), 0))
        .where(DigitalPurchase.status.in_(["paid", "delivering", "delivered", "fulfillment_problem"]))
        .group_by(DigitalPurchase.currency)
    )).all()
    revenue_text = ", ".join(f"{_money(amount, currency or 'USDT')}" for currency, amount in revenue_rows) or "0"
    return (
        "📊 Статистика\n\n"
        f"👥 Пользователей: {users}\n"
        f"📦 Товаров: {products}\n"
        f"🧾 Покупок: {purchases}\n"
        f"🎁 Выдано: {delivered}\n"
        f"💰 Оборот: {revenue_text}\n"
        f"💼 Балансы: {_money(wallets, 'USDT')}"
    )

def simple_back_keyboard(callback_data: str = "admin:panel") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=callback_data)
    return kb.as_markup()


# ---------------- V63 clean settings visual overrides ----------------
async def admin_settings_visual_text() -> str:
    return "⚙️ Настройки магазина"

def admin_settings_visual_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главная страница", callback_data="admin:edit_main_page")
    kb.button(text="📕 FAQ", callback_data="admin:edit_faq")
    kb.button(text="👥 Админы", callback_data="admin:admins")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(2)
    return kb.as_markup()


# ---------------- V64 audit-clean final overrides ----------------
async def admin_settings_visual_text() -> str:
    return "⚙️ Настройки магазина\n\nВыберите нужный раздел кнопкой ниже."


def admin_settings_visual_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Текст главной", callback_data="admin:edit_main_page")
    kb.button(text="🖼 Фото главной", callback_data="admin:main_photo")
    kb.button(text="🔗 Кнопки главной", callback_data="admin:main_buttons")
    kb.button(text="⌨️ Кнопки клавиатуры", callback_data="admin:reply_buttons")
    kb.button(text="📕 Текст FAQ", callback_data="admin:edit_faq")
    kb.button(text="🖼 Фото FAQ", callback_data="admin:faq_photo")
    kb.button(text="🔗 Кнопки FAQ", callback_data="admin:faq_buttons")
    kb.button(text="🧩 Вид каталога", callback_data="v25:view_settings")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(2)
    return kb.as_markup()
