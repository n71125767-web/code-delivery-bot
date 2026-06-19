from __future__ import annotations

import json
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CRYPTO_PAY_ACCEPTED_ASSET_LIST, CRYPTO_PAY_INVOICE_EXPIRES_SECONDS
from app.cryptopay_service import CRYPTO_ASSETS, crypto_client
from app.database import SessionLocal
from app.market_wallet_v49 import add_wallet_balance, admin_recipients, money
from app.models import ProductProvider, ServiceOption, ShopProduct, TextTemplate, WalletTopup
from app.senders import safe_send_message


DEFAULT_MAIN_TEXT = (
    "MCS Shop\n"
    "Быстрый магазин с автовыдачей.\n\n"
    "Выберите нужный раздел ниже."
)

DEFAULT_FAQ_TEXT = (
    "FAQ\n\n"
    "Как купить товар: откройте Каталог, выберите товар и оплатите.\n"
    "Как купить номер: откройте Номера и выберите нужный сервис.\n"
    "Как пополнить баланс: откройте Кошелёк → Пополнить.\n"
    "Если возникла проблема, напишите в поддержку."
)


def _now() -> datetime:
    return datetime.utcnow()


def parse_money(raw: str) -> Decimal:
    value = Decimal(str(raw).replace(",", "."))
    if value <= 0:
        raise ValueError("amount must be positive")
    return value.quantize(Decimal("0.01"))


def _obj_to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    data: dict[str, Any] = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool, Decimal, type(None), datetime)):
            data[name] = value
    return data


async def get_template_value(session: AsyncSession, key: str, default: str = "") -> str:
    row = await session.scalar(select(TextTemplate).where(TextTemplate.key == key))
    return row.value if row and row.value is not None else default


async def set_template_value(session: AsyncSession, key: str, value: str) -> None:
    row = await session.scalar(select(TextTemplate).where(TextTemplate.key == key))
    if row is None:
        session.add(TextTemplate(key=key, value=value))
    else:
        row.value = value
        row.updated_at = _now()


async def get_main_page_text() -> str:
    async with SessionLocal() as session:
        return await get_template_value(session, "main_page_text", DEFAULT_MAIN_TEXT)


async def get_faq_page_text() -> str:
    async with SessionLocal() as session:
        return await get_template_value(session, "faq_text", DEFAULT_FAQ_TEXT)


async def main_settings_text() -> str:
    async with SessionLocal() as session:
        main_text = await get_template_value(session, "main_page_text", DEFAULT_MAIN_TEXT)
        faq_text = await get_template_value(session, "faq_text", DEFAULT_FAQ_TEXT)
    return (
        "🎨 Настройка главной и визуала\n\n"
        "Команды:\n"
        "• /main_set ТЕКСТ — изменить главную страницу\n"
        "• /faq_set ТЕКСТ — изменить FAQ\n"
        "• /number_service_add НАЗВАНИЕ — добавить сервис для номеров\n"
        "• /number_service_remove НАЗВАНИЕ — убрать сервис\n"
        "• /number_services — список сервисов\n\n"
        "Текущая главная:\n"
        f"{main_text[:700]}\n\n"
        "Текущий FAQ:\n"
        f"{faq_text[:700]}"
    )


async def set_main_page_text(raw: str) -> str:
    text = raw.strip()
    if not text:
        return "Формат: /main_set текст главной страницы"
    async with SessionLocal() as session:
        await set_template_value(session, "main_page_text", text)
        await session.commit()
    return "✅ Главная страница обновлена."


async def set_faq_text(raw: str) -> str:
    text = raw.strip()
    if not text:
        return "Формат: /faq_set текст FAQ"
    async with SessionLocal() as session:
        await set_template_value(session, "faq_text", text)
        await session.commit()
    return "✅ FAQ обновлён."


async def number_services_text() -> str:
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(ServiceOption).order_by(ServiceOption.name))).all())
    active = [r for r in rows if r.is_active]
    if not active:
        return "📱 Сервисы номеров пока не настроены.\nДобавить: /number_service_add Telegram"
    return "📱 Сервисы номеров\n\n" + "\n".join(f"• {r.name}" for r in active)


async def add_number_service(raw: str) -> str:
    name = raw.strip()[:255]
    if not name:
        return "Формат: /number_service_add Название сервиса"
    async with SessionLocal() as session:
        row = await session.scalar(select(ServiceOption).where(ServiceOption.name == name))
        if row is None:
            session.add(ServiceOption(name=name, emoji=None, is_active=True))
        else:
            row.is_active = True
            row.emoji = None
        await session.commit()
    return f"✅ Сервис «{name}» добавлен для номеров."


