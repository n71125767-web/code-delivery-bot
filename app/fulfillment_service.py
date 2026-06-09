from __future__ import annotations
import json
import logging
from datetime import datetime
from decimal import Decimal
from aiogram import Bot
from sqlalchemy import select

from app.config import ADMIN_IDS, PROXYLINE_API_KEY, PROXYLINE_COUPON, PROXYLINE_ENABLED
from app.database import SessionLocal
from app.models import (
    DigitalPurchase,
    Order,
    ProductProvider,
    ShopProduct,
    Supplier,
    SupplierProduct,
)
from app.proxyline import ProxylineError, ProxylineService, format_proxyline_result
from app.proxyline_products import ProxylineProduct, resolve_proxyline_product

logger = logging.getLogger(__name__)


async def notify_admins_simple(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("ADMIN_NOTIFY_FAILED admin_id=%s", admin_id)


async def resolve_fulfillment(product: ShopProduct) -> tuple[str, str | None]:
    """
    Fulfillment is explicit. Product names never control business logic.
    Legacy ProductProvider rows are used only as a compatibility fallback.
    """
    if product.fulfillment_type in {
        "digital", "stock", "proxyline", "supplier", "number"
    }:
        return product.fulfillment_type, product.provider_key

    async with SessionLocal() as session:
        provider = await session.scalar(
            select(ProductProvider).where(
                ProductProvider.internal_key == product.internal_key,
                ProductProvider.enabled.is_(True),
            )
        )
    if provider is None:
        return ("stock" if product.product_type == "quantity" else "digital", None)
    if provider.provider_type == "proxyline":
        return "proxyline", provider.provider_key
    if provider.provider_type == "supplier":
        return "supplier", provider.provider_key
    return ("stock" if product.product_type == "quantity" else "digital", None)


def _proxy_cfg(
    product: ShopProduct, provider_key: str | None
) -> ProxylineProduct | None:
    if provider_key:
        try:
            raw = json.loads(provider_key)
            if isinstance(raw, dict):
                return ProxylineProduct(
                    country=str(raw.get("country", "ru")).lower(),
                    period=int(raw.get("period", 30)),
                    count=max(1, int(raw.get("count", raw.get("quantity", 1)))),
                    ip_version=int(raw.get("ip_version", 4)),
                    proxy_type=str(
                        raw.get("type", raw.get("proxy_type", "dedicated"))
                    ).lower(),
                    coupon=raw.get("coupon"),
                )
        except Exception:
            logger.warning("INVALID_PROXY_PROVIDER_KEY product_id=%s", product.id)
    return None


async def fulfill_proxyline(
    bot: Bot, purchase: DigitalPurchase, product: ShopProduct
) -> bool:
    if not PROXYLINE_ENABLED or not PROXYLINE_API_KEY:
        raise ProxylineError("Proxyline API is not configured")
    cfg = _proxy_cfg(product, purchase.provider_key)
    if cfg is None:
        raise ProxylineError("Proxyline product parameters are missing")
    if PROXYLINE_COUPON and not cfg.coupon:
        from dataclasses import replace

        cfg = replace(cfg, coupon=PROXYLINE_COUPON)
    service = ProxylineService(PROXYLINE_API_KEY)
    available = await service.ips_count(cfg)
    if available < cfg.count:
        raise ProxylineError(
            f"Not enough proxies: available={available}, required={cfg.count}"
        )
    payload = await service.buy_proxy(cfg)
    proxy_text = format_proxyline_result(payload)
    message = await bot.send_message(
        purchase.buyer_id,
        "✅ Ваш прокси готов\n\n" + proxy_text + "\n\nСохраните данные подключения.",
    )
    async with SessionLocal() as session:
        row = await session.get(DigitalPurchase, purchase.id)
        db_product = await session.get(ShopProduct, product.id)
        row.status = "delivered"
        row.delivered_at = datetime.utcnow()
        row.delivery_message_id = message.message_id
        row.delivery_error = None
        row.active_key = None
        row.updated_at = datetime.utcnow()
        db_product.sales_count = int(db_product.sales_count or 0) + 1
        db_product.revenue_total = Decimal(
            str(db_product.revenue_total or 0)
        ) + Decimal(str(row.amount))
        await session.commit()
    await notify_admins_simple(bot, f"✅ Proxyline purchase #{purchase.id} delivered")
    return True


async def fulfill_supplier(
    bot: Bot, purchase: DigitalPurchase, product: ShopProduct
) -> bool:
    async with SessionLocal() as session:
        current = await session.get(DigitalPurchase, purchase.id)
        if current.legacy_order_id:
            return True
        operation_id = 9_000_000_000 + purchase.id
        order = Order(
            operation_id=operation_id,
            external_id=f"digital:{purchase.id}",
            customer_telegram_id=purchase.buyer_id,
            buyer_chat_id=purchase.buyer_id,
            customer_username=purchase.buyer_username,
            product_id=product.internal_key,
            product_name=product.name,
            amount=purchase.amount,
            currency=purchase.currency,
            status="waiting_service",
            paid_at=purchase.paid_at or datetime.utcnow(),
            raw_message=f"Crypto Pay purchase #{purchase.id}",
        )
        session.add(order)
        await session.flush()
        if purchase.provider_key and purchase.provider_key.isdigit():
            supplier_id = int(purchase.provider_key)
            supplier = await session.get(Supplier, supplier_id)
            if supplier is None:
                supplier = await session.scalar(
                    select(Supplier).where(Supplier.telegram_id == supplier_id)
                )
            if supplier is not None:
                mapping = await session.scalar(
                    select(SupplierProduct).where(
                        SupplierProduct.supplier_telegram_id == supplier.telegram_id,
                        SupplierProduct.product_key == str(product.internal_key),
                    )
                )
                if mapping is None:
                    session.add(
                        SupplierProduct(
                            supplier_telegram_id=supplier.telegram_id,
                            product_key=str(product.internal_key),
                        )
                    )
        current.legacy_order_id = order.id
        current.status = "awaiting_supplier"
        current.active_key = None
        current.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(order)
    try:
        await bot.send_message(
            purchase.buyer_id,
            "✅ Оплата подтверждена.\n\nНажмите /start и выберите сервис для получения номера.",
        )
    except Exception as exc:
        async with SessionLocal() as session:
            row = await session.get(DigitalPurchase, purchase.id)
            row.delivery_error = f"Buyer notification failed: {exc}"[:500]
            await session.commit()
    await notify_admins_simple(
        bot,
        f"📱 Paid supplier order #{operation_id} created for purchase #{purchase.id}",
    )
    return True


async def sync_purchase_from_order(
    order_id: int, success: bool, error: str | None = None
) -> None:
    async with SessionLocal() as session:
        purchase = await session.scalar(
            select(DigitalPurchase).where(DigitalPurchase.legacy_order_id == order_id)
        )
        if purchase is None:
            return
        purchase.status = "delivered" if success else "fulfillment_problem"
        purchase.delivered_at = datetime.utcnow() if success else purchase.delivered_at
        purchase.delivery_error = (
            None if success else (error or "Supplier fulfillment problem")
        )
        purchase.active_key = None
        purchase.updated_at = datetime.utcnow()
        await session.commit()
