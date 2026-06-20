from __future__ import annotations
import json
import logging
from datetime import datetime
from decimal import Decimal
from aiogram import Bot
from sqlalchemy import select, update

from app.config import (
    ADMIN_IDS,
    PROXYLINE_API_KEY,
    PROXYLINE_COUPON,
    PROXYLINE_ENABLED,
    PROXYLINE_MTPROXY_MODE,
    PROXYLINE_MTPROXY_API_TYPE,
    PROXYS_API_KEY,
    PROXYS_ENABLED,
)
from app.database import SessionLocal
from app.models import (
    DigitalPurchase,
    Order,
    ProductProvider,
    ProductStockItem,
    ShopProduct,
    Supplier,
    SupplierProduct,
)
from app.proxyline import ProxylineError, ProxylineService, format_mtproxy_result, format_proxyline_result
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
    if provider.provider_type in {"proxyline", "proxys"}:
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
                raw_kind = str(
                    raw.get("category")
                    or raw.get("kind")
                    or raw.get("proxy_kind")
                    or ""
                ).lower()
                proxy_type = str(
                    raw.get("type", raw.get("proxy_type", "dedicated"))
                ).lower()
                # Старые записи V45/V47 могли сохранить type=mtproxy.
                # Публичный Proxyline new-order принимает dedicated/shared, поэтому
                # для покупки через API переводим MTProxy/Telegram-тариф в dedicated
                # или в значение из PROXYLINE_MTPROXY_API_TYPE.
                if raw_kind == "mtproxy" and PROXYLINE_MTPROXY_MODE != "stock":
                    proxy_type = PROXYLINE_MTPROXY_API_TYPE or "dedicated"
                return ProxylineProduct(
                    country=str(raw.get("country", "ru")).lower(),
                    period=int(raw.get("period", 30)),
                    count=max(1, int(raw.get("count", raw.get("quantity", 1)))),
                    ip_version=int(raw.get("ip_version", 4)),
                    proxy_type=proxy_type,
                    coupon=raw.get("coupon"),
                )
        except Exception:
            logger.warning("INVALID_PROXY_PROVIDER_KEY product_id=%s", product.id)
    return None



def _proxy_kind_from_provider_key(provider_key: str | None, product: ShopProduct | None = None) -> str:
    proxy_kind = ""
    try:
        raw_key = json.loads(provider_key or "{}")
        if isinstance(raw_key, dict):
            proxy_kind = str(
                raw_key.get("category")
                or raw_key.get("kind")
                or raw_key.get("proxy_kind")
                or raw_key.get("tariff")
                or ""
            ).lower()
    except Exception:
        proxy_kind = ""
    if not proxy_kind and product is not None and product.note:
        proxy_kind = str(product.note).replace("proxy_autofix:", "").lower()
    return proxy_kind


async def _reserve_mtproxy_stock(product_id: int, purchase_id: int) -> tuple[int, str] | None:
    """Reserve one MTProxy stock line atomically.

    Stock format accepted by the formatter:
    ip:port:secret
    tg://proxy?server=...&port=...&secret=...
    IP: ...\nPort: ...\nSecret: ...
    """
    for _ in range(5):
        async with SessionLocal() as session:
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
                .values(
                    status="reserved",
                    reserved_at=datetime.utcnow(),
                    reserved_purchase_id=purchase_id,
                )
            )
            if result.rowcount == 1:
                stock = await session.get(ProductStockItem, candidate_id)
                await session.commit()
                if stock and stock.content_text:
                    return stock.id, stock.content_text
                return None
            await session.rollback()
    return None


