from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any

from aiogram import Bot
from sqlalchemy import select

from app.config import (
    WALLET_PAYMENT_ADDRESS,
    WALLET_PAYMENT_CURRENCY,
    WALLET_PAYMENT_ENABLED,
    WALLET_WEBHOOK_SECRET,
)
from app.database import SessionLocal
from app.extended_v37 import get_active_promo_discount
from app.cryptopay_service import PaymentConfigurationError, PaymentValidationError, deliver_purchase
from app.models import DigitalPurchase, ProductSnapshot, ShopProduct, WalletPayment


def verify_wallet_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    if not WALLET_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(WALLET_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


async def create_wallet_payment(
    buyer_id: int,
    buyer_username: str | None,
    product_id: int,
) -> tuple[DigitalPurchase, WalletPayment]:
    if not WALLET_PAYMENT_ENABLED:
        raise PaymentConfigurationError("Оплата на кошелёк не включена. Задайте WALLET_PAYMENT_ENABLED=1.")
    if not WALLET_PAYMENT_ADDRESS:
        raise PaymentConfigurationError("Адрес кошелька не настроен. Задайте WALLET_PAYMENT_ADDRESS.")

    async with SessionLocal() as session:
        product = await session.get(ShopProduct, product_id)
        if product is None or product.is_deleted or not product.is_active:
            raise PaymentValidationError("Товар не найден или скрыт.")
        if not product.payment_enabled:
            raise PaymentValidationError("Оплата этого товара временно выключена.")
        if product.price is None or _decimal(product.price) <= 0:
            raise PaymentValidationError("У товара не настроена корректная цена.")

        amount = _decimal(product.price)
        currency = (product.currency or WALLET_PAYMENT_CURRENCY or "USDT").upper()
        promo_code, final_amount, discount = await get_active_promo_discount(session, buyer_id, product.id, amount, currency)
        memo = f"MCS-{secrets.token_hex(4).upper()}"
        purchase = DigitalPurchase(
            buyer_id=buyer_id,
            buyer_username=buyer_username,
            product_id=product.id,
            amount=final_amount,
            currency=currency,
            status="pending_wallet",
            idempotency_key=f"wallet:{buyer_id}:{product.id}:{secrets.token_hex(16)}",
            active_key=f"wallet:{buyer_id}:{product.id}:{memo}",
            fulfillment_type=product.fulfillment_type or ("stock" if product.product_type == "quantity" else "digital"),
            provider_key=product.provider_key,
            promo_code=promo_code,
            discount_amount=discount,
        )
        session.add(purchase)
        await session.flush()
        snapshot = ProductSnapshot(
            purchase_id=purchase.id,
            product_name=product.name,
            product_type=product.product_type,
            description=product.description,
            content_type=product.content_type,
            content_text=product.content_text,
            content_file_id=product.content_file_id,
            amount=final_amount,
            currency=currency,
            fulfillment_type=purchase.fulfillment_type,
            provider_key=product.provider_key,
        )
        session.add(snapshot)
        wallet_payment = WalletPayment(
            purchase_id=purchase.id,
            buyer_id=buyer_id,
            product_id=product.id,
            address=WALLET_PAYMENT_ADDRESS,
            memo=memo,
            amount=final_amount,
            currency=currency,
            status="pending",
        )
        session.add(wallet_payment)
        await session.commit()
        await session.refresh(purchase)
        await session.refresh(wallet_payment)
        return purchase, wallet_payment


async def mark_wallet_payment_paid(
    bot: Bot,
    payment_id: int,
    *,
    tx_hash: str | None = None,
    source: str = "webhook",
) -> tuple[bool, str]:
    async with SessionLocal() as session:
        payment = await session.get(WalletPayment, payment_id)
        if not payment:
            return False, "Платёж не найден."
        purchase = await session.get(DigitalPurchase, payment.purchase_id)
        if not purchase:
            return False, "Покупка не найдена."
        if payment.status == "paid" and purchase.status == "delivered":
            return True, "Платёж уже подтверждён и товар выдан."
        payment.status = "paid"
        payment.tx_hash = tx_hash or payment.tx_hash
        payment.provider_payload = json.dumps({"source": source}, ensure_ascii=False)
        payment.paid_at = datetime.utcnow()
        payment.updated_at = datetime.utcnow()
        purchase.status = "paid"
        purchase.paid_at = datetime.utcnow()
        purchase.updated_at = datetime.utcnow()
        await session.commit()

    delivered = await deliver_purchase(bot, purchase.id)
    return delivered, "Оплата подтверждена, товар выдан." if delivered else "Оплата подтверждена, выдача требует проверки."


async def process_wallet_webhook(bot: Bot, raw_body: bytes, signature: str | None) -> tuple[int, str]:
    if not WALLET_PAYMENT_ENABLED:
        return 503, "wallet disabled"
    if WALLET_WEBHOOK_SECRET and not verify_wallet_webhook_signature(raw_body, signature):
        return 401, "bad signature"
    try:
        data = json.loads(raw_body.decode("utf-8") or "{}")
        payment_id = int(data.get("payment_id") or 0)
        tx_hash = data.get("tx_hash") or data.get("hash")
        status = str(data.get("status") or "paid").lower()
    except Exception:
        return 400, "bad payload"
    if status != "paid":
        return 200, "ignored"
    ok, text = await mark_wallet_payment_paid(bot, payment_id, tx_hash=tx_hash, source="webhook")
    return (200 if ok else 202), text
