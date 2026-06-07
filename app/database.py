import logging
from sqlalchemy import text, select, inspect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import DATABASE_URL, SUPPLIER_IDS, SERVICE_OPTIONS, ADMIN_IDS
from app.models import (
    Base,
    Supplier,
    ServiceOption,
    TextTemplate,
    AdminUser,
    CatalogDisplaySettings,
)

logger = logging.getLogger(__name__)

engine = create_async_engine(DATABASE_URL, echo=False)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        if DATABASE_URL.startswith("sqlite"):
            await _sqlite_migrations(conn)
        await _critical_schema_migrations(conn)

    await seed_env_suppliers()
    await seed_env_admins()
    await seed_services()
    await seed_text_templates()
    await seed_catalog_display_settings()


async def _critical_schema_migrations(conn) -> None:
    """Idempotent additive migrations required by the current release."""

    def columns(sync_conn, table_name: str) -> set[str]:
        inspector = inspect(sync_conn)
        if table_name not in inspector.get_table_names():
            return set()
        return {column["name"] for column in inspector.get_columns(table_name)}

    dialect = conn.dialect.name
    timestamp = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
    additions = {
        "digital_purchases": {
            "delivery_started_at": f"{timestamp}",
            "delivery_attempts": "INTEGER DEFAULT 0 NOT NULL",
            "delivery_message_id": "BIGINT",
            "active_key": "VARCHAR(120)",
            "fulfillment_type": "VARCHAR(30) DEFAULT 'digital' NOT NULL",
            "provider_key": "VARCHAR(500)",
            "legacy_order_id": "INTEGER",
        },
        "product_snapshots": {
            "fulfillment_type": "VARCHAR(30) DEFAULT 'digital' NOT NULL",
            "provider_key": "VARCHAR(500)",
        },
    }
    for table, table_additions in additions.items():
        existing = await conn.run_sync(columns, table)
        if not existing:
            continue
        for column, definition in table_additions.items():
            if column in existing:
                continue
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            try:
                await conn.execute(text(sql))
                logger.info("Migration applied: %s", sql)
            except Exception:
                logger.exception("Critical migration failed: %s", sql)
                raise

    # Cross-process duplicate checkout protection.
    try:
        if dialect == "postgresql":
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_digital_purchases_active_key "
                    "ON digital_purchases(active_key) WHERE active_key IS NOT NULL"
                )
            )
        else:
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_digital_purchases_active_key "
                    "ON digital_purchases(active_key)"
                )
            )
    except Exception:
        logger.exception("Failed to create active checkout index")
        raise


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

    req_columns_result = await conn.execute(
        text("PRAGMA table_info(supplier_requests)")
    )
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

    admin_columns_result = await conn.execute(text("PRAGMA table_info(admin_users)"))
    admin_columns_result.fetchall()
    # Таблица создаётся через Base.metadata.create_all. Этот блок оставлен для будущих SQLite-миграций.

    category_columns_result = await conn.execute(
        text("PRAGMA table_info(shop_categories)")
    )
    category_columns = {row[1] for row in category_columns_result.fetchall()}
    category_migrations = {
        "description": "ALTER TABLE shop_categories ADD COLUMN description TEXT",
        "photo_file_id": "ALTER TABLE shop_categories ADD COLUMN photo_file_id VARCHAR(500)",
        "parent_id": "ALTER TABLE shop_categories ADD COLUMN parent_id INTEGER",
    }
    for column, sql in category_migrations.items():
        if column not in category_columns:
            try:
                await conn.execute(text(sql))
                logger.info("Migration applied: %s", sql)
            except Exception as exc:
                logger.warning("Migration skipped: %s; error=%s", sql, exc)

    product_columns_result = await conn.execute(
        text("PRAGMA table_info(shop_products)")
    )
    product_columns = {row[1] for row in product_columns_result.fetchall()}
    product_migrations = {
        "product_type": "ALTER TABLE shop_products ADD COLUMN product_type VARCHAR(20) DEFAULT 'static'",
        "content_type": "ALTER TABLE shop_products ADD COLUMN content_type VARCHAR(30)",
        "content_text": "ALTER TABLE shop_products ADD COLUMN content_text TEXT",
        "content_file_id": "ALTER TABLE shop_products ADD COLUMN content_file_id VARCHAR(500)",
        "photo_file_id": "ALTER TABLE shop_products ADD COLUMN photo_file_id VARCHAR(500)",
        "video_file_id": "ALTER TABLE shop_products ADD COLUMN video_file_id VARCHAR(500)",
        "note": "ALTER TABLE shop_products ADD COLUMN note TEXT",
        "old_price": "ALTER TABLE shop_products ADD COLUMN old_price NUMERIC(24,8)",
        "payment_enabled": "ALTER TABLE shop_products ADD COLUMN payment_enabled BOOLEAN DEFAULT 1",
        "payment_systems": "ALTER TABLE shop_products ADD COLUMN payment_systems TEXT",
        "payment_description": "ALTER TABLE shop_products ADD COLUMN payment_description TEXT",
        "views_count": "ALTER TABLE shop_products ADD COLUMN views_count INTEGER DEFAULT 0",
        "sales_count": "ALTER TABLE shop_products ADD COLUMN sales_count INTEGER DEFAULT 0",
        "revenue_total": "ALTER TABLE shop_products ADD COLUMN revenue_total NUMERIC(24,8) DEFAULT 0",
    }
    for column, sql in product_migrations.items():
        if column not in product_columns:
            try:
                await conn.execute(text(sql))
                logger.info("Migration applied: %s", sql)
            except Exception as exc:
                logger.warning("Migration skipped: %s; error=%s", sql, exc)

    bug_columns_result = await conn.execute(text("PRAGMA table_info(bug_reports)"))
    bug_columns_result.fetchall()
    # Таблица создаётся через Base.metadata.create_all. Этот блок оставлен для будущих SQLite-миграций.


