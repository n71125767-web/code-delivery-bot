from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
import aiohttp

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.config import (
    ADMIN_IDS,
    ADMIN_ALERT_CHAT_IDS,
    ADMIN_ALERT_CHAT_ID,
    WITHDRAWAL_FEE_USD,
    WITHDRAW_AUTO_CRYPTOBOT,
    WITHDRAW_PAYOUT_ASSET,
    CRYPTO_PAY_TOKEN,
    CRYPTO_PAY_NETWORK,
    CRYPTO_PAY_API_BASE_URL,
    CRYPTO_PAY_CHECK_BASE_URL,
)
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


def money_text(value: Any, currency: str | None = None) -> str:
    """Human readable money without database-scale zero spam."""
    try:
        amount = Decimal(str(value or "0")).quantize(Decimal("0.01"))
        rendered = f"{amount:.2f}"
    except Exception:
        rendered = str(value or "0")
    return f"{rendered} {currency}" if currency else rendered


def _crypto_pay_base_url() -> str:
    base = (CRYPTO_PAY_API_BASE_URL or "").strip().rstrip("/")
    if base:
        return base
    if CRYPTO_PAY_NETWORK == "mainnet":
        return "https://pay.crypt.bot/api"
    return "https://testnet-pay.crypt.bot/api"


def _crypto_pay_method_urls(method: str) -> list[str]:
    method = method.lstrip("/")
    urls: list[str] = []
    custom = (CRYPTO_PAY_CHECK_BASE_URL or "").strip().rstrip("/")
    if custom:
        urls.append(f"{custom}/{method}")
    urls.append(f"{_crypto_pay_base_url()}/{method}")
    # Compatibility with examples that use https://crypt.bot + createCheck.
    # Kept as fallback only; official Crypto Pay API normally uses pay.crypt.bot/api.
    urls.append(f"https://crypt.bot/{method}")
    dedup: list[str] = []
    for url in urls:
        if url not in dedup:
            dedup.append(url)
    return dedup


async def _raw_crypto_pay_request(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not CRYPTO_PAY_TOKEN:
        raise RuntimeError("CRYPTO_PAY_TOKEN не задан")
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json",
    }
    errors: list[str] = []
    async with aiohttp.ClientSession() as client:
        for url in _crypto_pay_method_urls(method):
            try:
                async with client.post(url, headers=headers, json=payload, timeout=30) as response:
                    try:
                        data = await response.json()
                    except Exception:
                        text = await response.text()
                        errors.append(f"{url}: HTTP {response.status}: {text[:300]}")
                        continue
                if not data.get("ok"):
                    error = data.get("error") or data
                    errors.append(f"{url}: {error}")
                    continue
                return data.get("result") or {}
            except Exception as exc:
                errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors[-3:]) or "CryptoBot API request failed")


def _extract_check_link(data: dict[str, Any]) -> str | None:
    """Extract a CryptoBot check URL from direct API or library responses."""
    if not isinstance(data, dict):
        return None
    direct = (
        data.get("bot_check_url")
        or data.get("check_url")
        or data.get("url")
        or data.get("link")
        or data.get("pay_url")
    )
    if direct:
        return str(direct)
    for key in ("result", "check", "data"):
        nested = data.get(key)
        if isinstance(nested, dict):
            found = _extract_check_link(nested)
            if found:
                return found
    return None