async def _fulfill_mtproxy_stock(bot: Bot, purchase: DigitalPurchase, product: ShopProduct) -> bool:
    reserved = await _reserve_mtproxy_stock(product.id, purchase.id)
    if reserved is None:
        raise ProxylineError(
            "MTProxy stock is empty. Upload real MTProxy lines with /mtproxy_stock_add PRODUCT_ID ip:port:secret"
        )
    stock_id, stock_text = reserved
    proxy_text = format_mtproxy_result(stock_text)
    if proxy_text.strip() == str(stock_text).strip():
        # Formatter could not find ip/port/secret; do not deliver a broken item.
        async with SessionLocal() as session:
            stock = await session.get(ProductStockItem, stock_id)
            if stock:
                stock.status = "available"
                stock.reserved_at = None
                stock.reserved_purchase_id = None
            row = await session.get(DigitalPurchase, purchase.id)
            if row:
                row.stock_item_id = None
                row.updated_at = datetime.utcnow()
            await session.commit()
        raise ProxylineError(
            "MTProxy stock line has invalid format. Use ip:port:secret or tg://proxy?..."
        )

    message = await bot.send_message(
        purchase.buyer_id,
        "✅ Ваш MTProxy готов\n\n"
        + proxy_text
        + "\n\nНажмите на ссылку подключения или вручную введите IP, порт и секретный ключ в Telegram.",
    )
    async with SessionLocal() as session:
        row = await session.get(DigitalPurchase, purchase.id)
        stock = await session.get(ProductStockItem, stock_id)
        db_product = await session.get(ShopProduct, product.id)
        if row:
            row.status = "delivered"
            row.stock_item_id = stock_id
            row.delivered_at = datetime.utcnow()
            row.delivery_message_id = message.message_id
            row.delivery_error = None
            row.active_key = None
            row.updated_at = datetime.utcnow()
        if stock:
            stock.status = "delivered"
            stock.delivered_to = purchase.buyer_id
            stock.delivered_at = datetime.utcnow()
            stock.reserved_at = None
            stock.reserved_purchase_id = None
        if db_product:
            qty = max(1, int(getattr(row, "quantity", None) or getattr(purchase, "quantity", 1) or 1))
            db_product.sales_count = int(db_product.sales_count or 0) + qty
            db_product.revenue_total = Decimal(str(db_product.revenue_total or 0)) + Decimal(str(row.amount if row else purchase.amount))
        await session.commit()
    await notify_admins_simple(bot, f"✅ MTProxy purchase #{purchase.id} delivered from stock")
    return True


