import logging
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import DATABASE_URL, SUPPLIER_IDS, SERVICE_OPTIONS, ADMIN_IDS
from app.models import Base, Supplier, ServiceOption, TextTemplate, AdminUser

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

    await seed_env_suppliers()
    await seed_env_admins()
    await seed_services()
    await seed_text_templates()


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

    admin_columns_result = await conn.execute(text("PRAGMA table_info(admin_users)"))
    admin_columns = {row[1] for row in admin_columns_result.fetchall()}
    # Таблица создаётся через Base.metadata.create_all. Этот блок оставлен для будущих SQLite-миграций.

    bug_columns_result = await conn.execute(text("PRAGMA table_info(bug_reports)"))
    bug_columns = {row[1] for row in bug_columns_result.fetchall()}
    # Таблица создаётся через Base.metadata.create_all. Этот блок оставлен для будущих SQLite-миграций.


async def seed_env_suppliers() -> None:
    if not SUPPLIER_IDS:
        return

    async with SessionLocal() as session:
        for supplier_id in SUPPLIER_IDS:
            result = await session.execute(select(Supplier).where(Supplier.telegram_id == supplier_id))
            exists = result.scalars().first()
            if not exists:
                session.add(Supplier(telegram_id=supplier_id, name=f"supplier_{supplier_id}", is_active=True))
        await session.commit()


async def seed_env_admins() -> None:
    if not ADMIN_IDS:
        return

    async with SessionLocal() as session:
        for admin_id in ADMIN_IDS:
            result = await session.execute(select(AdminUser).where(AdminUser.telegram_id == admin_id))
            exists = result.scalars().first()
            if not exists:
                session.add(AdminUser(telegram_id=admin_id, name=f"admin_{admin_id}", is_active=True, added_by=admin_id))
            else:
                exists.is_active = True
        await session.commit()


async def seed_services() -> None:
    if not SERVICE_OPTIONS:
        return

    async with SessionLocal() as session:
        for service in SERVICE_OPTIONS:
            result = await session.execute(select(ServiceOption).where(ServiceOption.name == service))
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
    }

    async with SessionLocal() as session:
        for key, value in defaults.items():
            result = await session.execute(select(TextTemplate).where(TextTemplate.key == key))
            exists = result.scalars().first()
            if not exists:
                session.add(TextTemplate(key=key, value=value))
        await session.commit()


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
