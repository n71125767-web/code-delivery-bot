from datetime import datetime
from sqlalchemy import (
    BigInteger,
    String,
    DateTime,
    Text,
    ForeignKey,
    Numeric,
    Boolean,
    UniqueConstraint,
    Integer,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    operation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)

    customer_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    buyer_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    customer_username: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    business_connection_id: Mapped[str | None] = mapped_column(String, nullable=True)

    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)

    amount: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
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
        UniqueConstraint(
            "supplier_telegram_id", "product_key", name="uq_supplier_product_key"
        ),
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
    reporter_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    reporter_username: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductProvider(Base):
    __tablename__ = "product_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    internal_key: Mapped[int] = mapped_column(
        "internal_key", BigInteger, unique=True, index=True
    )
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_type: Mapped[str] = mapped_column(
        String(30), default="supplier", index=True
    )
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
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("shop_categories.id"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ShopProduct(Base):
    __tablename__ = "shop_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    internal_key: Mapped[int] = mapped_column(
        "internal_key", BigInteger, unique=True, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("shop_categories.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    buy_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_type: Mapped[str] = mapped_column(String(20), default="static", index=True)
    fulfillment_type: Mapped[str] = mapped_column(
        String(30), default="digital", index=True
    )
    provider_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_price: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    payment_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    payment_systems: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    revenue_total: Mapped[float] = mapped_column(Numeric(24, 8), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ProductStockItem(Base):
    __tablename__ = "product_stock_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("shop_products.id"), index=True)
    content_type: Mapped[str] = mapped_column(String(30), default="text")
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    delivered_to: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    reserved_purchase_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CatalogDisplaySettings(Base):
    __tablename__ = "catalog_display_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    columns_count: Mapped[int] = mapped_column(Integer, default=1)
    sort_mode: Mapped[str] = mapped_column(String(30), default="position")
    search_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DigitalPurchase(Base):
    __tablename__ = "digital_purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    buyer_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("shop_products.id"), index=True)
    stock_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_stock_items.id"),
        nullable=True,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivery_started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0)
    delivery_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    active_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True, unique=True, index=True
    )
    fulfillment_type: Mapped[str] = mapped_column(
        String(30), default="digital", index=True
    )
    provider_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    promo_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    discount_amount: Mapped[float] = mapped_column(Numeric(24, 8), default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    legacy_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    refund_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True, index=True
    )
    refund_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CryptoPayment(Base):
    __tablename__ = "crypto_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("digital_purchases.id"),
        unique=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), default="cryptopay")
    invoice_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    invoice_url: Mapped[str] = mapped_column(String(1000))
    amount: Mapped[float] = mapped_column(Numeric(24, 8))
    currency_type: Mapped[str] = mapped_column(String(20))
    asset: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fiat: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    payload: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    request_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(50), index=True)
    resource_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("digital_purchases.id"),
        unique=True,
        index=True,
    )
    product_name: Mapped[str] = mapped_column(String(255))
    product_type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(10))
    fulfillment_type: Mapped[str] = mapped_column(String(30), default="digital")
    provider_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("shop_products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BotUser(Base):
    __tablename__ = "bot_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    text: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    media_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConversationState(Base):
    __tablename__ = "conversation_states"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketplaceApplication(Base):
    __tablename__ = "marketplace_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    applicant_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    category_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    moderator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("shop_products.id"), nullable=True, index=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    discount_type: Mapped[str] = mapped_column(String(20), default="percent")
    value: Mapped[float] = mapped_column(Numeric(24, 8), default=0)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("shop_products.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_id", "purchase_id", name="uq_promo_purchase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("digital_purchases.id"), index=True)
    discount_amount: Mapped[float] = mapped_column(Numeric(24, 8), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CooldownSetting(Base):
    __tablename__ = "cooldown_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CustomerTrophy(Base):
    __tablename__ = "customer_trophies"
    __table_args__ = (
        UniqueConstraint("user_id", "trophy_key", name="uq_customer_trophy"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    trophy_key: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    awarded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InternalRewardEvent(Base):
    __tablename__ = "internal_reward_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WalletPayment(Base):
    __tablename__ = "wallet_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("digital_purchases.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("shop_products.id"), index=True)
    address: Mapped[str] = mapped_column(String(500))
    memo: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    tx_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ManualPage(Base):
    __tablename__ = "manual_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserWallet(Base):
    __tablename__ = "user_wallets"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance: Mapped[float] = mapped_column(Numeric(24, 8), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WalletLedger(Base):
    __tablename__ = "wallet_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[float] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplierWithdrawal(Base):
    __tablename__ = "supplier_withdrawals"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[float] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    payout_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payout_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