def _extract_check_id(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return ""
    direct = data.get("check_id") or data.get("id")
    if direct:
        return str(direct)
    for key in ("result", "check", "data"):
        nested = data.get(key)
        if isinstance(nested, dict):
            value = _extract_check_id(nested)
            if value:
                return value
    return ""


async def _create_cryptobot_withdraw_check(*, supplier_id: int, amount: Decimal, asset: str) -> tuple[str | None, str | None]:
    """Create an outgoing CryptoBot check for supplier withdrawal.

    Important: createInvoice creates an incoming payment link; supplier payouts need
    createCheck. We try the official HTTP method first, then the library method.
    If CryptoBot disallows checks for this token, caller sends the withdrawal to
    manual moderation instead of losing the request.
    """
    normalized_amount = str(Decimal(str(amount)).quantize(Decimal("0.01")))
    errors: list[str] = []

    # Some CryptoBot tokens reject pinned checks, so try both variants.
    for payload in (
        {"asset": asset, "amount": normalized_amount, "pin_to_user_id": supplier_id},
        {"asset": asset, "amount": normalized_amount},
    ):
        try:
            data = await _raw_crypto_pay_request("createCheck", payload)
            link = _extract_check_link(data)
            check_id = _extract_check_id(data)
            if link or check_id:
                return link, check_id
            errors.append(f"empty createCheck response: {data}")
        except Exception as exc:
            errors.append(str(exc))

    try:
        from app.cryptopay_service import crypto_client
        try:
            check = await crypto_client().create_check(
                asset=asset,
                amount=float(amount),
                pin_to_user_id=supplier_id,
            )
        except TypeError:
            check = await crypto_client().create_check(
                asset=asset,
                amount=float(amount),
            )
        data = _obj_to_dict(check)
        link = _extract_check_link(data)
        check_id = _extract_check_id(data)
        if link or check_id:
            return link, check_id
        errors.append(f"empty library response: {data}")
    except Exception as exc:
        errors.append(str(exc))

    raise RuntimeError("; ".join(errors[-3:]) or "CryptoBot createCheck failed")


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
    kb.adjust(2)
    return kb.as_markup()


def supplier_wallet_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Мои заказы", callback_data="supplier:filter:all:0")
    kb.button(text="💼 Баланс", callback_data="supplier:wallet")
    kb.button(text="↗️ Вывод", callback_data="supplier:withdraw_help")
    kb.button(text="🏠 Режим покупателя", callback_data="buyer:panel")
    kb.adjust(2)
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
                    # V70: поставщик получает не всю сумму продажи, а фиксированную сумму,
                    # указанную админом при привязке поставщика к товару.
                    payout_amount = getattr(provider, "supplier_payout_amount", None)
                    payout_currency = getattr(provider, "supplier_payout_currency", None) or purchase.currency
                    qty = max(1, int(getattr(purchase, "quantity", 1) or 1))
                    if payout_amount is None:
                        # Legacy fallback for old bindings: old records used the full order amount.
                        payout_amount = purchase.amount
                    else:
                        # New bindings store supplier payout per 1 unit, so multiply by quantity.
                        payout_amount = money(payout_amount) * qty
                    existing_ledger = await session.scalar(
                        select(WalletLedger).where(
                            WalletLedger.user_id == supplier_id,
                            WalletLedger.event_type == "supplier_sale",
                            WalletLedger.source_type == "purchase",
                            WalletLedger.source_id == purchase.id,
                        )
                    )
                    if existing_ledger is None:
                        await add_wallet_balance(
                            session,
                            supplier_id,
                            payout_amount,
                            payout_currency,
                            "supplier_sale",
                            source_type="purchase",
                            source_id=purchase.id,
                            note=f"Продажа товара {product.name}",
                        )
                        await session.commit()
        username = purchase.buyer_username or ""
        product_name = product.name if product else f"Товар #{purchase.product_id}"
        bot_username = (await bot.me()).username or ""
        product_link = f"https://t.me/{bot_username}?start=admproduct_{product.internal_key}" if bot_username and product else ""
        tech = (
            f"операция {purchase.id} · invoice {payment.invoice_id if payment else '—'} · "
            f"payment {payment.id if payment else '—'} · product {purchase.product_id} · "
            f"status {purchase.status}"
        )
        text = (
            "💰 Новая покупка через CryptoBot!\n\n"
            f"👤 Пользователь: {user_label(purchase.buyer_id, username)}\n"
            f"🆔 ID: {purchase.buyer_id}\n"
            f"📦 Купил: {product_name}" + (f"\n{product_link}" if product_link else "") + "\n"
            f"💵 Сумма: {money_text(purchase.amount, purchase.currency)}\n\n"
            f"📋 Техника: {tech}"
        )
    for admin_id in admin_recipients():
        await safe_send_message(bot, admin_id, text)
    if supplier_id:
        payout_line = ""
        try:
            payout_amount = getattr(provider, "supplier_payout_amount", None)
            payout_currency = getattr(provider, "supplier_payout_currency", None) or purchase.currency
            qty = max(1, int(getattr(purchase, "quantity", 1) or 1))
            if payout_amount is not None:
                payout_amount = money(payout_amount) * qty
                qty_note = f" × {qty}" if qty > 1 else ""
                payout_line = f"\n✅ Начислено: {money_text(payout_amount, payout_currency)}{qty_note}"
        except Exception:
            payout_line = ""
        supplier_text = (
            "💰 Продажа вашего товара!\n\n"
            f"📦 Товар: {product_name}\n"
            f"💵 Сумма продажи: {money_text(purchase.amount, purchase.currency)}"
            f"{payout_line}\n\n"
            "Покупатель скрыт магазином."
        )
        await safe_send_message(bot, supplier_id, supplier_text)


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


async def create_withdrawal_request(supplier_id: int, raw: str, asset: str | None = None) -> str:
    """Create supplier withdrawal.

    V77: CryptoBot checks do not need a payout address. Supplier may send:
    - "10"
    - "10 USDT"
    - "10 UQ..." (legacy, address is kept as note only)
    - "всё" / "all" / "вывести всё"
    """
    raw_text = (raw or "").strip()
    payout_asset = (asset or WITHDRAW_PAYOUT_ASSET or "USDT").upper()
    parts = raw_text.split()
    if not parts:
        return (
            "↗️ Вывод средств\n\n"
            "Отправьте сумму одним сообщением или нажмите «💰 Вывести всё».\n"
            "Пример: 10\n\n"
            "Адрес для CryptoBot-чека не нужен — бот создаёт ссылку на чек."
        )

    payout_address = None
    all_requested = raw_text.lower() in {"all", "всё", "все", "вывести всё", "вывести все", "max", "макс", "баланс"}
    fee = money(WITHDRAWAL_FEE_USD)

    async with SessionLocal() as session:
        wallet = await session.get(UserWallet, supplier_id)
        wallet_balance = money(wallet.balance if wallet else 0)
        wallet_currency = (wallet.currency if wallet else payout_asset) or payout_asset

    if all_requested:
        amount = wallet_balance
    else:
        try:
            amount = money(parts[0].replace(",", "."))
        except Exception:
            return (
                "Неверная сумма.\n\n"
                "Введите только сумму, например: 10\n"
                "Или нажмите «💰 Вывести всё»."
            )
        # Legacy compatibility: second token may be address or asset.
        if len(parts) >= 2:
            second = parts[1].strip()
            if second.upper() in {"USDT", "TON", "BTC", "ETH", "LTC", "TRX", "BNB", "USDC"}:
                payout_asset = second.upper()
            else:
                payout_address = second
        if len(parts) >= 3 and parts[2].strip().upper() in {"USDT", "TON", "BTC", "ETH", "LTC", "TRX", "BNB", "USDC"}:
            payout_asset = parts[2].strip().upper()

    if amount <= 0:
        return "Сумма должна быть больше нуля."
    if amount <= fee:
        return f"Минимальная сумма должна быть больше комиссии вывода {money_text(fee, payout_asset)}."
    net_amount = money(amount - fee)

    async with SessionLocal() as session:
        wallet = await session.get(UserWallet, supplier_id)
        if not wallet or money(wallet.balance) < amount:
            return f"Недостаточно средств. Баланс: {money_text(wallet.balance if wallet else 0, (wallet.currency if wallet else payout_asset))}"
        wallet.balance = money(wallet.balance) - amount
        wallet.updated_at = datetime.utcnow()
        wallet.currency = payout_asset
        wd = SupplierWithdrawal(
            supplier_id=supplier_id,
            amount=amount,
            currency=payout_asset,
            payout_address=payout_address,
            status="pending",
        )
        session.add(wd)
        await session.flush()
        session.add(WalletLedger(
            user_id=supplier_id,
            amount=-amount,
            currency=payout_asset,
            event_type="withdraw_hold",
            source_type="withdrawal",
            source_id=wd.id,
            note=f"crypto_check; fee={fee}; net={net_amount}; legacy_address={payout_address or ''}",
        ))
        await session.commit()
        await session.refresh(wd)
        withdrawal_id = wd.id

    if WITHDRAW_AUTO_CRYPTOBOT:
        try:
            link, check_id = await _create_cryptobot_withdraw_check(
                supplier_id=supplier_id,
                amount=net_amount,
                asset=payout_asset,
            )
            async with SessionLocal() as session:
                wd = await session.get(SupplierWithdrawal, withdrawal_id)
                if wd:
                    wd.status = "paid"
                    wd.payout_link = str(link or check_id or "")
                    wd.updated_at = datetime.utcnow()
                    await session.commit()
            return (
                f"✅ Чек CryptoBot создан\n\n"
                f"Заявка: #{withdrawal_id}\n"
                f"Списано с баланса: {money_text(amount, payout_asset)}\n"
                f"Комиссия: {money_text(fee, payout_asset)}\n"
                f"К выплате: {money_text(net_amount, payout_asset)}\n\n"
                f"🔗 Ссылка на чек:\n{link or check_id or 'ссылка не получена'}"
            )
        except Exception as exc:
            async with SessionLocal() as session:
                wd = await session.get(SupplierWithdrawal, withdrawal_id)
                if wd:
                    wd.status = "manual_review"
                    wd.note = f"autocheck_failed: {exc}"[:900]
                    wd.updated_at = datetime.utcnow()
                    await session.commit()
            return (
                f"✅ Заявка на вывод #{withdrawal_id} создана и отправлена администратору.\n\n"
                f"Списано с баланса: {money_text(amount, payout_asset)}\n"
                f"Комиссия: {money_text(fee, payout_asset)}\n"
                f"К выплате: {money_text(net_amount, payout_asset)}\n\n"
                "⚠️ Авточек CryptoBot не создался. Администратор увидит заявку и нажмёт «✅ Одобрить» после ручной выплаты или «❌ Отклонить» для возврата средств."
            )

    return (
        f"✅ Заявка на вывод #{withdrawal_id} создана.\n\n"
        f"Списано с баланса: {money_text(amount, payout_asset)}\n"
        f"Комиссия: {money_text(fee, payout_asset)}\n"
        f"К выплате: {money_text(net_amount, payout_asset)}\n\n"
        "Администратор отправит выплату вручную."
    )


async def admin_withdrawals_text() -> str:
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(SupplierWithdrawal).order_by(SupplierWithdrawal.id.desc()).limit(20))).all())
    if not rows:
        return "↗️ Заявок на вывод нет."
    status_label = {
        "pending": "⏳ ожидает",
        "manual_review": "🟠 ручная модерация",
        "paid": "✅ выплачено",
        "rejected": "❌ отклонено",
    }
    lines = ["↗️ Заявки на вывод", ""]
    for r in rows:
        fee = money(WITHDRAWAL_FEE_USD)
        net = money(r.amount) - fee if money(r.amount) > fee else money(0)
        lines.append(
            f"#{r.id} — поставщик {r.supplier_id}\n"
            f"• статус: {status_label.get(r.status, r.status)}\n"
            f"• сумма: {money_text(r.amount, r.currency)}\n"
            f"• к выплате: {money_text(net, r.currency)}\n"
            f"• чек/TX: {r.payout_link or 'нет'}"
        )
    lines.append("\nДля ручных заявок используйте кнопки «✅ Одобрить» или «❌ Отклонить».")
    return "\n\n".join(lines)


