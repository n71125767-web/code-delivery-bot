from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, Text, ForeignKey, Numeric
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