async def fulfill_proxyline(
    bot: Bot, purchase: DigitalPurchase, product: ShopProduct
) -> bool:
    cfg = _proxy_cfg(product, purchase.provider_key)
    proxy_kind = _proxy_kind_from_provider_key(purchase.provider_key, product)

    # MTProxy/Telegram-тариф может работать в двух режимах:
    # stock — выдавать реальные MTProxy строки ip:port:secret из склада;
    # api — покупать через Proxyline API. По умолчанию включён api, потому что
    # пользователь хочет автоматическую покупку через Proxyline.
    if proxy_kind == "mtproxy" and PROXYLINE_MTPROXY_MODE == "stock":
        return await _fulfill_mtproxy_stock(bot, purchase, product)

    provider_name = "proxyline"
    try:
        if purchase.provider_key:
            raw_provider = json.loads(purchase.provider_key).get("provider")
            if raw_provider:
                provider_name = str(raw_provider).lower()
    except Exception:
        provider_name = "proxyline"

    if provider_name == "proxys":
        if not PROXYS_ENABLED or not PROXYS_API_KEY:
            raise ProxylineError("Proxys API is not configured: set PROXYS_ENABLED=1 and PROXYS_API_KEY")
    elif not PROXYLINE_ENABLED or not PROXYLINE_API_KEY:
        raise ProxylineError("Proxyline API is not configured")

    if cfg is None:
        raise ProxylineError("Proxyline product parameters are missing")
    if PROXYLINE_COUPON and not cfg.coupon:
        from dataclasses import replace

        cfg = replace(cfg, coupon=PROXYLINE_COUPON)
    if provider_name == "proxys":
        from app.proxys import ProxysService
        service = ProxysService(PROXYS_API_KEY)
    else:
        service = ProxylineService(PROXYLINE_API_KEY)
    available = await service.ips_count(cfg)
    if available < cfg.count:
        raise ProxylineError(
            f"Not enough proxies: available={available}, required={cfg.count}"
        )
    payload = await service.buy_proxy(cfg)
    if proxy_kind == "mtproxy":
        # Если у провайдера/адаптера всё-таки вернулся настоящий MTProxy secret,
        # покажем MTProxy-формат. Иначе выдаём обычный Proxyline HTTP/SOCKS формат.
        mt_text = format_mtproxy_result(payload)
        raw_text = str(payload)
        if "Секретный ключ" in mt_text and mt_text.strip() != raw_text.strip():
            proxy_text = mt_text
            message_title = "✅ Ваш MTProxy готов"
            message_footer = "Нажмите на ссылку подключения или введите данные вручную."
        else:
            proxy_text = format_proxyline_result(payload)
            message_title = "✅ Ваш Telegram-прокси готов"
            message_footer = "Proxyline выдал прокси в формате HTTP/SOCKS5. Сохраните данные подключения."
    else:
        proxy_text = format_proxyline_result(payload)
        message_title = "✅ Ваш прокси готов"
        message_footer = "Сохраните данные подключения."

    message = await bot.send_message(
        purchase.buyer_id,
        message_title + "\n\n" + proxy_text + "\n\n" + message_footer,
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
        qty = max(1, int(getattr(row, "quantity", None) or getattr(purchase, "quantity", 1) or 1))
        db_product.sales_count = int(db_product.sales_count or 0) + qty
        db_product.revenue_total = Decimal(
            str(db_product.revenue_total or 0)
        ) + Decimal(str(row.amount))
        await session.commit()
    provider_label = "Proxys" if provider_name == "proxys" else "Proxyline"
    await notify_admins_simple(bot, f"✅ {provider_label} purchase #{purchase.id} delivered")
    return True


async def fulfill_supplier(
    bot: Bot, purchase: DigitalPurchase, product: ShopProduct
) -> bool:
    """Create a supplier order after a paid CryptoBot purchase.

    provider_key stores the supplier Telegram ID, not suppliers.id. Telegram IDs can
    be larger than PostgreSQL int32 primary keys, so we never call session.get(Supplier, telegram_id).
    """
    operation_id = 9_000_000_000 + purchase.id
    supplier = None
    instant_request = False
    order_id_for_ui = None

    async with SessionLocal() as session:
        current = await session.get(DigitalPurchase, purchase.id)
        if current.legacy_order_id:
            return True

        content_type = (getattr(product, "content_type", None) or "number").lower()
        instant_request = content_type in {"account", "manual", "other"}
        order_status = "waiting_supplier_account" if instant_request else "waiting_service"

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
            status=order_status,
            service_name=("Готовая выдача" if instant_request else None),
            paid_at=purchase.paid_at or datetime.utcnow(),
            raw_message=f"Crypto Pay purchase #{purchase.id}",
        )
        session.add(order)
        await session.flush()

        if purchase.provider_key and str(purchase.provider_key).isdigit():
            supplier_telegram_id = int(purchase.provider_key)
            supplier = await session.scalar(
                select(Supplier).where(Supplier.telegram_id == supplier_telegram_id)
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
        order_id_for_ui = order.id

    if instant_request and supplier is not None:
        try:
            from app.services import create_supplier_request
            from app.keyboards import supplier_new_order_keyboard
            async with SessionLocal() as session:
                request = await create_supplier_request(session, order_id_for_ui, supplier.telegram_id, "account")
            sent = await bot.send_message(
                supplier.telegram_id,
                "🧾 Новый заказ на выдачу\n\n"
                f"Товар: {product.name}\n"
                "Пришлите данные аккаунта/товара одним сообщением. Покупатель не увидит ваши контакты.",
                reply_markup=supplier_new_order_keyboard(request.id, "account"),
            )
            async with SessionLocal() as session:
                req = await session.get(type(request), request.id)
                if req:
                    req.supplier_message_id = getattr(sent, "message_id", None)
                    await session.commit()
            await bot.send_message(
                purchase.buyer_id,
                "✅ Оплата подтверждена. Поставщик получил заявку на выдачу товара.",
            )
        except Exception as exc:
            logger.exception("SUPPLIER_INSTANT_REQUEST_FAILED purchase_id=%s", purchase.id)
            async with SessionLocal() as session:
                row = await session.get(DigitalPurchase, purchase.id)
                if row:
                    row.delivery_error = f"Supplier request failed: {exc}"[:500]
                    await session.commit()
        await notify_admins_simple(bot, f"🧾 Paid supplier account order #{operation_id} created for purchase #{purchase.id}")
        return True

    try:
        await bot.send_message(
            purchase.buyer_id,
            "✅ Оплата подтверждена.\n\nВыберите сервис, под который нужен номер.",
        )
        from app.handlers_main import send_service_keyboard

        class _FakeMessage:
            def __init__(self, chat_id, user_id):
                self.chat = type("Chat", (), {"id": chat_id})()
                self.from_user = type("User", (), {"id": user_id, "username": None})()

            async def answer(self, *args, **kwargs):
                return await bot.send_message(self.chat.id, *args, **kwargs)

        await send_service_keyboard(
            bot, _FakeMessage(purchase.buyer_id, purchase.buyer_id), order_id_for_ui, None, page=0
        )
    except Exception as exc:
        async with SessionLocal() as session:
            row = await session.get(DigitalPurchase, purchase.id)
            if row:
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
