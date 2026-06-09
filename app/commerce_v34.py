from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select

from app.config import (
    CRYPTO_PAY_ENABLED,
    PROXYLINE_API_KEY,
    PROXYLINE_ENABLED,
)
from app.database import SessionLocal
from app.models import (
    AdminAuditLog,
    ConversationState,
    DigitalPurchase,
    ProductProvider,
    ProductStockItem,
    ShopProduct,
)

FULFILLMENT_TYPES = {"digital", "stock", "proxyline", "supplier", "number"}
PROXY_REQUIRED_KEYS = {"country", "period", "count", "ip_version", "type"}


async def write_audit(
    admin_id: int,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    details: dict[str, Any] | str | None = None,
) -> None:
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=False, default=str)
    async with SessionLocal() as session:
        session.add(
            AdminAuditLog(
                admin_id=admin_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )
        )
        await session.commit()


async def set_state(
    user_id: int,
    scope: str,
    payload: dict[str, Any],
    ttl_seconds: int = 1800,
) -> None:
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    async with SessionLocal() as session:
        row = await session.get(ConversationState, (user_id, scope))
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        if row is None:
            row = ConversationState(
                user_id=user_id,
                scope=scope,
                payload_json=raw,
                expires_at=expires_at,
            )
            session.add(row)
        else:
            row.payload_json = raw
            row.expires_at = expires_at
            row.updated_at = datetime.utcnow()
        await session.commit()


async def get_state(user_id: int, scope: str) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        row = await session.get(ConversationState, (user_id, scope))
        if row is None:
            return None
        if row.expires_at and row.expires_at < datetime.utcnow():
            await session.delete(row)
            await session.commit()
            return None
        try:
            return json.loads(row.payload_json)
        except Exception:
            await session.delete(row)
            await session.commit()
            return None


async def clear_state(user_id: int, scope: str | None = None) -> None:
    async with SessionLocal() as session:
        stmt = delete(ConversationState).where(ConversationState.user_id == user_id)
        if scope is not None:
            stmt = stmt.where(ConversationState.scope == scope)
        await session.execute(stmt)
        await session.commit()


def parse_proxy_provider_key(provider_key: str | None) -> dict[str, Any] | None:
    if not provider_key:
        return None
    try:
        data = json.loads(provider_key)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def validate_product_for_sale(product: ShopProduct) -> list[str]:
    errors: list[str] = []

    if product.is_deleted:
        errors.append("товар находится в архиве")
    if not product.name.strip():
        errors.append("не задано название")
    if product.price is None or Decimal(str(product.price)) <= 0:
        errors.append("цена должна быть больше нуля")
    if not product.currency:
        errors.append("не задана валюта")
    if product.fulfillment_type not in FULFILLMENT_TYPES:
        errors.append("не выбран способ выдачи")

    if product.fulfillment_type == "digital":
        if not (product.content_text or product.content_file_id):
            errors.append("не добавлен контент")

    if product.fulfillment_type == "stock":
        async with SessionLocal() as session:
            stock_id = await session.scalar(
                select(ProductStockItem.id).where(
                    ProductStockItem.product_id == product.id,
                    ProductStockItem.status == "available",
                ).limit(1)
            )
        if stock_id is None:
            errors.append("нет доступных позиций")

    if product.fulfillment_type == "proxyline":
        if not PROXYLINE_ENABLED or not PROXYLINE_API_KEY:
            errors.append("Proxyline API не настроен")
        cfg = parse_proxy_provider_key(product.provider_key)
        if cfg is None:
            errors.append("не заданы параметры Proxyline")
        else:
            missing = sorted(PROXY_REQUIRED_KEYS - set(cfg))
            if missing:
                errors.append("в Proxyline JSON отсутствуют: " + ", ".join(missing))

    if product.fulfillment_type in {"supplier", "number"}:
        if not product.provider_key or not str(product.provider_key).isdigit():
            errors.append("не назначен поставщик")

    if not CRYPTO_PAY_ENABLED:
        errors.append("Crypto Pay не настроен")

    return errors


async def release_stale_reservations(max_age_seconds: int = 3900) -> int:
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
    released = 0
    async with SessionLocal() as session:
        rows = list((await session.scalars(
            select(ProductStockItem).where(
                ProductStockItem.status == "reserved",
                ProductStockItem.reserved_at.is_not(None),
                ProductStockItem.reserved_at < cutoff,
            )
        )).all())
        for row in rows:
            purchase = None
            if row.reserved_purchase_id:
                purchase = await session.get(DigitalPurchase, row.reserved_purchase_id)
            if purchase and purchase.status in {
                "paid", "delivering", "delivered", "awaiting_supplier"
            }:
                continue
            row.status = "available"
            row.reserved_at = None
            row.reserved_purchase_id = None
            if purchase and purchase.stock_item_id == row.id:
                purchase.stock_item_id = None
                purchase.active_key = None
                if purchase.status in {"creating_invoice", "pending_payment"}:
                    purchase.status = "expired"
                purchase.updated_at = datetime.utcnow()
            released += 1
        await session.commit()
    return released
