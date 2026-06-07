from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from aiocryptopay import AioCryptoPay, Networks
from aiogram import Bot
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.time_utils import utcnow
from app.config import (
    CRYPTO_PAY_ACCEPTED_ASSET_LIST,
    CRYPTO_PAY_ENABLED,
    CRYPTO_PAY_DELIVERY_STALE_SECONDS,
    CRYPTO_PAY_INVOICE_EXPIRES_SECONDS,
    CRYPTO_PAY_NETWORK,
    CRYPTO_PAY_PENDING_LIMIT,
    CRYPTO_PAY_TOKEN,
)
from app.database import SessionLocal
from app.models import (
    CryptoPayment,
    DigitalPurchase,
    PaymentEvent,
    ProductStockItem,
    ProductSnapshot,
    ProductProvider,
    ShopProduct,
)

logger = logging.getLogger(__name__)

CRYPTO_ASSETS = {"USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"}
FIAT_CURRENCIES = {
    "USD",
    "EUR",
    "RUB",
    "BYN",
    "UAH",
    "GBP",
    "CNY",
    "KZT",
    "UZS",
    "GEL",
    "TRY",
    "AMD",
    "THB",
    "INR",
    "BRL",
    "IDR",
    "AZN",
    "AED",
    "PLN",
    "ILS",
}

_client: AioCryptoPay | None = None
_delivery_locks: dict[int, asyncio.Lock] = {}
_checkout_locks: dict[tuple[int, int], asyncio.Lock] = {}


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
            Networks.MAIN_NET if CRYPTO_PAY_NETWORK == "mainnet" else Networks.TEST_NET
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
        "invoice_id",
        "status",
        "amount",
        "asset",
        "fiat",
        "currency_type",
        "payload",
        "bot_invoice_url",
        "mini_app_invoice_url",
        "web_app_invoice_url",
        "created_at",
        "paid_at",
        "paid_asset",
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


def _safe_error(exc: Exception, limit: int = 500) -> str:
    text = f"{type(exc).__name__}: {exc}".replace(CRYPTO_PAY_TOKEN, "***")
    return text[:limit]


