import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import DATABASE_URL
from app.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL, echo=False)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Создаёт таблицы и мягко добавляет новые колонки в старую SQLite-базу.

    Для разработки самый простой вариант при проблемах со схемой:
    остановить бота -> удалить bot.db -> запустить снова.
    Но эта функция старается не ломать старую базу.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        if DATABASE_URL.startswith("sqlite"):
            columns_result = await conn.execute(text("PRAGMA table_info(orders)"))
            columns = {row[1] for row in columns_result.fetchall()}

            migrations = {
                "business_connection_id": "ALTER TABLE orders ADD COLUMN business_connection_id VARCHAR",
                "buyer_chat_id": "ALTER TABLE orders ADD COLUMN buyer_chat_id BIGINT",
                "supplier_message_id": "ALTER TABLE supplier_requests ADD COLUMN supplier_message_id BIGINT",
            }

            for column, sql in migrations.items():
                target_table = "orders" if column in {"business_connection_id", "buyer_chat_id"} else "supplier_requests"
                if target_table == "supplier_requests":
                    req_columns_result = await conn.execute(text("PRAGMA table_info(supplier_requests)"))
                    req_columns = {row[1] for row in req_columns_result.fetchall()}
                    exists = column in req_columns
                else:
                    exists = column in columns

                if not exists:
                    try:
                        await conn.execute(text(sql))
                        logger.info("Migration applied: %s", sql)
                    except Exception as exc:
                        logger.warning("Migration skipped: %s; error=%s", sql, exc)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