async def seed_env_suppliers() -> None:
    if not SUPPLIER_IDS:
        return

    async with SessionLocal() as session:
        for supplier_id in SUPPLIER_IDS:
            result = await session.execute(
                select(Supplier).where(Supplier.telegram_id == supplier_id)
            )
            exists = result.scalars().first()
            if not exists:
                session.add(
                    Supplier(
                        telegram_id=supplier_id,
                        name=f"supplier_{supplier_id}",
                        is_active=True,
                    )
                )
        await session.commit()


async def seed_env_admins() -> None:
    if not ADMIN_IDS:
        return

    async with SessionLocal() as session:
        for admin_id in ADMIN_IDS:
            result = await session.execute(
                select(AdminUser).where(AdminUser.telegram_id == admin_id)
            )
            exists = result.scalars().first()
            if not exists:
                session.add(
                    AdminUser(
                        telegram_id=admin_id,
                        name=f"admin_{admin_id}",
                        is_active=True,
                        added_by=admin_id,
                    )
                )
            else:
                exists.is_active = True
        await session.commit()


async def seed_services() -> None:
    if not SERVICE_OPTIONS:
        return

    async with SessionLocal() as session:
        for service in SERVICE_OPTIONS:
            result = await session.execute(
                select(ServiceOption).where(ServiceOption.name == service)
            )
            exists = result.scalars().first()
            if not exists:
                session.add(ServiceOption(name=service, emoji=None, is_active=True))
        await session.commit()


async def seed_text_templates() -> None:
    defaults = {
        "thank_you": "Спасибо за покупку!",
        "service_accepted": "OK. Сервис принят. Ожидайте номер.",
        "service_select": "Выберите сервис кнопкой ниже или напишите название из списка.",
        "order_not_found": "Заказ не найден.\n\nЕсли вы уже оплатили, напишите админу.",
        "contact_forbidden": "Нельзя отправлять контакты, username, ссылки или номера для связи.\n\nНапишите только название сервиса или выберите кнопку ниже.",
        "number_sent_supplier": "OK. Номер отправлен покупателю.",
        "code_sent_supplier": "OK. Код отправлен покупателю.",
        "welcome_start": "Здравствуйте. Чтобы открыть меню и связать заказы, нажмите или отправьте команду /start.",
        "bug_report_hint": "Опишите проблему так: /bug что случилось, на каком шаге, номер заказа если есть.",
        "proxy_shop_enabled": "1",
        "proxy_shop_countries": "ru,us,de",
        "proxy_shop_periods": "30,90,180",
        "proxy_shop_type": "dedicated",
        "proxy_shop_count": "1",
        "proxy_shop_ip_version": "4",
    }

    async with SessionLocal() as session:
        for key, value in defaults.items():
            result = await session.execute(
                select(TextTemplate).where(TextTemplate.key == key)
            )
            exists = result.scalars().first()
            if not exists:
                session.add(TextTemplate(key=key, value=value))
        await session.commit()


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def seed_catalog_display_settings() -> None:
    async with SessionLocal() as session:
        exists = await session.scalar(select(CatalogDisplaySettings).limit(1))
        if not exists:
            session.add(
                CatalogDisplaySettings(
                    columns_count=1, sort_mode="position", search_enabled=True
                )
            )
            await session.commit()