async def create_purchase_invoice(
    buyer_id: int,
    buyer_username: str | None,
    product_id: int,
) -> tuple[DigitalPurchase, CryptoPayment]:
    key = (buyer_id, product_id)
    lock = _checkout_locks.setdefault(key, asyncio.Lock())
    try:
        async with lock:
            async with SessionLocal() as session:
                existing_purchase = await session.scalar(
                    select(DigitalPurchase)
                    .where(
                        DigitalPurchase.active_key == f"{buyer_id}:{product_id}",
                        DigitalPurchase.status.in_(
                            ("creating_invoice", "pending_payment")
                        ),
                    )
                    .order_by(DigitalPurchase.id.desc())
                    .limit(1)
                )
                if existing_purchase is not None:
                    existing_payment = await session.scalar(
                        select(CryptoPayment).where(
                            CryptoPayment.purchase_id == existing_purchase.id,
                            CryptoPayment.status == "active",
                        )
                    )
                    if existing_payment is not None:
                        return existing_purchase, existing_payment

                product = await session.get(ShopProduct, product_id)
                if product is None or not product.is_active:
                    raise PaymentValidationError("Товар не найден или скрыт.")
                if not product.payment_enabled:
                    raise PaymentValidationError(
                        "Оплата этого товара временно выключена."
                    )
                if product.price is None or _decimal(product.price) <= 0:
                    raise PaymentValidationError(
                        "У товара не настроена корректная цена."
                    )

                provider = await session.scalar(
                    select(ProductProvider).where(
                        ProductProvider.internal_key == product.internal_key,
                        ProductProvider.enabled.is_(True),
                    )
                )
                fulfillment_type = (
                    provider.provider_type
                    if provider
                    else ("stock" if product.product_type == "quantity" else "digital")
                )
                provider_key = provider.provider_key if provider else None

                if fulfillment_type == "digital" and not (
                    product.content_text or product.content_file_id
                ):
                    raise PaymentValidationError("У товара не настроена выдача.")
                if fulfillment_type == "stock":
                    available_id = await session.scalar(
                        select(ProductStockItem.id)
                        .where(
                            ProductStockItem.product_id == product.id,
                            ProductStockItem.status == "available",
                        )
                        .order_by(ProductStockItem.id)
                        .limit(1)
                    )
                    if available_id is None:
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
                    active_key=f"{buyer_id}:{product.id}",
                    fulfillment_type=fulfillment_type,
                    provider_key=provider_key,
                )
                session.add(purchase)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    existing = await session.scalar(
                        select(DigitalPurchase).where(
                            DigitalPurchase.active_key == f"{buyer_id}:{product_id}"
                        )
                    )
                    payment = (
                        await session.scalar(
                            select(CryptoPayment).where(
                                CryptoPayment.purchase_id == existing.id
                            )
                        )
                        if existing
                        else None
                    )
                    if existing and payment:
                        return existing, payment
                    raise PaymentValidationError(
                        "Счёт уже создаётся. Повторите через несколько секунд."
                    )

                if fulfillment_type == "stock":
                    result = await session.execute(
                        update(ProductStockItem)
                        .where(
                            ProductStockItem.id == available_id,
                            ProductStockItem.status == "available",
                        )
                        .values(status="reserved")
                    )
                    if result.rowcount != 1:
                        await session.rollback()
                        raise PaymentValidationError(
                            "Позицию уже забронировал другой покупатель. Повторите покупку."
                        )
                    purchase.stock_item_id = available_id

                snapshot = ProductSnapshot(
                    purchase_id=purchase.id,
                    product_name=product.name,
                    product_type=product.product_type,
                    description=product.description,
                    content_type=product.content_type,
                    content_text=product.content_text,
                    content_file_id=product.content_file_id,
                    amount=product.price,
                    currency=currency,
                    fulfillment_type=fulfillment_type,
                    provider_key=provider_key,
                )
                session.add(snapshot)
                await session.commit()
                await session.refresh(purchase)

            payload = _payload_for(purchase.id, nonce)
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
                    accepted_assets=CRYPTO_PAY_ACCEPTED_ASSET_LIST,
                )

            try:
                invoice = await crypto_client().create_invoice(**kwargs)
                invoice_data = _invoice_to_dict(invoice)
                invoice_id = int(
                    invoice_data.get("invoice_id") or getattr(invoice, "invoice_id")
                )
                invoice_url = (
                    invoice_data.get("bot_invoice_url")
                    or invoice_data.get("mini_app_invoice_url")
                    or invoice_data.get("web_app_invoice_url")
                    or getattr(invoice, "bot_invoice_url", None)
                )
                if not invoice_url:
                    raise PaymentConfigurationError(
                        "Crypto Pay не вернул ссылку на оплату."
                    )
            except Exception as exc:
                async with SessionLocal() as session:
                    db_purchase = await session.get(DigitalPurchase, purchase.id)
                    if db_purchase:
                        db_purchase.status = "invoice_failed"
                        db_purchase.active_key = None
                        db_purchase.delivery_error = _safe_error(exc)
                        db_purchase.updated_at = utcnow()
                        if db_purchase.stock_item_id:
                            stock = await session.get(
                                ProductStockItem, db_purchase.stock_item_id
                            )
                            if stock and stock.status == "reserved":
                                stock.status = "available"
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
                    raw_response=json.dumps(
                        invoice_data, ensure_ascii=False, default=str
                    ),
                )
                session.add(payment)
                db_purchase.status = "pending_payment"
                db_purchase.updated_at = utcnow()
                await session.commit()
                await session.refresh(payment)
                await session.refresh(db_purchase)
                return db_purchase, payment
    finally:
        if not lock.locked():
            _checkout_locks.pop(key, None)


