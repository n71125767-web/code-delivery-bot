import logging
from sqlalchemy import text, select, inspect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import DATABASE_URL, SERVICE_OPTIONS, ADMIN_IDS, GA_IDS
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

    await seed_env_admins()
    await seed_services()
    await seed_text_templates()
    await seed_catalog_display_settings()
    await migrate_legacy_fulfillment()


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
            "promo_code": "VARCHAR(80)",
            "discount_amount": "NUMERIC(24,8) DEFAULT 0 NOT NULL",
            "quantity": "INTEGER DEFAULT 1 NOT NULL",
            "refund_status": "VARCHAR(30)",
            "refund_reason": "TEXT",
            "refunded_at": f"{timestamp}",
            "updated_at": f"{timestamp} DEFAULT CURRENT_TIMESTAMP NOT NULL",
        },
        "product_snapshots": {
            "fulfillment_type": "VARCHAR(30) DEFAULT 'digital' NOT NULL",
            "provider_key": "VARCHAR(500)",
            "quantity": "INTEGER DEFAULT 1 NOT NULL",
        },
        "shop_products": {
            "fulfillment_type": "VARCHAR(30) DEFAULT 'digital' NOT NULL",
            "provider_key": "VARCHAR(500)",
            "is_deleted": "BOOLEAN DEFAULT FALSE NOT NULL",
            "deleted_at": f"{timestamp}",
            "deleted_by": "BIGINT",
        },
        "product_stock_items": {
            "reserved_at": f"{timestamp}",
            "reserved_purchase_id": "BIGINT",
        },
        "broadcast_jobs": {
            "media_type": "VARCHAR(30)",
            "media_file_id": "VARCHAR(500)",
            "last_user_id": "BIGINT",
            "error_text": "TEXT",
            "started_at": f"{timestamp}",
        },
        "marketplace_applications": {
            "content_preview": "TEXT",
            "reject_reason": "TEXT",
        },
        "wallet_payments": {
            "provider_payload": "TEXT",
        },
        "product_providers": {
            "supplier_payout_amount": "NUMERIC(24,8)",
            "supplier_payout_currency": "VARCHAR(10)",
        },
        "supplier_products": {
            "payout_amount": "NUMERIC(24,8)",
            "payout_currency": "VARCHAR(10)",
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


    # One-time cleanup of the legacy external-store column name.
    if dialect == "postgresql":
        try:
            product_columns = await conn.run_sync(columns, "shop_products")
            if "admaker_product_id" in product_columns and "internal_key" not in product_columns:
                await conn.execute(
                    text(
                        "ALTER TABLE shop_products "
                        "RENAME COLUMN admaker_product_id TO internal_key"
                    )
                )
            provider_columns = await conn.run_sync(columns, "product_providers")
            if "admaker_product_id" in provider_columns and "internal_key" not in provider_columns:
                await conn.execute(
                    text(
                        "ALTER TABLE product_providers "
                        "RENAME COLUMN admaker_product_id TO internal_key"
                    )
                )
        except Exception:
            logger.exception("Legacy internal_key column migration failed")
            raise


    # V52/V60: allow product rows to be physically deleted while keeping history.
    # Historical purchases, marketplace applications, promo codes and wallet payments
    # keep their data; product_id may become NULL after catalog cleanup.
    if dialect == "postgresql":
        nullable_product_refs = (
            "digital_purchases",
            "marketplace_applications",
            "promo_codes",
            "wallet_payments",
            "cart_items",
            "product_stock_items",
        )
        for table_name in nullable_product_refs:
            try:
                table_columns = await conn.run_sync(columns, table_name)
                if "product_id" in table_columns:
                    await conn.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN product_id DROP NOT NULL"))
                    logger.info("Migration applied: %s.product_id DROP NOT NULL", table_name)
            except Exception:
                logger.exception("Failed to make %s.product_id nullable", table_name)
                raise

        # V62: make product FKs tolerant to hard deletion. If an old database was
        # created before nullable models, PostgreSQL constraints can still block
        # DELETE even after ORM cleanup. Recreate those FKs with ON DELETE SET NULL
        # where possible. This block is idempotent and only touches product_id FKs.
        try:
            fk_rows = (await conn.execute(text("""
                SELECT tc.table_name, tc.constraint_name, kcu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND ccu.table_name = 'shop_products'
                  AND ccu.column_name = 'id'
                  AND tc.table_schema = 'public'
            """))).all()
            for table_name, constraint_name, column_name in fk_rows:
                if column_name != "product_id":
                    continue
                safe_table = str(table_name).replace('_', '').isalnum()
                safe_constraint = str(constraint_name).replace('_', '').isalnum()
                if not (safe_table and safe_constraint):
                    continue
                await conn.execute(text(f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}'))
                await conn.execute(text(
                    f'ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} '
                    f'FOREIGN KEY (product_id) REFERENCES shop_products(id) ON DELETE SET NULL'
                ))
                logger.info("Migration applied: %s.%s ON DELETE SET NULL", table_name, column_name)
        except Exception:
            logger.exception("Failed to update shop_products FK constraints")
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


async def seed_env_admins() -> None:
    admin_ids = sorted(set(ADMIN_IDS + GA_IDS))
    if not admin_ids:
        return

    async with SessionLocal() as session:
        for admin_id in admin_ids:
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


async def migrate_legacy_fulfillment() -> None:
    """Backfill explicit fulfillment fields for products from older releases."""
    from app.models import ProductProvider, ShopProduct

    async with SessionLocal() as session:
        products = list((await session.scalars(select(ShopProduct))).all())
        providers = list((await session.scalars(select(ProductProvider))).all())
        provider_map = {row.internal_key: row for row in providers if row.enabled}

        changed = 0
        for product in products:
            provider = provider_map.get(product.internal_key)
            if provider is not None:
                if provider.provider_type in {"proxyline", "proxys"}:
                    product.fulfillment_type = "proxyline"
                    product.provider_key = provider.provider_key
                elif provider.provider_type == "supplier":
                    product.fulfillment_type = "supplier"
                    product.provider_key = provider.provider_key
            elif product.product_type == "quantity":
                product.fulfillment_type = "stock"
            elif not product.fulfillment_type:
                product.fulfillment_type = "digital"
            changed += 1

        if changed:
            await session.commit()
            logger.info("Legacy fulfillment backfill checked products=%s", changed)
