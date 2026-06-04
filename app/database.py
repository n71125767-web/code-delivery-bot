import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import DATABASE_URL, SUPPLIER_IDS
from app.models import Base, Supplier

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL, echo=False)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Создаёт таблицы.
    Для SQLite мягко добавляет новые колонки в старые таблицы.
    Новые таблицы suppliers и supplier_products создаются автоматически.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        if DATABASE_URL.startswith("sqlite"):
            await _sqlite_migrations(conn)

    await seed_env_suppliers()


async def _sqlite_migrations(conn) -> None:
    orders_columns_result = await conn.execute(text("PRAGMA table_info(orders)"))
    orders_columns = {row[1] for row in orders_columns_result.fetchall()}

    order_migrations = {
        "business_connection_id": "ALTER TABLE orders ADD COLUMN business_connection_id VARCHAR",
        "buyer_chat_id": "ALTER TABLE orders ADD COLUMN buyer_chat_id BIGINT",
    }

    for column, sql in order_migrations.items():
        if column not in orders_columns:
            try:
                await conn.execute(text(sql))
                logger.info("Migration applied: %s", sql)
            except Exception as exc:
                logger.warning("Migration skipped: %s; error=%s", sql, exc)

    req_columns_result = await conn.execute(text("PRAGMA table_info(supplier_requests)"))
    req_columns = {row[1] for row in req_columns_result.fetchall()}

    req_migrations = {
        "supplier_message_id": "ALTER TABLE supplier_requests ADD COLUMN supplier_message_id BIGINT",
    }

    for column, sql in req_migrations.items():
        if column not in req_columns:
            try:
                await conn.execute(text(sql))
                logger.info("Migration applied: %s", sql)
            except Exception as exc:
                logger.warning("Migration skipped: %s; error=%s", sql, exc)


async def seed_env_suppliers() -> None:
    """
    Старые SUPPLIER_IDS из Render Environment автоматически добавляются в базу,
    чтобы после обновления бот не потерял текущих поставщиков.
    """
    if not SUPPLIER_IDS:
        return

    from sqlalchemy import select

    async with SessionLocal() as session:
        for supplier_id in SUPPLIER_IDS:
            result = await session.execute(
                select(Supplier).where(Supplier.telegram_id == supplier_id)
            )
            exists = result.scalars().first()
            if not exists:
                session.add(Supplier(telegram_id=supplier_id, name=f"supplier_{supplier_id}", is_active=True))
        await session.commit()


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
