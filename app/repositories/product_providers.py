from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ProductProvider, Order


async def get_product_provider(session: AsyncSession, internal_key: int | None) -> ProductProvider | None:
    if internal_key is None:
        return None
    result = await session.execute(select(ProductProvider).where(ProductProvider.internal_key == int(internal_key)))
    return result.scalars().first()


async def bind_product_provider(session: AsyncSession, internal_key: int, provider_type: str, provider_key: str | None = None, product_name: str | None = None) -> ProductProvider:
    provider_type = provider_type.strip().lower()
    if provider_type not in {"proxyline", "supplier"}:
        raise ValueError("provider_type must be proxyline or supplier")
    row = await get_product_provider(session, internal_key)
    if row is None:
        row = ProductProvider(internal_key=int(internal_key))
        session.add(row)
    row.provider_type = provider_type
    row.provider_key = provider_key or ("proxyline" if provider_type == "proxyline" else None)
    row.product_name = product_name or row.product_name
    row.enabled = True
    await session.commit()
    await session.refresh(row)
    return row


async def unbind_product_provider(session: AsyncSession, internal_key: int) -> bool:
    row = await get_product_provider(session, internal_key)
    if row is None:
        return False
    row.enabled = False
    await session.commit()
    return True


async def list_product_providers(session: AsyncSession) -> list[ProductProvider]:
    result = await session.execute(select(ProductProvider).order_by(ProductProvider.internal_key))
    return list(result.scalars().all())


async def list_recent_internal_products(session: AsyncSession, limit: int = 30) -> list[tuple[int, str]]:
    result = await session.execute(
        select(Order.product_id, Order.product_name)
        .where(Order.product_id.is_not(None))
        .order_by(Order.created_at.desc())
        .limit(limit * 5)
    )
    seen = set(); rows=[]
    for product_id, product_name in result.all():
        if int(product_id) in seen:
            continue
        seen.add(int(product_id)); rows.append((int(product_id), product_name or "Товар"))
        if len(rows) >= limit:
            break
    return rows
