from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.config import ADMIN_IDS, ADMIN_ALERT_CHAT_IDS, ADMIN_ALERT_CHAT_ID, WITHDRAWAL_FEE_USD, WITHDRAW_AUTO_CRYPTOBOT, WITHDRAW_PAYOUT_ASSET
from app.database import SessionLocal
from app.models import (
    CryptoPayment,
    DigitalPurchase,
    ProductProvider,
    ShopProduct,
    Supplier,
    SupplierProduct,
    SupplierWithdrawal,
    UserWallet,
    WalletLedger,
)
from app.senders import safe_send_message


def money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def user_label(user_id: int | None, username: str | None = None) -> str:
    u = (username or "").strip().lstrip("@")
    return f"@{u}" if u else f"ID {user_id or '—'}"


def admin_recipients() -> list[int]:
    ids: list[int] = []
    for value in list(ADMIN_IDS) + list(ADMIN_ALERT_CHAT_IDS or []):
        if value and int(value) not in ids:
            ids.append(int(value))
    if ADMIN_ALERT_CHAT_ID and int(ADMIN_ALERT_CHAT_ID) not in ids:
        ids.append(int(ADMIN_ALERT_CHAT_ID))
    return ids


async def notify_new_user(bot: Bot, user_id: int, username: str | None, full_name: str | None = None) -> None:
    text = (
        "🆕 Новый пользователь зарегистрировался!\n\n"
        f"👤 Пользователь: {user_label(user_id, username)} ({full_name or 'никнейм не указан'})\n"
        f"🆔 ID: {user_id}"
    )
    for admin_id in admin_recipients():
        await safe_send_message(bot, admin_id, text)


async def add_wallet_balance(session, user_id: int, amount: Any, currency: str, event_type: str, *, source_type: str | None = None, source_id: int | None = None, note: str | None = None) -> None:
    amount_d = money(amount)
    wallet = await session.get(UserWallet, user_id)
    if wallet is None:
        wallet = UserWallet(user_id=user_id, balance=0, currency=(currency or "USD").upper())
        session.add(wallet)
        await session.flush()
    wallet.balance = money(wallet.balance) + amount_d
    wallet.currency = (currency or wallet.currency or "USD").upper()
    wallet.updated_at = datetime.utcnow()
    session.add(WalletLedger(user_id=user_id, amount=amount_d, currency=wallet.currency, event_type=event_type, source_type=source_type, source_id=source_id, note=note))


async def get_wallet_text(user_id: int) -> str:
    async with SessionLocal() as session:
        wallet = await session.get(UserWallet, user_id)
        rows = list((await session.scalars(select(WalletLedger).where(WalletLedger.user_id == user_id).order_by(WalletLedger.id.desc()).limit(8))).all())
    balance = money(wallet.balance if wallet else 0)
    currency = (wallet.currency if wallet else "USD") or "USD"
    lines = ["💼 Внутренний кошелёк", "", f"Баланс: {balance} {currency}", ""]
    if rows:
        lines.append("Последние операции:")
        for r in rows:
            sign = "+" if money(r.amount) >= 0 else ""
            lines.append(f"• {sign}{money(r.amount)} {r.currency} — {r.event_type}")
    else:
        lines.append("Операций пока нет.")
    return "\n".join(lines)


