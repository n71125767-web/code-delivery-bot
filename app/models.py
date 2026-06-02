from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    operation_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)

    customer_telegram_id: Mapped[int] = mapped_column(BigInteger)
    customer_username: Mapped[str | None] = mapped_column(String, nullable=True)

    product_id: Mapped[int] = mapped_column(BigInteger)
    product_name: Mapped[str] = mapped_column(String)

    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)

    service_name: Mapped[str | None] = mapped_column(String, nullable=True)

    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_code: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="waiting_service")

    raw_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SupplierRequest(Base):
    __tablename__ = "supplier_requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    supplier_telegram_id: Mapped[int] = mapped_column(BigInteger)

    request_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="sent")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)