async def reject_withdrawal_request(bot: Bot, admin_id: int, withdrawal_id: int, reason: str | None = None) -> str:
    async with SessionLocal() as session:
        wd = await session.get(SupplierWithdrawal, withdrawal_id)
        if not wd:
            return "Заявка не найдена."
        if wd.status in {"paid", "rejected"}:
            return f"Заявка уже обработана: {wd.status}."
        wd.status = "rejected"
        wd.admin_id = admin_id
        wd.note = ((wd.note or "") + f"\nrejected: {reason or 'manual'}")[:900]
        wd.updated_at = datetime.utcnow()
        wallet = await session.get(UserWallet, wd.supplier_id)
        if wallet is None:
            wallet = UserWallet(user_id=wd.supplier_id, balance=0, currency=wd.currency)
            session.add(wallet)
            await session.flush()
        wallet.balance = money(wallet.balance) + money(wd.amount)
        wallet.currency = wd.currency
        wallet.updated_at = datetime.utcnow()
        session.add(WalletLedger(
            user_id=wd.supplier_id,
            amount=money(wd.amount),
            currency=wd.currency,
            event_type="withdraw_reject_refund",
            source_type="withdrawal",
            source_id=wd.id,
            note=reason or "manual reject",
        ))
        await session.commit()
        supplier_id = wd.supplier_id
        amount_text = money_text(wd.amount, wd.currency)
    await safe_send_message(
        bot,
        supplier_id,
        "❌ Заявка на вывод отклонена\n\n"
        f"Заявка: #{withdrawal_id}\n"
        f"Возвращено на баланс: {amount_text}\n"
        f"Причина: {reason or 'ручная проверка администратора'}"
    )
    return f"❌ Вывод #{withdrawal_id} отклонён. Средства возвращены поставщику: {amount_text}."


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
        f"Сумма: {money_text(wd.amount, wd.currency)}\n"
        f"Ссылка/TX: {link or 'не указан'}"
    )
    return f"✅ Вывод #{wid} отмечен как выплаченный. Ссылка/TX: {link or 'не указан'}"

