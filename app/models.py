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
