from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from aiocryptopay import AioCryptoPay, Networks
from aiogram import Bot
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import (
    CRYPTO_PAY_ACCEPTED_ASSETS,
    CRYPTO_PAY_ENABLED,
    CRYPTO_PAY_INVOICE_EXPIRES_SECONDS,
    CRYPTO_PAY_NETWORK,
    CRYPTO_PAY_PENDING_LIMIT,
    CRYPTO_PAY_TOKEN,
)
from app.database import SessionLocal
from app.models import (
    AdminAuditLog,
    CryptoPayment,
    DigitalPurchase,
    PaymentEvent,
    ProductStockItem,
    ShopProduct,
)

logger = logging.getLogger(__name__)

CRYPTO_ASSETS = {"USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"}
FIAT_CURRENCIES = {
    "USD", "EUR", "RUB", "BYN", "UAH", "GBP", "CNY", "KZT",
    "UZS", "GEL", "TRY", "AMD", "THB", "INR", "BRL", "IDR",
    "AZN", "AED", "PLN", "ILS",
}

_client: AioCryptoPay | None = None
_delivery_locks: dict[int, asyncio.Lock] = {}


class PaymentConfigurationError(RuntimeError):
    pass


class PaymentValidationError(RuntimeError):
    pass


def crypto_client() -> AioCryptoPay:
    global _client
    if not CRYPTO_PAY_ENABLED:
        raise PaymentConfigurationError(
            "Crypto Pay не настроен. Добавьте CRYPTO_PAY_TOKEN в Render Environment."
        )
    if _client is None:
        network = (
            Networks.MAIN_NET
            if CRYPTO_PAY_NETWORK == "mainnet"
            else Networks.TEST_NET
        )
        _client = AioCryptoPay(token=CRYPTO_PAY_TOKEN, network=network)
    return _client


async def close_crypto_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    if not CRYPTO_PAY_TOKEN or not signature:
        return False
    secret = hashlib.sha256(CRYPTO_PAY_TOKEN.encode("utf-8")).digest()
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _invoice_to_dict(invoice: Any) -> dict[str, Any]:
    if invoice is None:
        return {}
    if isinstance(invoice, dict):
        return invoice
    for method_name in ("model_dump", "dict"):
        method = getattr(invoice, method_name, None)
        if callable(method):
            try:
                return method()
            except Exception:
                pass
    result = {}
    for key in (
        "invoice_id", "status", "amount", "asset", "fiat", "currency_type",
        "payload", "bot_invoice_url", "mini_app_invoice_url",
        "web_app_invoice_url", "created_at", "paid_at", "paid_asset",
        "paid_amount",
    ):
        value = getattr(invoice, key, None)
        if value is not None:
            result[key] = value
    return result


