from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, Text, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)

    customer_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    customer_username: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    customer_business_connection_id: Mapped[str | None] = mapped_column(String, nullable=True)

    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String, nullable=True)

    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)

    buyer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_name: Mapped[str | None] = mapped_column(String, nullable=True)

    supplier_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    supplier_username: Mapped[str | None] = mapped_column(String, nullable=True)
    supplier_business_connection_id: Mapped[str | None] = mapped_column(String, nullable=True)

    delivered_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_code: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="waiting_buyer_message", index=True)
    timeout_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    raw_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_paid: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplierRequest(Base):
    __tablename__ = "supplier_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    supplier_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    supplier_username: Mapped[str | None] = mapped_column(String, nullable=True)

    request_type: Mapped[str] = mapped_column(String, default="product")
    status: Mapped[str] = mapped_column(String, default="sent", index=True)

    buyer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    source: Mapped[str] = mapped_column(String)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderAction(Base):
    __tablename__ = "order_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)