async def _reserve_stock(session, product_id: int) -> ProductStockItem | None:
    for _ in range(5):
        candidate_id = await session.scalar(
            select(ProductStockItem.id)
            .where(
                ProductStockItem.product_id == product_id,
                ProductStockItem.status == "available",
            )
            .order_by(ProductStockItem.id)
            .limit(1)
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


async def _send_product_content(
    bot: Bot,
    chat_id: int,
    product: ShopProduct,
    stock: ProductStockItem | None,
    snapshot: ProductSnapshot | None = None,
) -> Any:
    if stock is not None:
        content_type = stock.content_type
        text = stock.content_text
        file_id = stock.content_file_id
    elif snapshot is not None:
        content_type = snapshot.content_type
        text = snapshot.content_text
        file_id = snapshot.content_file_id
    else:
        content_type = product.content_type
        text = product.content_text
        file_id = product.content_file_id

    if content_type == "photo" and file_id:
        message = await bot.send_photo(chat_id, file_id, caption=text)
    elif content_type == "video" and file_id:
        message = await bot.send_video(chat_id, file_id, caption=text)
    elif content_type == "document" and file_id:
        message = await bot.send_document(chat_id, file_id, caption=text)
    else:
        message = await bot.send_message(chat_id, text or "Ваш товар готов.")
    return message


async def deliver_purchase(bot: Bot, purchase_id: int) -> bool:
    """Deliver one paid purchase exactly once as far as the external API allows.

    A Telegram send and a database commit cannot be one atomic transaction. If a
    send has started and the process dies, the purchase is moved to
    ``delivery_review_required`` instead of being sent again blindly.
    """
    lock = _delivery_locks.setdefault(purchase_id, asyncio.Lock())
    try:
        async with lock:
            now = utcnow()
            async with SessionLocal() as session:
                claim = await session.execute(
                    update(DigitalPurchase)
                    .where(
                        DigitalPurchase.id == purchase_id,
                        DigitalPurchase.status.in_(("paid", "delivery_failed")),
                    )
                    .values(
                        status="delivering",
                        delivery_started_at=now,
                        delivery_attempts=DigitalPurchase.delivery_attempts + 1,
                        delivery_error=None,
                        updated_at=now,
                    )
                )
                if claim.rowcount != 1:
                    await session.rollback()
                    purchase = await session.get(DigitalPurchase, purchase_id)
                    return bool(purchase and purchase.status == "delivered")
                await session.commit()

                purchase = await session.get(DigitalPurchase, purchase_id)
                if purchase is None:
                    return False
                product = await session.get(ShopProduct, purchase.product_id)
                snapshot = await session.scalar(
                    select(ProductSnapshot).where(
                        ProductSnapshot.purchase_id == purchase_id
                    )
                )
                if product is None:
                    purchase.status = "delivery_failed"
                    purchase.delivery_error = "Product not found"
                    purchase.updated_at = utcnow()
                    await session.commit()
                    return False

            if purchase.fulfillment_type == "proxyline":
                from app.fulfillment_service import fulfill_proxyline

                try:
                    return await fulfill_proxyline(bot, purchase, product)
                except Exception as exc:
                    async with SessionLocal() as session:
                        row = await session.get(DigitalPurchase, purchase_id)
                        row.status = "delivery_failed"
                        row.delivery_error = _safe_error(exc)
                        row.active_key = None
                        row.updated_at = utcnow()
                        await session.commit()
                    logger.exception(
                        "PROXYLINE_FULFILLMENT_FAILED purchase_id=%s", purchase_id
                    )
                    return False
            if purchase.fulfillment_type == "supplier":
                from app.fulfillment_service import fulfill_supplier

                try:
                    return await fulfill_supplier(bot, purchase, product)
                except Exception as exc:
                    async with SessionLocal() as session:
                        row = await session.get(DigitalPurchase, purchase_id)
                        row.status = "delivery_failed"
                        row.delivery_error = _safe_error(exc)
                        row.active_key = None
                        row.updated_at = utcnow()
                        await session.commit()
                    logger.exception(
                        "SUPPLIER_FULFILLMENT_FAILED purchase_id=%s", purchase_id
                    )
                    return False

            stock = None
            if (
                purchase.fulfillment_type == "stock"
                or product.product_type == "quantity"
            ):
                async with SessionLocal() as session:
                    db_purchase = await session.get(DigitalPurchase, purchase_id)
                    if db_purchase.stock_item_id is not None:
                        stock = await session.get(
                            ProductStockItem, db_purchase.stock_item_id
                        )
                    else:
                        stock = await _reserve_stock(session, product.id)
                        if stock is not None:
                            db_purchase = await session.get(
                                DigitalPurchase, purchase_id
                            )
                            db_purchase.stock_item_id = stock.id
                            db_purchase.updated_at = utcnow()
                            await session.commit()
                    if stock is None:
                        db_product = await session.get(ShopProduct, product.id)
                        db_purchase.status = "delivery_failed"
                        db_purchase.delivery_error = "No stock available"
                        db_purchase.updated_at = utcnow()
                        db_product.payment_enabled = False
                        db_product.is_active = False
                        await session.commit()
                        return False

            try:
                message = await _send_product_content(
                    bot, purchase.buyer_id, product, stock, snapshot
                )
            except Exception as exc:
                async with SessionLocal() as session:
                    db_purchase = await session.get(DigitalPurchase, purchase_id)
                    if db_purchase:
                        # The Telegram API may have accepted the message even when the
                        # client observed a transport error. Do not release or resend
                        # one-time stock automatically.
                        db_purchase.status = "delivery_review_required"
                        db_purchase.delivery_error = _safe_error(exc)
                        db_purchase.updated_at = utcnow()
                        await session.commit()
                logger.exception(
                    "DIGITAL_DELIVERY_REVIEW_REQUIRED purchase_id=%s", purchase_id
                )
                return False

            async with SessionLocal() as session:
                db_purchase = await session.get(DigitalPurchase, purchase_id)
                db_product = await session.get(ShopProduct, product.id)
                if db_purchase is None or db_product is None:
                    raise RuntimeError(
                        "Purchase or product disappeared during delivery"
                    )
                if db_purchase.status == "delivered":
                    return True
                db_purchase.status = "delivered"
                db_purchase.delivered_at = utcnow()
                db_purchase.updated_at = utcnow()
                db_purchase.delivery_error = None
                db_purchase.active_key = None
                db_purchase.delivery_message_id = getattr(message, "message_id", None)
                db_product.sales_count = int(db_product.sales_count or 0) + 1
                db_product.revenue_total = _decimal(
                    db_product.revenue_total or 0
                ) + _decimal(db_purchase.amount)
                if stock:
                    db_stock = await session.get(ProductStockItem, stock.id)
                    if db_stock is None:
                        raise RuntimeError("Reserved stock item disappeared")
                    db_stock.status = "delivered"
                    db_stock.delivered_to = db_purchase.buyer_id
                    db_stock.delivered_at = utcnow()
                    remaining = await session.scalar(
                        select(ProductStockItem.id)
                        .where(
                            ProductStockItem.product_id == db_product.id,
                            ProductStockItem.status == "available",
                        )
                        .limit(1)
                    )
                    if remaining is None:
                        db_product.payment_enabled = False
                        db_product.is_active = False
                await session.commit()
            return True
    finally:
        if not lock.locked():
            _delivery_locks.pop(purchase_id, None)


async def _validate_paid_invoice(
    payment: CryptoPayment, invoice_data: dict[str, Any]
) -> None:
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
        if purchase.status in {"delivering", "delivery_review_required"}:
            return False

        payment.status = "paid"
        payment.paid_at = utcnow()
        payment.updated_at = utcnow()
        payment.raw_response = json.dumps(invoice_data, ensure_ascii=False, default=str)
        if purchase.status not in {"delivered", "delivering"}:
            purchase.status = "paid"
            purchase.paid_at = utcnow()
            purchase.updated_at = utcnow()
        await session.commit()

    return await deliver_purchase(bot, payment.purchase_id)


async def process_webhook(
    bot: Bot, raw_body: bytes, signature: str | None
) -> tuple[int, str]:
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
            event.processed_at = utcnow()
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


async def check_purchase_payment(
    bot: Bot,
    purchase_id: int,
    buyer_id: int | None = None,
) -> str:
    async with SessionLocal() as session:
        purchase = await session.get(DigitalPurchase, purchase_id)
        if purchase is None:
            raise PaymentValidationError("Покупка не найдена.")
        if buyer_id is not None and purchase.buyer_id != buyer_id:
            raise PaymentValidationError("Это не ваша покупка.")
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
    status = str(data.get("status", "")).lower()

    if status == "paid":
        await process_paid_invoice(bot, data)
        async with SessionLocal() as session:
            current = await session.get(DigitalPurchase, purchase_id)
        if current and current.status == "delivered":
            return "Оплата подтверждена, товар выдан."
        if current and current.status == "awaiting_supplier":
            return "Оплата подтверждена. Откройте /start и выберите сервис."
        return "Оплата подтверждена, выдача обрабатывается."

    if status in {"expired", "cancelled"}:
        async with SessionLocal() as session:
            purchase = await session.get(DigitalPurchase, purchase_id)
            payment = await session.scalar(
                select(CryptoPayment).where(CryptoPayment.purchase_id == purchase_id)
            )
            if purchase and purchase.status != "delivered":
                purchase.status = status
                purchase.active_key = None
                purchase.updated_at = utcnow()
                if purchase.stock_item_id:
                    stock = await session.get(ProductStockItem, purchase.stock_item_id)
                    if stock and stock.status == "reserved":
                        stock.status = "available"
            if payment and payment.status != "paid":
                payment.status = status
                payment.updated_at = utcnow()
            await session.commit()
        return "Счёт истёк. Создайте новый счёт из карточки товара."

    return "Оплата пока не найдена."


async def recover_pending_payments(bot: Bot) -> int:
    """Recover invoices and safe-to-retry deliveries after a restart."""
    stale_before = utcnow() - timedelta(
        seconds=CRYPTO_PAY_DELIVERY_STALE_SECONDS
    )
    async with SessionLocal() as session:
        # A process may die after claiming delivery. Retrying that send can expose a
        # one-time item twice, so stale ambiguous sends go to manual review.
        await session.execute(
            update(DigitalPurchase)
            .where(
                DigitalPurchase.status == "delivering",
                DigitalPurchase.delivery_started_at.is_not(None),
                DigitalPurchase.delivery_started_at < stale_before,
            )
            .values(
                status="delivery_review_required",
                delivery_error="Delivery interrupted; verify Telegram history before retry",
                updated_at=utcnow(),
            )
        )
        await session.commit()

        payments = list(
            (
                await session.scalars(
                    select(CryptoPayment)
                    .where(CryptoPayment.status.in_(("active", "paid")))
                    .order_by(CryptoPayment.id)
                    .limit(CRYPTO_PAY_PENDING_LIMIT)
                )
            ).all()
        )

    recovered = 0
    for payment in payments:
        try:
            if payment.status == "paid":
                async with SessionLocal() as session:
                    purchase = await session.get(DigitalPurchase, payment.purchase_id)
                    retryable = bool(
                        purchase and purchase.status in {"paid", "delivery_failed"}
                    )
                if retryable and await deliver_purchase(bot, payment.purchase_id):
                    recovered += 1
                continue

            result = await crypto_client().get_invoices(invoice_ids=payment.invoice_id)
            invoice = _extract_invoice(result)
            data = _invoice_to_dict(invoice)
            status = str(data.get("status", "")).lower()
            if status == "paid":
                if await process_paid_invoice(bot, data):
                    recovered += 1
            elif status in {"expired", "cancelled"}:
                async with SessionLocal() as session:
                    db_payment = await session.get(CryptoPayment, payment.id)
                    purchase = await session.get(DigitalPurchase, payment.purchase_id)
                    if db_payment and db_payment.status != "paid":
                        db_payment.status = status
                        db_payment.updated_at = utcnow()
                    if purchase and purchase.status not in {
                        "delivered",
                        "paid",
                        "delivering",
                        "delivery_review_required",
                    }:
                        purchase.status = status
                        purchase.active_key = None
                        purchase.updated_at = utcnow()
                        if purchase.stock_item_id:
                            stock = await session.get(
                                ProductStockItem, purchase.stock_item_id
                            )
                            if stock and stock.status == "reserved":
                                stock.status = "available"
                    await session.commit()
        except Exception:
            logger.exception(
                "PAYMENT_RECOVERY_FAILED invoice_id=%s", payment.invoice_id
            )
    return recovered