def wallet_keyboard(is_supplier: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Пополнить", callback_data="wallet:topup_help")
    if is_supplier:
        kb.button(text="↗️ Вывести", callback_data="supplier:withdraw_help")
    kb.button(text="🏠 Главная", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


def supplier_wallet_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Мои заказы", callback_data="supplier:filter:all:0")
    kb.button(text="💼 Баланс", callback_data="supplier:wallet")
    kb.button(text="↗️ Вывод", callback_data="supplier:withdraw_help")
    kb.button(text="🏠 Режим покупателя", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


async def supplier_orders_text(supplier_id: int) -> str:
    async with SessionLocal() as session:
        provider_keys = [str(supplier_id)]
        rows = list((await session.scalars(
            select(DigitalPurchase)
            .join(ShopProduct, ShopProduct.id == DigitalPurchase.product_id)
            .join(ProductProvider, ProductProvider.internal_key == ShopProduct.internal_key)
            .where(ProductProvider.provider_type == "supplier", ProductProvider.provider_key.in_(provider_keys))
            .order_by(DigitalPurchase.id.desc())
            .limit(20)
        )).all())
        products = {p.id: p for p in (await session.scalars(select(ShopProduct).where(ShopProduct.id.in_([r.product_id for r in rows] or [0])))).all()}
    lines = ["📦 Заказы поставщика", ""]
    if not rows:
        lines.append("Заказов по вашим товарам пока нет.")
    for r in rows:
        p = products.get(r.product_id)
        lines.append(f"#{r.id} — {p.name if p else 'Товар'} — {money(r.amount)} {r.currency} — {r.status}")
    return "\n".join(lines)


async def notify_purchase_and_credit_supplier(bot: Bot, purchase_id: int) -> None:
    async with SessionLocal() as session:
        purchase = await session.get(DigitalPurchase, purchase_id)
        if not purchase:
            return
        product = await session.get(ShopProduct, purchase.product_id)
        payment = await session.scalar(select(CryptoPayment).where(CryptoPayment.purchase_id == purchase_id))
        provider = None
        supplier_id = None
        if product:
            provider = await session.scalar(select(ProductProvider).where(ProductProvider.internal_key == product.internal_key, ProductProvider.enabled.is_(True)))
            if provider and provider.provider_type == "supplier" and provider.provider_key:
                try:
                    supplier_id = int(provider.provider_key)
                except Exception:
                    supplier_id = None
                if supplier_id:
                    # Пока без комиссии: вся сумма зачисляется на внутренний баланс поставщика.
                    await add_wallet_balance(session, supplier_id, purchase.amount, purchase.currency, "supplier_sale", source_type="purchase", source_id=purchase.id, note=f"Продажа товара {product.name}")
                    await session.commit()
        username = purchase.buyer_username or ""
        product_name = product.name if product else f"Товар #{purchase.product_id}"
        bot_username = (await bot.me()).username or ""
        product_link = f"https://t.me/{bot_username}?start=admproduct_{product.internal_key}" if bot_username and product else ""
        text = (
            "💰 Новая покупка через CryptoBot!\n\n"
            f"👤 Пользователь: {user_label(purchase.buyer_id, username)}\n"
            f"🆔 ID: {purchase.buyer_id}\n"
            f"📦 Купил: {product_name}" + (f"\n{product_link}" if product_link else "") + "\n"
            f"💵 Сумма: {money(purchase.amount)} {purchase.currency}\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "📋 ТЕХНИЧЕСКАЯ ИНФОРМАЦИЯ\n\n"
            f"🔢 ID операции: {purchase.id}\n"
            f"🆔 Внешний ID: {payment.invoice_id if payment else '—'}\n"
            f"👤 ID пользователя: {purchase.buyer_id}\n"
            f"💳 ID платёжной системы: {payment.id if payment else '—'}\n"
            f"📦 ID товара: {purchase.product_id}\n\n"
            f"📊 Статус: {purchase.status}\n"
            f"🕐 Создан: {purchase.created_at}\n"
            f"✅ Оплачен: {purchase.paid_at or '—'}"
        )
    for admin_id in admin_recipients():
        await safe_send_message(bot, admin_id, text)
    if supplier_id:
        await safe_send_message(bot, supplier_id, "💰 Купили ваш товар!\n\n" + text)


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


async def create_withdrawal_request(supplier_id: int, raw: str) -> str:
    parts = raw.split(maxsplit=2)
    if len(parts) < 2:
        return "Формат: /withdraw СУММА USDT_АДРЕС\nПример: /withdraw 10 UQ..."
    try:
        amount = money(parts[0])
    except Exception:
        return "Сумма должна быть числом."
    address = parts[1].strip()
    fee = money(WITHDRAWAL_FEE_USD)
    if amount <= 0:
        return "Сумма должна быть больше нуля."
    if amount <= fee:
        return f"Минимальная сумма должна быть больше комиссии вывода {fee} {WITHDRAW_PAYOUT_ASSET}."
    net_amount = money(amount - fee)
    async with SessionLocal() as session:
        wallet = await session.get(UserWallet, supplier_id)
        if not wallet or money(wallet.balance) < amount:
            return f"Недостаточно средств. Баланс: {money(wallet.balance if wallet else 0)} {(wallet.currency if wallet else 'USD')}"
        wallet.balance = money(wallet.balance) - amount
        wallet.updated_at = datetime.utcnow()
        wd = SupplierWithdrawal(
            supplier_id=supplier_id,
            amount=amount,
            currency=wallet.currency or WITHDRAW_PAYOUT_ASSET,
            payout_address=address,
            status="pending",
        )
        session.add(wd)
        await session.flush()
        session.add(WalletLedger(
            user_id=supplier_id,
            amount=-amount,
            currency=wallet.currency or WITHDRAW_PAYOUT_ASSET,
            event_type="withdraw_hold",
            source_type="withdrawal",
            source_id=wd.id,
            note=f"{address}; fee={fee}; net={net_amount}",
        ))
        await session.commit()
        await session.refresh(wd)
        withdrawal_id = wd.id

    if WITHDRAW_AUTO_CRYPTOBOT:
        try:
            from app.cryptopay_service import crypto_client
            try:
                check = await crypto_client().create_check(
                    asset=WITHDRAW_PAYOUT_ASSET,
                    amount=float(net_amount),
                    pin_to_user_id=supplier_id,
                )
            except TypeError:
                check = await crypto_client().create_check(
                    asset=WITHDRAW_PAYOUT_ASSET,
                    amount=float(net_amount),
                )
            data = _obj_to_dict(check)
            link = (
                data.get("bot_check_url")
                or data.get("check_url")
                or data.get("url")
                or getattr(check, "bot_check_url", None)
            )
            check_id = data.get("check_id") or data.get("id") or "—"
            async with SessionLocal() as session:
                wd = await session.get(SupplierWithdrawal, withdrawal_id)
                if wd:
                    wd.status = "paid"
                    wd.payout_link = str(link or check_id)
                    wd.updated_at = datetime.utcnow()
                    await session.commit()
            return (
                f"✅ Вывод #{withdrawal_id} создан и отправлен через CryptoBot.\n"
                f"Сумма: {amount} {WITHDRAW_PAYOUT_ASSET}\n"
                f"Комиссия: {fee} {WITHDRAW_PAYOUT_ASSET}\n"
                f"К выплате: {net_amount} {WITHDRAW_PAYOUT_ASSET}\n"
                f"Ссылка: {link or check_id}"
            )
        except Exception:
            return (
                f"✅ Заявка на вывод #{withdrawal_id} создана.\n"
                f"Сумма: {amount} {WITHDRAW_PAYOUT_ASSET}\n"
                f"Комиссия: {fee} {WITHDRAW_PAYOUT_ASSET}\n"
                f"К выплате: {net_amount} {WITHDRAW_PAYOUT_ASSET}\n\n"
                "Автовыплата не прошла. Администратор отправит выплату вручную."
            )

    return (
        f"✅ Заявка на вывод #{withdrawal_id} создана.\n"
        f"Сумма: {amount} {WITHDRAW_PAYOUT_ASSET}\n"
        f"Комиссия: {fee} {WITHDRAW_PAYOUT_ASSET}\n"
        f"К выплате: {net_amount} {WITHDRAW_PAYOUT_ASSET}\n\n"
        "Администратор отправит выплату через CryptoBot и прикрепит ссылку."
    )


async def admin_withdrawals_text() -> str:
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(SupplierWithdrawal).order_by(SupplierWithdrawal.id.desc()).limit(20))).all())
    if not rows:
        return "↗️ Заявок на вывод нет."
    lines = ["↗️ Заявки на вывод", ""]
    for r in rows:
        lines.append(f"#{r.id} — supplier {r.supplier_id} — {money(r.amount)} {r.currency} — {r.status} — {r.payout_address or 'адрес не указан'}")
    lines.append("\nПодтвердить: /withdraw_done ID ССЫЛКА_ИЛИ_TX")
    return "\n".join(lines)


async def mark_withdrawal_done(bot: Bot, admin_id: int, raw: str) -> str:
    parts = raw.split(maxsplit=1)
    if not parts or not parts[0].isdigit():
        return "Формат: /withdraw_done ID ССЫЛКА_ИЛИ_TX"
    wid = int(parts[0]); link = parts[1].strip() if len(parts)>1 else None
    async with SessionLocal() as session:
        wd = await session.get(SupplierWithdrawal, wid)
        if not wd:
            return "Заявка не найдена."
        wd.status = "paid"
        wd.payout_link = link
        wd.admin_id = admin_id
        wd.updated_at = datetime.utcnow()
        await session.commit()
        supplier_id = wd.supplier_id
    await safe_send_message(
        bot,
        supplier_id,
        "✅ Выплата отправлена\n\n"
        f"Заявка: #{wid}\n"
        f"Сумма: {money(wd.amount)} {wd.currency}\n"
        f"Ссылка/TX: {link or 'не указан'}"
    )
    return f"✅ Вывод #{wid} отмечен как выплаченный. Ссылка/TX: {link or 'не указан'}"