# V51 wallet visual override.
async def get_wallet_text(user_id: int) -> str:
    async with SessionLocal() as session:
        wallet = await session.get(UserWallet, user_id)
        rows = list((await session.scalars(select(WalletLedger).where(WalletLedger.user_id == user_id).order_by(WalletLedger.id.desc()).limit(5))).all())
    balance = money(wallet.balance if wallet else 0)
    currency = (wallet.currency if wallet else "USD") or "USD"
    lines = [
        "💼 Кошелёк магазина",
        "",
        f"💰 Баланс: {balance} {currency}",
        "",
        "Баланс можно использовать для покупок и выплат поставщикам.",
    ]
    if rows:
        lines += ["", "📋 Последние операции:"]
        for r in rows:
            sign = "+" if money(r.amount) >= 0 else ""
            lines.append(f"{sign}{money(r.amount)} {r.currency} · {r.event_type}")
    return "\n".join(lines)


def wallet_keyboard(is_supplier: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Пополнить", callback_data="wallet:topup_help")
    kb.button(text="🔄 Обновить", callback_data="buyer:wallet")
    if is_supplier:
        kb.button(text="↗️ Вывести", callback_data="supplier:withdraw_help")
    kb.button(text="🏠 Главная", callback_data="buyer:panel")
    kb.adjust(2, 1, 1)
    return kb.as_markup()
