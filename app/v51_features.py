from __future__ import annotations

import json
from decimal import Decimal
from typing import Iterable

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, or_
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
    text = f"{amount:.2f}"
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
        lines = [f"🧾 Мои заказы", f"Страница {page + 1}/{max_page + 1}", ""]
        for row in rows:
            p = products.get(row.product_id)
            created = row.created_at.strftime("%d.%m.%Y %H:%M") if row.created_at else "—"
            paid = row.paid_at.strftime("%d.%m.%Y %H:%M") if row.paid_at else "—"
            qty = int(getattr(row, "quantity", 1) or 1)
            payment = payment_map.get(row.id)
            lines.extend([
                f"#{row.id} · {labels.get(row.status, row.status)}",
                f"📦 {_safe_name(p.name if p else None)}",
                f"🔢 {qty} шт. · 💵 {_money(row.amount, row.currency)}",
                f"🕐 Создан: {created}",
                f"✅ Оплачен: {paid}",
            ])
            if payment and payment.invoice_url and row.status in {"creating_invoice", "pending_payment"}:
                lines.append("💳 Счёт ещё можно открыть кнопкой заказа.")
            lines.append("— — —")
        if lines[-1] == "— — —":
            lines.pop()
        text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    for row in rows:
        p = products.get(row.product_id)
        kb.button(text=f"🔎 Заказ #{row.id} · {_safe_name(p.name if p else None, 'Товар')}", callback_data=f"buyer:order:{row.id}")
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"buyer:orders_page:{page - 1}")
    if page < max_page:
        kb.button(text="➡️ Вперёд", callback_data=f"buyer:orders_page:{page + 1}")
    kb.button(text="🏠 Главная", callback_data="buyer:panel")
    kb.adjust(1)
    return text, kb.as_markup()


async def hard_delete_product(session: AsyncSession, product_id: int) -> bool:
    product = await session.get(ShopProduct, product_id)
    if not product:
        return False

    providers = list((await session.scalars(select(ProductProvider).where(ProductProvider.internal_key == product.internal_key))).all())
    for row in providers:
        await session.delete(row)

    carts = list((await session.scalars(select(CartItem).where(CartItem.product_id == product_id))).all())
    for row in carts:
        await session.delete(row)

    # Сохраняем историю покупок, но отвязываем её от удаляемого товара и складской позиции.
    # В V52 product_id у digital_purchases переводится в nullable миграцией.
    purchases = list((await session.scalars(select(DigitalPurchase).where(DigitalPurchase.product_id == product_id))).all())
    for row in purchases:
        row.product_id = None
        row.stock_item_id = None

    stock = list((await session.scalars(select(ProductStockItem).where(ProductStockItem.product_id == product_id))).all())
    for row in stock:
        await session.delete(row)

    await session.flush()
    await session.delete(product)
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
    kb.adjust(1)
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
    category = await session.get(__import__('app.models', fromlist=['ShopCategory']).ShopCategory, category_id)
    rows = list((await session.scalars(select(ShopProduct).where(ShopProduct.category_id == category_id, ShopProduct.is_deleted.is_(False)).order_by(ShopProduct.sort_order, ShopProduct.id))).all())
    if not category:
        return "Категория не найдена."
    text = category_card_text(category, len(rows))
    if rows:
        text += "\n\nТовары в категории:\n" + "\n".join(f"• #{p.id} — {_safe_name(p.name)} — {_money(p.price, p.currency)}" for p in rows[:30])
    else:
        text += "\n\nВ этой категории пока нет товаров."
    return text


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
    revenue = await session.scalar(select(func.coalesce(func.sum(DigitalPurchase.amount), 0)).where(DigitalPurchase.status.in_(["paid", "delivering", "delivered", "fulfillment_problem"])))
    products = int(await session.scalar(select(func.count(ShopProduct.id)).where(ShopProduct.is_deleted.is_(False))) or 0)
    users = int(await session.scalar(select(func.count(BotUser.telegram_id))) or 0)
    wallets = await session.scalar(select(func.coalesce(func.sum(UserWallet.balance), 0)))
    return (
        "📊 Статистика\n\n"
        f"👥 Пользователей: {users}\n"
        f"📦 Товаров: {products}\n"
        f"🧾 Покупок всего: {purchases}\n"
        f"🎁 Выдано: {delivered}\n"
        f"💵 Оборот: {_money(revenue)}\n"
        f"💼 Балансы пользователей: {_money(wallets)}"
    )


def simple_back_keyboard(callback_data: str = "admin:panel") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=callback_data)
    return kb.as_markup()