def _extract_invoice(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    items = getattr(value, "items", None)
    if isinstance(items, list):
        return items[0] if items else None
    return value


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _payload_for(purchase_id: int, nonce: str) -> str:
    return json.dumps(
        {"purchase_id": purchase_id, "nonce": nonce, "version": 1},
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def create_purchase_invoice(
    buyer_id: int,
    buyer_username: str | None,
    product_id: int,
) -> tuple[DigitalPurchase, CryptoPayment]:
    async with SessionLocal() as session:
        product = await session.get(ShopProduct, product_id)
        if product is None or not product.is_active:
            raise PaymentValidationError("Товар не найден или скрыт.")
        if not product.payment_enabled:
            raise PaymentValidationError("Оплата этого товара временно выключена.")
        if product.price is None or _decimal(product.price) <= 0:
            raise PaymentValidationError("У товара не настроена корректная цена.")
        if product.product_type == "static":
            if not (product.content_text or product.content_file_id):
                raise PaymentValidationError("У товара не настроена выдача.")
        elif product.product_type == "quantity":
            available = await session.scalar(
                select(ProductStockItem.id).where(
                    ProductStockItem.product_id == product.id,
                    ProductStockItem.status == "available",
                ).limit(1)
            )
            if available is None:
                product.payment_enabled = False
                product.is_active = False
                await session.commit()
                raise PaymentValidationError("Товар закончился.")

        currency = (product.currency or "").upper()
        if currency not in CRYPTO_ASSETS and currency not in FIAT_CURRENCIES:
            raise PaymentValidationError(
                f"Валюта {currency} не поддерживается Crypto Pay."
            )

        nonce = secrets.token_hex(16)
        purchase = DigitalPurchase(
            buyer_id=buyer_id,
            buyer_username=buyer_username,
            product_id=product.id,
            amount=product.price,
            currency=currency,
            status="creating_invoice",
            idempotency_key=f"buy:{buyer_id}:{product.id}:{nonce}",
        )
        session.add(purchase)
        await session.commit()
        await session.refresh(purchase)

    payload = _payload_for(purchase.id, nonce)
    client = crypto_client()
    kwargs: dict[str, Any] = {
        "amount": float(_decimal(purchase.amount)),
        "description": f"MCS Shop — {product.name}"[:1024],
        "payload": payload,
        "expires_in": CRYPTO_PAY_INVOICE_EXPIRES_SECONDS,
        "allow_anonymous": False,
    }
    if currency in CRYPTO_ASSETS:
        kwargs.update(currency_type="crypto", asset=currency)
    else:
        kwargs.update(
            currency_type="fiat",
            fiat=currency,
            accepted_assets=CRYPTO_PAY_ACCEPTED_ASSETS,
        )

    try:
        invoice = await client.create_invoice(**kwargs)
        invoice_data = _invoice_to_dict(invoice)
        invoice_id = int(invoice_data.get("invoice_id") or getattr(invoice, "invoice_id"))
        invoice_url = (
            invoice_data.get("bot_invoice_url")
            or invoice_data.get("mini_app_invoice_url")
            or invoice_data.get("web_app_invoice_url")
            or getattr(invoice, "bot_invoice_url", None)
        )
        if not invoice_url:
            raise PaymentConfigurationError("Crypto Pay не вернул ссылку на оплату.")
    except Exception as exc:
        async with SessionLocal() as session:
            db_purchase = await session.get(DigitalPurchase, purchase.id)
            if db_purchase:
                db_purchase.status = "invoice_failed"
                db_purchase.delivery_error = str(exc)[:1000]
                db_purchase.updated_at = datetime.utcnow()
                await session.commit()
        raise

    async with SessionLocal() as session:
        db_purchase = await session.get(DigitalPurchase, purchase.id)
        payment = CryptoPayment(
            purchase_id=purchase.id,
            invoice_id=invoice_id,
            invoice_url=invoice_url,
            amount=purchase.amount,
            currency_type="crypto" if currency in CRYPTO_ASSETS else "fiat",
            asset=currency if currency in CRYPTO_ASSETS else None,
            fiat=currency if currency in FIAT_CURRENCIES else None,
            status="active",
            payload=payload,
            raw_response=json.dumps(invoice_data, ensure_ascii=False, default=str),
        )
        session.add(payment)
        db_purchase.status = "pending_payment"
        db_purchase.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(payment)
        await session.refresh(db_purchase)
        return db_purchase, payment


async def _reserve_stock(session, product_id: int) -> ProductStockItem | None:
    for _ in range(5):
        candidate_id = await session.scalar(
            select(ProductStockItem.id).where(
                ProductStockItem.product_id == product_id,
                ProductStockItem.status == "available",
            ).order_by(ProductStockItem.id).limit(1)
        )
        if candidate_id is None:
            return None
        result = await session.execute(
            update(ProductStockItem)
            .where(
                ProductStockItem.id == candidate_id,
                ProductStockItem.status == "available",
            )
            .values(status="reserved")
        )
        if result.rowcount == 1:
            await session.commit()
            return await session.get(ProductStockItem, candidate_id)
        await session.rollback()
    return None


async def _send_product_content(bot: Bot, chat_id: int, product: ShopProduct, stock: ProductStockItem | None) -> bool:
    content_type = stock.content_type if stock else product.content_type
    text = stock.content_text if stock else product.content_text
    file_id = stock.content_file_id if stock else product.content_file_id

    if content_type == "photo" and file_id:
        await bot.send_photo(chat_id, file_id, caption=text)
    elif content_type == "video" and file_id:
        await bot.send_video(chat_id, file_id, caption=text)
    elif content_type == "document" and file_id:
        await bot.send_document(chat_id, file_id, caption=text)
    else:
        await bot.send_message(chat_id, text or "Ваш товар готов.")
    return True


async def deliver_purchase(bot: Bot, purchase_id: int) -> bool:
    lock = _delivery_locks.setdefault(purchase_id, asyncio.Lock())
    async with lock:
        async with SessionLocal() as session:
            claim = await session.execute(
                update(DigitalPurchase)
                .where(
                    DigitalPurchase.id == purchase_id,
                    DigitalPurchase.status.in_(("paid", "delivery_failed")),
                )
                .values(status="delivering", updated_at=datetime.utcnow())
            )
            if claim.rowcount != 1:
                await session.rollback()
                purchase = await session.get(DigitalPurchase, purchase_id)
                return bool(purchase and purchase.status == "delivered")
            await session.commit()

            purchase = await session.get(DigitalPurchase, purchase_id)
            product = await session.get(ShopProduct, purchase.product_id)
            if product is None:
                purchase.status = "delivery_failed"
                purchase.delivery_error = "Product not found"
                await session.commit()
                return False

        stock = None
        if product.product_type == "quantity":
            async with SessionLocal() as session:
                stock = await _reserve_stock(session, product.id)
                if stock is None:
                    purchase = await session.get(DigitalPurchase, purchase_id)
                    product = await session.get(ShopProduct, product.id)
                    purchase.status = "delivery_failed"
                    purchase.delivery_error = "No stock available"
                    product.payment_enabled = False
                    product.is_active = False
                    await session.commit()
                    return False

        try:
            await _send_product_content(bot, purchase.buyer_id, product, stock)
        except Exception as exc:
            async with SessionLocal() as session:
                db_purchase = await session.get(DigitalPurchase, purchase_id)
                db_purchase.status = "delivery_failed"
                db_purchase.delivery_error = str(exc)[:1000]
                db_purchase.updated_at = datetime.utcnow()
                if stock:
                    db_stock = await session.get(ProductStockItem, stock.id)
                    if db_stock and db_stock.status == "reserved":
                        db_stock.status = "available"
                await session.commit()
            logger.exception("DIGITAL_DELIVERY_FAILED purchase_id=%s", purchase_id)
            return False

        async with SessionLocal() as session:
            db_purchase = await session.get(DigitalPurchase, purchase_id)
            db_product = await session.get(ShopProduct, product.id)
            db_purchase.status = "delivered"
            db_purchase.delivered_at = datetime.utcnow()
            db_purchase.updated_at = datetime.utcnow()
            db_purchase.delivery_error = None
            db_product.sales_count = int(db_product.sales_count or 0) + 1
            db_product.revenue_total = _decimal(db_product.revenue_total or 0) + _decimal(db_purchase.amount)
            if stock:
                db_stock = await session.get(ProductStockItem, stock.id)
                db_stock.status = "delivered"
                db_stock.delivered_to = db_purchase.buyer_id
                db_stock.delivered_at = datetime.utcnow()
                db_purchase.stock_item_id = db_stock.id
                remaining = await session.scalar(
                    select(ProductStockItem.id).where(
                        ProductStockItem.product_id == db_product.id,
                        ProductStockItem.status == "available",
                    ).limit(1)
                )
                if remaining is None:
                    db_product.payment_enabled = False
                    db_product.is_active = False
            await session.commit()
        return True


async def _validate_paid_invoice(payment: CryptoPayment, invoice_data: dict[str, Any]) -> None:
    if str(invoice_data.get("status", "")).lower() != "paid":
        raise PaymentValidationError("Invoice is not paid")
    if int(invoice_data.get("invoice_id")) != int(payment.invoice_id):
        raise PaymentValidationError("Invoice ID mismatch")
    if invoice_data.get("payload") != payment.payload:
        raise PaymentValidationError("Payload mismatch")

    expected = _decimal(payment.amount)
    actual = _decimal(invoice_data.get("amount"))
    if actual != expected:
        raise PaymentValidationError(f"Amount mismatch: {actual} != {expected}")

    if payment.currency_type == "crypto":
        if (invoice_data.get("asset") or "").upper() != (payment.asset or "").upper():
            raise PaymentValidationError("Asset mismatch")
    else:
        if (invoice_data.get("fiat") or "").upper() != (payment.fiat or "").upper():
            raise PaymentValidationError("Fiat mismatch")


async def process_paid_invoice(bot: Bot, invoice_data: dict[str, Any]) -> bool:
    invoice_id = int(invoice_data.get("invoice_id"))
    async with SessionLocal() as session:
        payment = await session.scalar(
            select(CryptoPayment).where(CryptoPayment.invoice_id == invoice_id)
        )
        if payment is None:
            raise PaymentValidationError("Unknown invoice")
        await _validate_paid_invoice(payment, invoice_data)

        purchase = await session.get(DigitalPurchase, payment.purchase_id)
        if purchase.status == "delivered":
            return True
        if payment.status == "paid" and purchase.status in {"paid", "delivering"}:
            return False

        payment.status = "paid"
        payment.paid_at = datetime.utcnow()
        payment.updated_at = datetime.utcnow()
        payment.raw_response = json.dumps(invoice_data, ensure_ascii=False, default=str)
        if purchase.status not in {"delivered", "delivering"}:
            purchase.status = "paid"
            purchase.paid_at = datetime.utcnow()
            purchase.updated_at = datetime.utcnow()
        await session.commit()

    return await deliver_purchase(bot, payment.purchase_id)


async def process_webhook(bot: Bot, raw_body: bytes, signature: str | None) -> tuple[int, str]:
    request_hash = hashlib.sha256(raw_body).hexdigest()
    if not verify_webhook_signature(raw_body, signature):
        return 401, "invalid signature"

    try:
        update_data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return 400, "invalid json"

    event_type = str(update_data.get("update_type") or "")
    invoice_data = update_data.get("payload") or {}
    invoice_id = invoice_data.get("invoice_id")

    async with SessionLocal() as session:
        existing = await session.scalar(
            select(PaymentEvent).where(PaymentEvent.request_hash == request_hash)
        )
        if existing:
            return 200, "duplicate"

        event = PaymentEvent(
            invoice_id=int(invoice_id) if invoice_id is not None else None,
            event_type=event_type,
            request_hash=request_hash,
            raw_body=raw_body.decode("utf-8", errors="replace"),
        )
        session.add(event)
        try:
            await session.commit()
            await session.refresh(event)
        except IntegrityError:
            await session.rollback()
            return 200, "duplicate"

    try:
        if event_type != "invoice_paid":
            raise PaymentValidationError(f"Unsupported event: {event_type}")
        await process_paid_invoice(bot, invoice_data)
        async with SessionLocal() as session:
            event = await session.scalar(
                select(PaymentEvent).where(PaymentEvent.request_hash == request_hash)
            )
            event.processed = True
            event.processed_at = datetime.utcnow()
            await session.commit()
        return 200, "ok"
    except Exception as exc:
        logger.exception("CRYPTOPAY_WEBHOOK_PROCESS_FAILED invoice_id=%s", invoice_id)
        async with SessionLocal() as session:
            event = await session.scalar(
                select(PaymentEvent).where(PaymentEvent.request_hash == request_hash)
            )
            if event:
                event.error_text = str(exc)[:2000]
                await session.commit()
        return 500, "processing failed"


async def check_purchase_payment(bot: Bot, purchase_id: int) -> str:
    async with SessionLocal() as session:
        purchase = await session.get(DigitalPurchase, purchase_id)
        if purchase is None:
            raise PaymentValidationError("Покупка не найдена.")
        if purchase.status == "delivered":
            return "Товар уже выдан."
        payment = await session.scalar(
            select(CryptoPayment).where(CryptoPayment.purchase_id == purchase_id)
        )
        if payment is None:
            raise PaymentValidationError("Счёт не найден.")
        invoice_id = payment.invoice_id

    result = await crypto_client().get_invoices(invoice_ids=invoice_id)
    invoice = _extract_invoice(result)
    data = _invoice_to_dict(invoice)
    if str(data.get("status", "")).lower() == "paid":
        delivered = await process_paid_invoice(bot, data)
        return "Оплата подтверждена, товар выдан." if delivered else "Оплата подтверждена, выдача обрабатывается."
    return "Оплата пока не найдена."


async def recover_pending_payments(bot: Bot) -> int:
    async with SessionLocal() as session:
        payments = list((await session.scalars(
            select(CryptoPayment)
            .where(CryptoPayment.status == "active")
            .order_by(CryptoPayment.id)
            .limit(CRYPTO_PAY_PENDING_LIMIT)
        )).all())

    recovered = 0
    for payment in payments:
        try:
            result = await crypto_client().get_invoices(invoice_ids=payment.invoice_id)
            invoice = _extract_invoice(result)
            data = _invoice_to_dict(invoice)
            if str(data.get("status", "")).lower() == "paid":
                if await process_paid_invoice(bot, data):
                    recovered += 1
        except Exception:
            logger.exception("PAYMENT_RECOVERY_FAILED invoice_id=%s", payment.invoice_id)
    return recovered
