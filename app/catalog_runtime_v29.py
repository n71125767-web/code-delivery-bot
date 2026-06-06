from __future__ import annotations

from sqlalchemy import or_, select

from app.models import ShopProduct


def sort_products(products, mode: str):
    rows = list(products)
    if mode == "name":
        return sorted(rows, key=lambda p: ((p.name or "").lower(), p.id))
    if mode == "price":
        return sorted(rows, key=lambda p: (float(p.price or 0), p.id))
    if mode == "newest":
        return sorted(rows, key=lambda p: p.id, reverse=True)
    return sorted(rows, key=lambda p: (p.sort_order, p.id))


def paginate(items, page: int, page_size: int = 12):
    rows = list(items)
    page_size = max(1, min(int(page_size), 30))
    pages = max(1, (len(rows) + page_size - 1) // page_size)
    page = max(0, min(int(page), pages - 1))
    start = page * page_size
    return rows[start:start + page_size], page, pages


async def search_visible_products(session, query: str, limit: int = 30):
    clean = (query or "").strip()
    if not clean:
        return []
    pattern = f"%{clean}%"
    rows = list((await session.scalars(
        select(ShopProduct)
        .where(
            ShopProduct.is_active.is_(True),
            ShopProduct.payment_enabled.is_(True),
            or_(
                ShopProduct.name.ilike(pattern),
                ShopProduct.description.ilike(pattern),
            ),
        )
        .order_by(ShopProduct.sort_order, ShopProduct.id)
        .limit(limit)
    )).all())
    return rows
