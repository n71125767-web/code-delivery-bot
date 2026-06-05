from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, Text, ForeignKey, Numeric, Boolean, UniqueConstraint, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    operation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)

    customer_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    buyer_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    customer_username: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    business_connection_id: Mapped[str | None] = mapped_column(String, nullable=True)

    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)

    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)

    service_name: Mapped[str | None] = mapped_column(String, nullable=True)

    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_code: Mapped[str | None] = mapped_column(String, nullable=True)

    # waiting_service -> waiting_supplier_number -> number_sent_to_customer
    # -> waiting_supplier_code -> code_sent_to_customer -> confirmed/problem
    status: Mapped[str] = mapped_column(String, default="waiting_service", index=True)

    raw_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplierRequest(Base):
    __tablename__ = "supplier_requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    supplier_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    request_type: Mapped[str] = mapped_column(String)  # number / code
    status: Mapped[str] = mapped_column(String, default="sent", index=True)
    supplier_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, default="supplier")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplierProduct(Base):
    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_telegram_id", "product_key", name="uq_supplier_product_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_key: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ServiceOption(Base):
    __tablename__ = "service_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    emoji: Mapped[str | None] = mapped_column(String, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ServiceList(Base):
    __tablename__ = "service_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ServiceListItem(Base):
    __tablename__ = "service_list_items"
    __table_args__ = (
        UniqueConstraint("list_name", "service_name", name="uq_list_service"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_name: Mapped[str] = mapped_column(String, index=True)
    service_name: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TextTemplate(Base):
    __tablename__ = "text_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cooldown(Base):
    __tablename__ = "cooldowns"
    __table_args__ = (
        UniqueConstraint("user_id", "action", name="uq_cooldown_user_action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    last_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)



class ActionEvent(Base):
    __tablename__ = "action_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)



class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BugReport(Base):
    __tablename__ = "bug_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    reporter_username: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductProvider(Base):
    __tablename__ = "product_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    admaker_product_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_type: Mapped[str] = mapped_column(String(30), default="supplier", index=True)
    provider_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ShopCategory(Base):
    __tablename__ = "shop_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    emoji: Mapped[str] = mapped_column(String(20), default="📦")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("shop_categories.id"), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ShopProduct(Base):
    __tablename__ = "shop_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    admaker_product_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("shop_categories.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    buy_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_type: Mapped[str] = mapped_column(String(20), default="static", index=True)
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    payment_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    payment_systems: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    revenue_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductStockItem(Base):
    __tablename__ = "product_stock_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("shop_products.id"), index=True)
    content_type: Mapped[str] = mapped_column(String(30), default="text")
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    delivered_to: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CatalogDisplaySettings(Base):
    __tablename__ = "catalog_display_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    columns_count: Mapped[int] = mapped_column(Integer, default=1)
    sort_mode: Mapped[str] = mapped_column(String(30), default="position")
    search_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