async def remove_number_service(raw: str) -> str:
    name = raw.strip()
    if not name:
        return "Формат: /number_service_remove Название сервиса"
    async with SessionLocal() as session:
        row = await session.scalar(select(ServiceOption).where(ServiceOption.name == name))
        if not row:
            return "Сервис не найден."
        row.is_active = False
        await session.commit()
    return f"✅ Сервис «{name}» скрыт."


def wallet_topup_amounts_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for amount in ("5", "10", "25", "50"):
        kb.button(text=f"{amount} USDT", callback_data=f"wallet:topup_quick:{amount}:USDT")
    kb.button(text="✍️ Своя сумма", callback_data="wallet:topup_custom")
    kb.button(text="⬅️ К кошельку", callback_data="buyer:wallet")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def wallet_topup_invoice_keyboard(invoice_url: str, topup_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатить через CryptoBot", url=invoice_url)
    kb.button(text="🔄 Проверить пополнение", callback_data=f"wallet_topup:check:{topup_id}")
    kb.button(text="💼 К кошельку", callback_data="buyer:wallet")
    kb.adjust(1)
    return kb.as_markup()


async def create_wallet_topup_invoice(user_id: int, username: str | None, amount: Decimal, currency: str = "USDT") -> WalletTopup:
    currency = (currency or "USDT").upper()[:10]
    amount = money(amount)
    if amount <= 0:
        raise ValueError("Сумма должна быть больше 0.")
    async with SessionLocal() as session:
        topup = WalletTopup(
            user_id=user_id,
            username=username,
            amount=amount,
            currency=currency,
            status="creating",
            payload="",
        )
        session.add(topup)
        await session.flush()
        payload = json.dumps(
            {"type": "wallet_topup", "topup_id": topup.id, "nonce": secrets.token_hex(8)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        topup.payload = payload
        await session.commit()
        await session.refresh(topup)

    kwargs: dict[str, Any] = {
        "amount": float(amount),
        "description": "Пополнение внутреннего баланса магазина",
        "payload": payload,
        "expires_in": CRYPTO_PAY_INVOICE_EXPIRES_SECONDS,
        "allow_anonymous": False,
    }
    if currency in CRYPTO_ASSETS:
        kwargs.update(currency_type="crypto", asset=currency)
    else:
        kwargs.update(currency_type="fiat", fiat=currency, accepted_assets=CRYPTO_PAY_ACCEPTED_ASSET_LIST)
    invoice = await crypto_client().create_invoice(**kwargs)
    data = _obj_to_dict(invoice)
    invoice_id = int(data.get("invoice_id") or getattr(invoice, "invoice_id"))
    invoice_url = (
        data.get("bot_invoice_url")
        or data.get("mini_app_invoice_url")
        or data.get("web_app_invoice_url")
        or getattr(invoice, "bot_invoice_url", None)
    )
    if not invoice_url:
        raise RuntimeError("Crypto Pay не вернул ссылку на оплату.")
    async with SessionLocal() as session:
        row = await session.get(WalletTopup, topup.id)
        row.invoice_id = invoice_id
        row.invoice_url = invoice_url
        row.status = "active"
        row.raw_response = json.dumps(data, ensure_ascii=False, default=str)
        row.updated_at = _now()
        await session.commit()
        await session.refresh(row)
        return row


async def process_wallet_topup_paid(bot: Bot, invoice_data: dict[str, Any]) -> bool:
    payload_raw = invoice_data.get("payload") or "{}"
    try:
        payload = json.loads(payload_raw)
    except Exception:
        return False
    if payload.get("type") != "wallet_topup":
        return False
    topup_id = int(payload.get("topup_id") or 0)
    if not topup_id:
        return False
    status = str(invoice_data.get("status") or "").lower()
    if status != "paid":
        return False
    invoice_id = int(invoice_data.get("invoice_id") or 0)
    async with SessionLocal() as session:
        topup = await session.get(WalletTopup, topup_id)
        if not topup:
            return False
        if invoice_id and topup.invoice_id and int(topup.invoice_id) != invoice_id:
            raise RuntimeError("Wallet topup invoice mismatch")
        if topup.status == "paid":
            return True
        topup.status = "paid"
        topup.paid_at = _now()
        topup.updated_at = _now()
        topup.raw_response = json.dumps(invoice_data, ensure_ascii=False, default=str)
        await add_wallet_balance(
            session,
            topup.user_id,
            topup.amount,
            topup.currency,
            "wallet_topup",
            source_type="wallet_topup",
            source_id=topup.id,
            note=f"CryptoBot invoice {topup.invoice_id}",
        )
        await session.commit()
        user_id = topup.user_id
        username = topup.username
        amount = money(topup.amount)
        currency = topup.currency
    await safe_send_message(bot, user_id, f"✅ Баланс пополнен на {amount} {currency}.")
    user_text = f"@{username}" if username else "без username"
    admin_text = (
        "✅ Активирован чек / пополнение CryptoBot\n\n"
        f"👤 Пользователь: {user_text}\n"
        f"🆔 ID: {user_id}\n"
        f"💵 Сумма: {amount} {currency}\n"
        f"🔢 Topup ID: {topup_id}\n"
        f"💳 Invoice ID: {invoice_id or '—'}"
    )
    for admin_id in admin_recipients():
        await safe_send_message(bot, admin_id, admin_text)
    return True


async def check_wallet_topup(bot: Bot, topup_id: int, user_id: int) -> str:
    async with SessionLocal() as session:
        topup = await session.get(WalletTopup, topup_id)
        if not topup:
            return "Пополнение не найдено."
        if topup.user_id != user_id:
            return "Это не ваше пополнение."
        if topup.status == "paid":
            return "Пополнение уже зачислено."
        invoice_id = topup.invoice_id
    if not invoice_id:
        return "Счёт ещё создаётся. Попробуйте позже."
    result = await crypto_client().get_invoices(invoice_ids=invoice_id)
    data = _obj_to_dict(result)
    # aiocryptopay может вернуть объект-список или объект с items.
    if not data or "invoice_id" not in data:
        items = getattr(result, "items", None) or getattr(result, "invoices", None)
        if items:
            data = _obj_to_dict(items[0])
    if str(data.get("status") or "").lower() == "paid":
        await process_wallet_topup_paid(bot, data)
        return "✅ Пополнение подтверждено и зачислено."
    return "Оплата пока не найдена."


async def supplier_products_text(supplier_id: int) -> str:
    async with SessionLocal() as session:
        rows = list((await session.scalars(
            select(ShopProduct)
            .join(ProductProvider, ProductProvider.internal_key == ShopProduct.internal_key)
            .where(
                ProductProvider.provider_type == "supplier",
                ProductProvider.provider_key == str(supplier_id),
                ProductProvider.enabled.is_(True),
                ShopProduct.is_deleted.is_(False),
            )
            .order_by(ShopProduct.id.desc())
        )).all())
    if not rows:
        return "📦 Мои товары\n\nУ вас пока нет привязанных товаров. После одобрения заявки товар появится здесь."
    lines = ["📦 Мои товары", "", "Чтобы изменить цену: /supplier_price ID ЦЕНА ВАЛЮТА", ""]
    for p in rows:
        status = "показывается" if p.is_active else "скрыт"
        lines.append(f"#{p.id} — {p.name} — {money(p.price)} {p.currency} — {status}")
    return "\n".join(lines)


async def set_supplier_product_price(supplier_id: int, raw: str) -> str:
    parts = raw.split()
    if len(parts) < 2 or not parts[0].isdigit():
        return "Формат: /supplier_price ID_ТОВАРА ЦЕНА [ВАЛЮТА]\nПример: /supplier_price 12 4.50 USD"
    product_id = int(parts[0])
    try:
        price = parse_money(parts[1])
    except (InvalidOperation, ValueError):
        return "Цена должна быть числом больше 0."
    currency = parts[2].upper()[:10] if len(parts) > 2 else None
    async with SessionLocal() as session:
        product = await session.get(ShopProduct, product_id)
        if not product:
            return "Товар не найден."
        provider = await session.scalar(select(ProductProvider).where(ProductProvider.internal_key == product.internal_key, ProductProvider.enabled.is_(True)))
        if not provider or provider.provider_type != "supplier" or provider.provider_key != str(supplier_id):
            return "Этот товар не привязан к вам."
        product.price = price
        if currency:
            product.currency = currency
        product.updated_at = _now()
        await session.commit()
    return f"✅ Цена обновлена: {price} {currency or product.currency}."
