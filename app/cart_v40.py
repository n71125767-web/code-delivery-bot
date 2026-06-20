from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CartItem, ShopProduct
from app.shop import money


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


async def add_to_cart(
    session: AsyncSession, user_id: int, product_id: int, qty: int = 1
) -> CartItem:
    qty = max(1, min(int(qty or 1), 99))
    product = await session.get(ShopProduct, product_id)
    if product is None or product.is_deleted or not product.is_active or not product.payment_enabled:
        raise ValueError("Товар сейчас недоступен")
    item = await session.scalar(
        select(CartItem).where(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id,
        )
    )
    if item is None:
        item = CartItem(user_id=user_id, product_id=product_id, quantity=qty)
        session.add(item)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            item = await session.scalar(
                select(CartItem).where(
                    CartItem.user_id == user_id,
                    CartItem.product_id == product_id,
                )
            )
            if item is None:
                raise
            item.quantity = max(1, min(int(item.quantity or 0) + qty, 99))
    else:
        item.quantity = max(1, min(int(item.quantity or 0) + qty, 99))
    item.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(item)
    return item


async def set_cart_quantity(
    session: AsyncSession, user_id: int, item_id: int, qty: int
) -> bool:
    item = await session.scalar(
        select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user_id)
    )
    if item is None:
        return False
    if qty <= 0:
        await session.delete(item)
    else:
        item.quantity = max(1, min(int(qty), 99))
        item.updated_at = datetime.utcnow()
    await session.commit()
    return True


async def clear_cart(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(CartItem).where(CartItem.user_id == user_id))
    await session.commit()


async def get_cart_rows(session: AsyncSession, user_id: int):
    rows = list(
        (
            await session.scalars(
                select(CartItem)
                .where(CartItem.user_id == user_id)
                .order_by(CartItem.updated_at.desc(), CartItem.id.desc())
            )
        ).all()
    )
    if not rows:
        return []
    products = list(
        (
            await session.scalars(
                select(ShopProduct).where(ShopProduct.id.in_({r.product_id for r in rows}))
            )
        ).all()
    )
    product_map = {p.id: p for p in products}
    return [(item, product_map.get(item.product_id)) for item in rows]


def cart_text(rows) -> str:
    if not rows:
        return (
            "🛒 <b>Корзина</b>\n\n"
            "Пока пусто. Откройте каталог и добавьте товары кнопкой «В корзину»."
        )
    lines = ["🛒 <b>Корзина</b>", ""]
    total_by_currency: dict[str, Decimal] = {}
    for idx, (item, product) in enumerate(rows, start=1):
        if not product:
            lines.append(f"{idx}. Товар удалён из каталога")
            continue
        price = _dec(product.price)
        qty = int(item.quantity or 1)
        line_total = price * Decimal(qty)
        currency = product.currency or "RUB"
        total_by_currency[currency] = total_by_currency.get(currency, Decimal("0")) + line_total
        lines.append(f"{idx}. <b>{product.name}</b>")
        lines.append(
            f"   {qty} шт. × {money(price, currency)} = <b>{money(line_total, currency)}</b>"
        )
    lines.append("")
    if total_by_currency:
        totals = ", ".join(money(amount, cur) for cur, amount in total_by_currency.items())
        lines.append(f"Итого: <b>{totals}</b>")
    lines.append("\nМожно менять количество кнопками + / − или задать своё число.")
    return "\n".join(lines)


def cart_keyboard(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item, product in rows:
        kb.button(text="−", callback_data=f"buyer:cart_dec:{item.id}")
        kb.button(text=f"{int(item.quantity or 1)}", callback_data=f"buyer:cart_custom:{item.id}")
        kb.button(text="+", callback_data=f"buyer:cart_inc:{item.id}")
    if rows:
        kb.button(text="✅ Оформить", callback_data="buyer:cart_checkout")
        kb.button(text="🧹 Очистить", callback_data="buyer:cart_clear")
    kb.button(text="🛍 Каталог", callback_data="buyer:shop")
    kb.button(text="🏠 Главное", callback_data="buyer:panel")
    if rows:
        kb.adjust(*([3] * len(rows)), 2, 2)
    else:
        kb.adjust(1)
    return kb.as_markup()
