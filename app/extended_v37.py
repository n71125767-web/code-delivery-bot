from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ADMIN_ALERT_CHAT_IDS, GA_IDS
from app.database import SessionLocal
from app.models import (
    AdminUser,
    ConversationState,
    CooldownSetting,
    CustomerTrophy,
    DigitalPurchase,
    InternalRewardEvent,
    MarketplaceApplication,
    ManualPage,
    ProductStockItem,
    ProductProvider,
    PromoCode,
    PromoRedemption,
    ShopCategory,
    ShopProduct,
    WalletPayment,
)
from app.proxy_pricing_v39 import (
    apply_proxy_markup,
    get_proxy_markup_multiplier,
    multiplier_label,
    set_proxy_markup_multiplier,
)
from app.senders import answer_message, safe_send_message

PROMO_SCOPE = "active_promo"
MIN_PAYMENT_AMOUNT = Decimal("0.10")


def _now() -> datetime:
    return datetime.utcnow()


def _money(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _split_pipe(text: str, maxsplit: int = -1) -> list[str]:
    return [part.strip() for part in text.split("|", maxsplit) if part.strip()]


def _period_bounds(period: str) -> tuple[datetime | None, str]:
    period = (period or "all").lower()
    if period in {"week", "неделя", "7"}:
        return _now() - timedelta(days=7), "за неделю"
    if period in {"month", "месяц", "30"}:
        return _now() - timedelta(days=30), "за месяц"
    return None, "за всё время"


def marketplace_moderation_keyboard(application_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"market:approve:{application_id}")
    kb.button(text="❌ Отклонить", callback_data=f"market:reject:{application_id}")
    kb.adjust(1)
    return kb.as_markup()


def wallet_payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Проверить оплату", callback_data=f"wallet:check:{payment_id}")
    kb.button(text="🧾 Мои заказы", callback_data="buyer:orders")
    kb.button(text="🏠 Главное меню", callback_data="buyer:panel")
    kb.adjust(1)
    return kb.as_markup()


async def _next_internal_key(session: AsyncSession) -> int:
    current = await session.scalar(select(func.max(ShopProduct.internal_key)))
    base = int(current or 10_000)
    return max(base + 1, 10_001)


async def _get_or_create_market_category(session: AsyncSession, name: str = "Маркетплейс") -> ShopCategory:
    category = await session.scalar(select(ShopCategory).where(ShopCategory.name == name))
    if category:
        return category
    category = ShopCategory(name=name, emoji="🛍", description="Товары от продавцов после модерации", is_active=True)
    session.add(category)
    await session.flush()
    return category


async def _store_active_promo(session: AsyncSession, user_id: int, code: str) -> None:
    row = await session.get(ConversationState, {"user_id": user_id, "scope": PROMO_SCOPE})
    payload = json.dumps({"code": code.upper(), "created_at": _now().isoformat()}, ensure_ascii=False)
    if row:
        row.payload_json = payload
        row.expires_at = _now() + timedelta(days=7)
        row.updated_at = _now()
    else:
        session.add(
            ConversationState(
                user_id=user_id,
                scope=PROMO_SCOPE,
                payload_json=payload,
                expires_at=_now() + timedelta(days=7),
            )
        )


async def _active_promo_code(session: AsyncSession, user_id: int) -> str | None:
    row = await session.get(ConversationState, {"user_id": user_id, "scope": PROMO_SCOPE})
    if not row:
        return None
    if row.expires_at and row.expires_at < _now():
        await session.delete(row)
        await session.flush()
        return None
    try:
        payload = json.loads(row.payload_json or "{}")
    except Exception:
        return None
    return str(payload.get("code") or "").strip().upper() or None


async def get_active_promo_discount(
    session: AsyncSession,
    buyer_id: int,
    product_id: int,
    amount: Decimal,
    currency: str,
) -> tuple[str | None, Decimal, Decimal]:
    """Return (promo_code, final_amount, discount_amount) for buyer's active promo."""
    code = await _active_promo_code(session, buyer_id)
    if not code:
        return None, amount, Decimal("0")

    promo = await session.scalar(select(PromoCode).where(PromoCode.code == code, PromoCode.is_active.is_(True)))
    if not promo:
        return None, amount, Decimal("0")
    if promo.expires_at and promo.expires_at < _now():
        return None, amount, Decimal("0")
    if promo.max_uses is not None and int(promo.used_count or 0) >= int(promo.max_uses):
        return None, amount, Decimal("0")
    if promo.product_id is not None and int(promo.product_id) != int(product_id):
        return None, amount, Decimal("0")

    value = _money(promo.value)
    if promo.discount_type == "percent":
        discount = (amount * value / Decimal("100")).quantize(Decimal("0.01"))
    else:
        discount = value.quantize(Decimal("0.01"))
    if discount <= 0:
        return None, amount, Decimal("0")
    if discount >= amount:
        discount = max(Decimal("0"), amount - MIN_PAYMENT_AMOUNT)
    final_amount = max(MIN_PAYMENT_AMOUNT, (amount - discount).quantize(Decimal("0.01")))
    discount = (amount - final_amount).quantize(Decimal("0.01"))
    return promo.code, final_amount, discount


async def finalize_promo_redemption(session: AsyncSession, purchase: DigitalPurchase) -> None:
    code = (getattr(purchase, "promo_code", None) or "").strip().upper()
    if not code:
        return
    exists = await session.scalar(
        select(PromoRedemption).where(PromoRedemption.purchase_id == purchase.id).limit(1)
    )
    if exists:
        return
    promo = await session.scalar(select(PromoCode).where(PromoCode.code == code))
    if not promo:
        return
    promo.used_count = int(promo.used_count or 0) + 1
    session.add(
        PromoRedemption(
            promo_id=promo.id,
            code=promo.code,
            user_id=purchase.buyer_id,
            purchase_id=purchase.id,
            discount_amount=getattr(purchase, "discount_amount", None) or 0,
        )
    )


async def award_purchase_trophies(session: AsyncSession, buyer_id: int) -> list[str]:
    delivered_count = int(
        await session.scalar(
            select(func.count(DigitalPurchase.id)).where(
                DigitalPurchase.buyer_id == buyer_id,
                DigitalPurchase.status == "delivered",
            )
        ) or 0
    )
    total_spent = _money(
        await session.scalar(
            select(func.coalesce(func.sum(DigitalPurchase.amount), 0)).where(
                DigitalPurchase.buyer_id == buyer_id,
                DigitalPurchase.status == "delivered",
            )
        )
    )
    rules = [
        ("first_buy", "Первый заказ", "Клиент сделал первую покупку", delivered_count >= 1),
        ("five_buys", "5 покупок", "Клиент сделал 5 успешных покупок", delivered_count >= 5),
        ("ten_buys", "10 покупок", "Клиент сделал 10 успешных покупок", delivered_count >= 10),
        ("vip_spender", "VIP покупатель", "Сумма покупок достигла 10 000", total_spent >= Decimal("10000")),
    ]
    awarded: list[str] = []
    for key, title, description, condition in rules:
        if not condition:
            continue
        exists = await session.scalar(
            select(CustomerTrophy).where(
                CustomerTrophy.user_id == buyer_id,
                CustomerTrophy.trophy_key == key,
            )
        )
        if exists:
            continue
        session.add(CustomerTrophy(user_id=buyer_id, trophy_key=key, title=title, description=description))
        awarded.append(title)
    return awarded


async def get_cooldown_seconds(session: AsyncSession, action: str, default_seconds: int) -> int:
    row = await session.scalar(select(CooldownSetting).where(CooldownSetting.action == action))
    if not row:
        return default_seconds
    return max(0, int(row.seconds or 0))


async def apply_internal_reward(session: AsyncSession, user_id: int, event_type: str, points: int, source_id: int | None = None) -> None:
    if points <= 0:
        return
    session.add(InternalRewardEvent(user_id=user_id, event_type=event_type, points=points, source_id=source_id))


async def stats_full_text(session: AsyncSession) -> str:
    products = int(await session.scalar(select(func.count(ShopProduct.id)).where(ShopProduct.is_deleted.is_(False))) or 0)
    active_products = int(await session.scalar(select(func.count(ShopProduct.id)).where(ShopProduct.is_deleted.is_(False), ShopProduct.is_active.is_(True))) or 0)
    categories = int(await session.scalar(select(func.count(ShopCategory.id))) or 0)
    pending_apps = int(await session.scalar(select(func.count(MarketplaceApplication.id)).where(MarketplaceApplication.status == "pending")) or 0)
    delivered = int(await session.scalar(select(func.count(DigitalPurchase.id)).where(DigitalPurchase.status == "delivered")) or 0)
    failed = int(await session.scalar(select(func.count(DigitalPurchase.id)).where(DigitalPurchase.status.in_(("delivery_failed", "delivery_review_required")))) or 0)
    revenue = _money(await session.scalar(select(func.coalesce(func.sum(DigitalPurchase.amount), 0)).where(DigitalPurchase.status == "delivered")))
    promos = int(await session.scalar(select(func.count(PromoCode.id)).where(PromoCode.is_active.is_(True))) or 0)
    wallet_pending = int(await session.scalar(select(func.count(WalletPayment.id)).where(WalletPayment.status == "pending")) or 0)
    return (
        "📊 Статистика магазина\n\n"
        f"Категорий: {categories}\n"
        f"Товаров: {products}\n"
        f"Активных товаров: {active_products}\n"
        f"Успешных покупок: {delivered}\n"
        f"Проблемных выдач: {failed}\n"
        f"Выручка: {revenue}\n"
        f"Активных промокодов: {promos}\n"
        f"Заявок маркетплейса на модерации: {pending_apps}\n"
        f"Ожидают оплату на кошелёк: {wallet_pending}"
    )


async def product_stats_text(session: AsyncSession, product_id: int) -> str:
    product = await session.get(ShopProduct, product_id)
    if not product:
        return "Товар не найден."
    purchases = int(await session.scalar(select(func.count(DigitalPurchase.id)).where(DigitalPurchase.product_id == product_id)) or 0)
    delivered = int(await session.scalar(select(func.count(DigitalPurchase.id)).where(DigitalPurchase.product_id == product_id, DigitalPurchase.status == "delivered")) or 0)
    revenue = _money(await session.scalar(select(func.coalesce(func.sum(DigitalPurchase.amount), 0)).where(DigitalPurchase.product_id == product_id, DigitalPurchase.status == "delivered")))
    stock_total = int(await session.scalar(select(func.count(ProductStockItem.id)).where(ProductStockItem.product_id == product_id)) or 0)
    stock_available = int(await session.scalar(select(func.count(ProductStockItem.id)).where(ProductStockItem.product_id == product_id, ProductStockItem.status == "available")) or 0)
    return (
        f"📦 Статистика товара #{product.id}\n\n"
        f"Название: {product.name}\n"
        f"Выдача: {product.fulfillment_type}\n"
        f"Просмотров: {product.views_count or 0}\n"
        f"Покупок всего: {purchases}\n"
        f"Успешно выдано: {delivered}\n"
        f"Выручка: {revenue} {product.currency}\n"
        f"Склад: {stock_available}/{stock_total}\n"
        f"Статус: {'активен' if product.is_active else 'скрыт'}"
    )


async def top_buyers_text(session: AsyncSession, period: str) -> str:
    since, label = _period_bounds(period)
    conditions = [DigitalPurchase.status == "delivered"]
    if since:
        conditions.append(DigitalPurchase.delivered_at >= since)
    rows = (
        await session.execute(
            select(
                DigitalPurchase.buyer_id,
                func.count(DigitalPurchase.id),
                func.coalesce(func.sum(DigitalPurchase.amount), 0),
            )
            .where(*conditions)
            .group_by(DigitalPurchase.buyer_id)
            .order_by(func.count(DigitalPurchase.id).desc(), func.sum(DigitalPurchase.amount).desc())
            .limit(10)
        )
    ).all()
    if not rows:
        return f"🏆 Топ покупателей {label}\n\nПока нет успешных покупок."
    lines = [f"🏆 Топ покупателей {label}", ""]
    for i, (buyer_id, count, amount) in enumerate(rows, start=1):
        lines.append(f"{i}. {buyer_id} — {count} покупок, сумма {amount}")
    return "\n".join(lines)


async def trophies_text(session: AsyncSession, user_id: int) -> str:
    rows = list((await session.scalars(select(CustomerTrophy).where(CustomerTrophy.user_id == user_id).order_by(CustomerTrophy.awarded_at.desc()))).all())
    points = int(await session.scalar(select(func.coalesce(func.sum(InternalRewardEvent.points), 0)).where(InternalRewardEvent.user_id == user_id)) or 0)
    if not rows:
        return f"🏆 Ваши трофеи\n\nПока трофеев нет. Баллы: {points}."
    lines = [f"🏆 Ваши трофеи\n\nБаллы: {points}", ""]
    for row in rows:
        lines.append(f"• {row.title} — {row.description}")
    return "\n".join(lines)


async def _create_stock_items(session: AsyncSession, product_id: int, text: str, content_type: str = "text") -> int:
    product = await session.get(ShopProduct, product_id)
    if not product:
        raise ValueError("Товар не найден")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Нет позиций для загрузки")
    for line in lines:
        session.add(ProductStockItem(product_id=product.id, content_type=content_type, content_text=line, status="available"))
    product.product_type = "quantity"
    if product.fulfillment_type not in {"number", "proxy_stock"}:
        product.fulfillment_type = "stock"
    product.payment_enabled = True
    product.updated_at = _now()
    await session.commit()
    return len(lines)


PROXY_AUTOFIX_PRODUCTS = [
    ("mtproxy", "🧩 MTProxy", "Прокси для Telegram/MTProxy"),
    ("premium", "💎 Премиум прокси", "Премиум-прокси с автовыдачей через Proxyline"),
    ("standard", "📦 Стандартные прокси", "Стандартные прокси с автовыдачей через Proxyline"),
    ("residential", "🏠 Резидентские прокси", "Резидентские прокси с автовыдачей через Proxyline"),
]


async def ensure_proxy_autofix_products(session: AsyncSession, price: Decimal, currency: str) -> list[ShopProduct]:
    category = await session.scalar(select(ShopCategory).where(ShopCategory.name == "Прокси"))
    if not category:
        category = ShopCategory(
            name="Прокси",
            emoji="🌐",
            description="Автоматическая выдача прокси через Proxyline",
            is_active=True,
        )
        session.add(category)
        await session.flush()
    else:
        category.emoji = "🌐"
        category.description = category.description or "Автоматическая выдача прокси через Proxyline"
        category.is_active = True

    created_or_updated: list[ShopProduct] = []
    for sort_index, (key, name, description) in enumerate(PROXY_AUTOFIX_PRODUCTS, start=10):
        note = f"proxy_autofix:{key}"
        product = await session.scalar(select(ShopProduct).where(ShopProduct.note == note))
        if not product:
            product = ShopProduct(
                internal_key=await _next_internal_key(session),
                note=note,
                created_at=_now(),
            )
            session.add(product)
            await session.flush()
        product.category_id = category.id
        product.name = name
        product.description = description
        product.price = price
        product.currency = currency.upper()[:10]
        product.product_type = "static"
        product.fulfillment_type = "proxyline"
        product.provider_key = json.dumps(
            {"type": "dedicated", "count": 1, "ip_version": 4},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        product.content_type = "text"
        product.content_text = "Автовыдача через Proxyline после оплаты."
        product.payment_enabled = True
        product.is_active = True
        product.is_deleted = False
        product.sort_order = sort_index
        product.updated_at = _now()

        provider = await session.scalar(
            select(ProductProvider).where(ProductProvider.internal_key == product.internal_key)
        )
        if not provider:
            provider = ProductProvider(internal_key=product.internal_key)
            session.add(provider)
        provider.product_name = product.name
        provider.provider_type = "proxyline"
        provider.provider_key = product.provider_key
        provider.enabled = True
        provider.updated_at = _now()
        created_or_updated.append(product)

    await session.commit()
    return created_or_updated


async def process_extended_command(
    bot: Bot,
    message: Message,
    business_connection_id: str | None,
    *,
    is_admin: bool,
    is_super_admin: bool = False,
) -> bool:
    if not message.from_user:
        return False
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return False
    command = text.split(maxsplit=1)[0].lower()
    arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
    user_id = message.from_user.id
    username = message.from_user.username

    if command == "/my_id":
        await answer_message(bot, message, f"Ваш Telegram ID: {user_id}", business_connection_id)
        return True

    if command == "/market_apply":
        parts = _split_pipe(arg, 4)
        if len(parts) < 5:
            await answer_message(
                bot,
                message,
                "Формат заявки:\n/market_apply Название | Цена | Валюта | Категория | Описание",
                business_connection_id,
            )
            return True
        title, price_raw, currency, category_name, description = parts
        try:
            price = _parse_decimal(price_raw)
        except InvalidOperation:
            await answer_message(bot, message, "Цена должна быть числом.", business_connection_id)
            return True
        async with SessionLocal() as session:
            app = MarketplaceApplication(
                applicant_telegram_id=user_id,
                applicant_username=username,
                seller_name=username or str(user_id),
                title=title[:255],
                description=description,
                price=price,
                currency=currency.upper()[:10],
                category_name=category_name[:120],
                status="pending",
            )
            session.add(app)
            await session.commit()
            await session.refresh(app)
        await answer_message(bot, message, f"✅ Заявка #{app.id} отправлена на модерацию.", business_connection_id)
        for admin_chat_id in ADMIN_ALERT_CHAT_IDS:
            await safe_send_message(
                bot,
                admin_chat_id,
                "🛍 Новая заявка в маркетплейс\n\n"
                f"ID: {app.id}\n"
                f"Пользователь: {user_id} @{username or 'нет'}\n"
                f"Товар: {title}\n"
                f"Цена: {price} {currency.upper()}\n"
                f"Категория: {category_name}\n\n"
                f"{description}",
                reply_markup=marketplace_moderation_keyboard(app.id),
            )
        return True

    if command == "/promo":
        if not arg:
            await answer_message(bot, message, "Формат: /promo CODE", business_connection_id)
            return True
        code = arg.split()[0].upper()
        async with SessionLocal() as session:
            promo = await session.scalar(select(PromoCode).where(PromoCode.code == code, PromoCode.is_active.is_(True)))
            if not promo or (promo.expires_at and promo.expires_at < _now()):
                await answer_message(bot, message, "Промокод не найден или истёк.", business_connection_id)
                return True
            await _store_active_promo(session, user_id, code)
            await session.commit()
        await answer_message(bot, message, f"✅ Промокод {code} применён к следующей покупке.", business_connection_id)
        return True

    if command == "/top_buyers":
        period = arg or "all"
        async with SessionLocal() as session:
            result = await top_buyers_text(session, period)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/trophies":
        async with SessionLocal() as session:
            result = await trophies_text(session, user_id)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/bot_avatar":
        await answer_message(
            bot,
            message,
            "🖼 Аватар бота\n\nTelegram Bot API не даёт боту менять свою аву из кода. "
            "Загрузите аватар через @BotFather → /mybots → Bot Settings → Edit Botpic.\n\n"
            "Картинки категорий и карточек товаров уже поддерживаются через админку: фото категории/товара сохраняется как file_id.",
            business_connection_id,
        )
        return True

    if not is_admin:
        return False

    if command in {"/v37_help", "/features"}:
        await answer_message(
            bot,
            message,
            "🧩 V37 команды\n\n"
            "Маркетплейс: /market_applications, /market_approve ID [CATEGORY_ID], /market_reject ID причина\n"
            "Товары: /product_add Название | Цена | Валюта | CATEGORY_ID | Контент, /product_delete ID, /stock_add ID позиции\n"
            "Номера/прокси со склада: /number_stock_add ID позиции, /proxy_stock_add ID позиции\n"
            "Прокси: /proxy_autofix 100 RUB, /proxy_markup 1.77, /proxy_price 100 RUB\n"
            "Промо: /promo_create CODE percent|fixed VALUE MAX_USES [YYYY-MM-DD] [PRODUCT_ID], /promos, /promo_disable CODE\n"
            "Статистика: /stats_full, /stats_product ID, /top_buyers week|month|all\n"
            "КД: /cooldowns, /set_cooldown ACTION SECONDS\n"
            "Мануалы: /manual_add Заголовок | Текст, /manuals\n"
            "ГА: /my_id, /grant_ga TELEGRAM_ID Имя",
            business_connection_id,
        )
        return True

    if command == "/proxy_autofix":
        parts = arg.split()
        try:
            price = _parse_decimal(parts[0]) if parts else Decimal("100")
            currency = parts[1].upper() if len(parts) > 1 else "RUB"
        except Exception:
            await answer_message(bot, message, "Формат: /proxy_autofix [PRICE] [CURRENCY]  пример: /proxy_autofix 100 RUB", business_connection_id)
            return True
        if price <= 0:
            await answer_message(bot, message, "Цена должна быть больше 0.", business_connection_id)
            return True
        async with SessionLocal() as session:
            rows = await ensure_proxy_autofix_products(session, price, currency)
            markup = await get_proxy_markup_multiplier(session)
            final_month = apply_proxy_markup(price, markup)
        lines = [
            "✅ Proxyline-товары созданы/обновлены.",
            "",
            f"База за 1 месяц: {price} {currency.upper()}",
            f"Наценка: {multiplier_label(markup)}",
            f"Цена покупателю за 1 месяц: {final_month} {currency.upper()}",
            "",
            "Активные товары:",
        ]
        lines.extend(f"#{row.id} — {row.name}" for row in rows)
        lines.append("")
        lines.append("Теперь покупатель может открыть: 🌐 Прокси → тип → страна → срок.")
        await answer_message(bot, message, "\n".join(lines), business_connection_id)
        return True

    if command == "/proxy_markup":
        parts = arg.split()
        if not parts:
            async with SessionLocal() as session:
                markup = await get_proxy_markup_multiplier(session)
            await answer_message(
                bot,
                message,
                f"💹 Текущая наценка прокси: {multiplier_label(markup)}\n\nИзменить: /proxy_markup 1.77",
                business_connection_id,
            )
            return True
        try:
            async with SessionLocal() as session:
                markup = await set_proxy_markup_multiplier(session, parts[0])
                await session.commit()
        except Exception as exc:
            await answer_message(bot, message, f"Не удалось сохранить наценку: {exc}", business_connection_id)
            return True
        await answer_message(
            bot,
            message,
            f"✅ Наценка прокси сохранена: {multiplier_label(markup)}\n\nБазовые цены товаров не менялись, меняется только финальная цена для покупателя.",
            business_connection_id,
        )
        return True

    if command == "/proxy_price":
        parts = arg.split()
        try:
            price = _parse_decimal(parts[0])
            currency = parts[1].upper() if len(parts) > 1 else "RUB"
        except Exception:
            await answer_message(bot, message, "Формат: /proxy_price 100 RUB", business_connection_id)
            return True
        if price <= 0:
            await answer_message(bot, message, "Базовая цена должна быть больше 0.", business_connection_id)
            return True
        async with SessionLocal() as session:
            rows = await ensure_proxy_autofix_products(session, price, currency)
            markup = await get_proxy_markup_multiplier(session)
            final_month = apply_proxy_markup(price, markup)
        await answer_message(
            bot,
            message,
            "✅ Базовая цена Proxyline-товаров обновлена.\n\n"
            f"База: {price} {currency.upper()}\n"
            f"Наценка: {multiplier_label(markup)}\n"
            f"Покупателю за 1 месяц: {final_month} {currency.upper()}\n"
            f"Обновлено товаров: {len(rows)}",
            business_connection_id,
        )
        return True

    if command == "/market_applications":
        async with SessionLocal() as session:
            rows = list((await session.scalars(select(MarketplaceApplication).where(MarketplaceApplication.status == "pending").order_by(MarketplaceApplication.id.desc()).limit(20))).all())
        if not rows:
            result = "🛍 Заявок на модерации нет."
        else:
            lines = ["🛍 Заявки маркетплейса на модерации", ""]
            for row in rows:
                lines.append(f"#{row.id} — {row.title} — {row.price} {row.currency} — @{row.applicant_username or row.applicant_telegram_id}")
            lines.append("\nПодтвердить: /market_approve ID [CATEGORY_ID]\nОтклонить: /market_reject ID причина")
            result = "\n".join(lines)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/market_approve":
        parts = arg.split()
        if not parts or not parts[0].isdigit():
            await answer_message(bot, message, "Формат: /market_approve ID [CATEGORY_ID]", business_connection_id)
            return True
        app_id = int(parts[0])
        category_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        async with SessionLocal() as session:
            app = await session.get(MarketplaceApplication, app_id)
            if not app or app.status != "pending":
                await answer_message(bot, message, "Заявка не найдена или уже обработана.", business_connection_id)
                return True
            category = await session.get(ShopCategory, category_id) if category_id else await _get_or_create_market_category(session, app.category_name or "Маркетплейс")
            product = ShopProduct(
                internal_key=await _next_internal_key(session),
                category_id=category.id,
                name=app.title,
                description=(app.description or "") + f"\n\nПродавец: @{app.applicant_username or app.applicant_telegram_id}",
                price=app.price,
                currency=app.currency,
                product_type="static",
                fulfillment_type="digital",
                content_type="text",
                content_text="Товар одобрен маркетплейсом. Администратор должен настроить выдачу перед включением продаж.",
                payment_enabled=False,
                is_active=False,
                note=f"marketplace_application:{app.id}",
            )
            session.add(product)
            await session.flush()
            app.status = "approved"
            app.moderator_id = user_id
            app.product_id = product.id
            app.updated_at = _now()
            await session.commit()
            await session.refresh(product)
        await answer_message(bot, message, f"✅ Заявка #{app_id} одобрена. Создан скрытый товар #{product.id}. Настройте выдачу и включите товар.", business_connection_id)
        await safe_send_message(bot, app.applicant_telegram_id, f"✅ Ваша заявка #{app_id} одобрена. После настройки выдачи товар появится в маркете.")
        return True

    if command == "/market_reject":
        parts = arg.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            await answer_message(bot, message, "Формат: /market_reject ID причина", business_connection_id)
            return True
        app_id = int(parts[0])
        reason = parts[1].strip() if len(parts) > 1 else "Не прошла модерацию"
        async with SessionLocal() as session:
            app = await session.get(MarketplaceApplication, app_id)
            if not app or app.status != "pending":
                await answer_message(bot, message, "Заявка не найдена или уже обработана.", business_connection_id)
                return True
            app.status = "rejected"
            app.moderator_id = user_id
            app.reject_reason = reason[:1000]
            app.updated_at = _now()
            await session.commit()
        await answer_message(bot, message, f"❌ Заявка #{app_id} отклонена.", business_connection_id)
        await safe_send_message(bot, app.applicant_telegram_id, f"❌ Ваша заявка #{app_id} отклонена. Причина: {reason}")
        return True

    if command == "/promo_create":
        parts = arg.split()
        if len(parts) < 4:
            await answer_message(bot, message, "Формат: /promo_create CODE percent|fixed VALUE MAX_USES [YYYY-MM-DD] [PRODUCT_ID]", business_connection_id)
            return True
        code, discount_type, value_raw, max_uses_raw = parts[:4]
        if discount_type not in {"percent", "fixed"}:
            await answer_message(bot, message, "Тип скидки: percent или fixed.", business_connection_id)
            return True
        try:
            value = _parse_decimal(value_raw)
            max_uses = int(max_uses_raw)
        except Exception:
            await answer_message(bot, message, "VALUE и MAX_USES должны быть числами.", business_connection_id)
            return True
        expires_at = None
        product_id = None
        if len(parts) >= 5 and parts[4] != "-":
            try:
                expires_at = datetime.strptime(parts[4], "%Y-%m-%d")
            except ValueError:
                await answer_message(bot, message, "Дата должна быть YYYY-MM-DD или -.", business_connection_id)
                return True
        if len(parts) >= 6 and parts[5].isdigit():
            product_id = int(parts[5])
        async with SessionLocal() as session:
            row = await session.scalar(select(PromoCode).where(PromoCode.code == code.upper()))
            if not row:
                row = PromoCode(code=code.upper())
                session.add(row)
            row.discount_type = discount_type
            row.value = value
            row.max_uses = max_uses
            row.expires_at = expires_at
            row.product_id = product_id
            row.is_active = True
            row.updated_at = _now()
            await session.commit()
        await answer_message(bot, message, f"✅ Промокод {code.upper()} сохранён.", business_connection_id)
        return True

    if command == "/promos":
        async with SessionLocal() as session:
            rows = list((await session.scalars(select(PromoCode).order_by(PromoCode.id.desc()).limit(50))).all())
        if not rows:
            result = "Промокодов пока нет."
        else:
            result = "🎟 Промокоды\n\n" + "\n".join(
                f"{('✅' if r.is_active else '⛔')} {r.code}: {r.discount_type} {r.value}, {r.used_count}/{r.max_uses or '∞'}, товар {r.product_id or 'любой'}"
                for r in rows
            )
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/promo_disable":
        code = arg.split()[0].upper() if arg else ""
        if not code:
            await answer_message(bot, message, "Формат: /promo_disable CODE", business_connection_id)
            return True
        async with SessionLocal() as session:
            row = await session.scalar(select(PromoCode).where(PromoCode.code == code))
            if not row:
                await answer_message(bot, message, "Промокод не найден.", business_connection_id)
                return True
            row.is_active = False
            row.updated_at = _now()
            await session.commit()
        await answer_message(bot, message, f"⛔ Промокод {code} выключен.", business_connection_id)
        return True

    if command == "/stats_full":
        async with SessionLocal() as session:
            result = await stats_full_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/stats_product":
        if not arg.isdigit():
            await answer_message(bot, message, "Формат: /stats_product PRODUCT_ID", business_connection_id)
            return True
        async with SessionLocal() as session:
            result = await product_stats_text(session, int(arg))
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/feature_stats":
        async with SessionLocal() as session:
            result = await stats_full_text(session)
        await answer_message(bot, message, result + "\n\nПункты V37: номера/прокси/маркет/промо/топы/трофеи/кд включены на уровне БД и команд.", business_connection_id)
        return True

    if command == "/cooldowns":
        async with SessionLocal() as session:
            rows = list((await session.scalars(select(CooldownSetting).order_by(CooldownSetting.action))).all())
        result = "⏱ Настройки КД\n\n" + ("\n".join(f"{r.action}: {r.seconds} сек" for r in rows) if rows else "Индивидуальных настроек нет, используются дефолты.")
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/set_cooldown":
        parts = arg.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await answer_message(bot, message, "Формат: /set_cooldown ACTION SECONDS", business_connection_id)
            return True
        action, seconds_raw = parts
        async with SessionLocal() as session:
            row = await session.scalar(select(CooldownSetting).where(CooldownSetting.action == action))
            if not row:
                row = CooldownSetting(action=action)
                session.add(row)
            row.seconds = int(seconds_raw)
            row.updated_at = _now()
            await session.commit()
        await answer_message(bot, message, f"✅ КД {action}: {seconds_raw} сек.", business_connection_id)
        return True

    if command == "/product_add":
        parts = _split_pipe(arg, 4)
        if len(parts) < 5:
            await answer_message(bot, message, "Формат: /product_add Название | Цена | Валюта | CATEGORY_ID | Контент", business_connection_id)
            return True
        name, price_raw, currency, category_raw, content = parts
        try:
            price = _parse_decimal(price_raw)
            category_id = int(category_raw)
        except Exception:
            await answer_message(bot, message, "Цена и CATEGORY_ID должны быть корректными.", business_connection_id)
            return True
        async with SessionLocal() as session:
            category = await session.get(ShopCategory, category_id)
            if not category:
                await answer_message(bot, message, "Категория не найдена.", business_connection_id)
                return True
            product = ShopProduct(
                internal_key=await _next_internal_key(session),
                category_id=category.id,
                name=name[:255],
                price=price,
                currency=currency.upper()[:10],
                product_type="static",
                fulfillment_type="digital",
                content_type="text",
                content_text=content,
                payment_enabled=True,
                is_active=True,
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)
        await answer_message(bot, message, f"✅ Товар #{product.id} добавлен и включён.", business_connection_id)
        return True

    if command == "/product_delete":
        if not arg.isdigit():
            await answer_message(bot, message, "Формат: /product_delete PRODUCT_ID", business_connection_id)
            return True
        async with SessionLocal() as session:
            product = await session.get(ShopProduct, int(arg))
            if not product:
                await answer_message(bot, message, "Товар не найден.", business_connection_id)
                return True
            product.is_deleted = True
            product.is_active = False
            product.payment_enabled = False
            product.deleted_at = _now()
            product.deleted_by = user_id
            product.updated_at = _now()
            await session.commit()
        await answer_message(bot, message, "🗑 Товар удалён в архив.", business_connection_id)
        return True

    if command in {"/stock_add", "/number_stock_add", "/proxy_stock_add"}:
        parts = arg.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            await answer_message(bot, message, f"Формат: {command} PRODUCT_ID позиции_каждая_с_новой_строки", business_connection_id)
            return True
        product_id = int(parts[0])
        try:
            async with SessionLocal() as session:
                product = await session.get(ShopProduct, product_id)
                if not product:
                    await answer_message(bot, message, "Товар не найден.", business_connection_id)
                    return True
                if command == "/number_stock_add":
                    product.fulfillment_type = "number"
                elif command == "/proxy_stock_add":
                    product.fulfillment_type = "stock"
                    product.content_type = "text"
                count = await _create_stock_items(session, product_id, parts[1])
        except Exception as exc:
            await answer_message(bot, message, f"❌ {exc}", business_connection_id)
            return True
        await answer_message(bot, message, f"✅ Загружено позиций: {count}.", business_connection_id)
        return True

    if command == "/manual_add":
        parts = _split_pipe(arg, 1)
        if len(parts) != 2:
            await answer_message(bot, message, "Формат: /manual_add Заголовок | Текст мануала", business_connection_id)
            return True
        async with SessionLocal() as session:
            page = ManualPage(title=parts[0][:255], body=parts[1], is_active=True, updated_at=_now())
            session.add(page)
            await session.commit()
            await session.refresh(page)
        await answer_message(bot, message, f"✅ Мануал #{page.id} добавлен.", business_connection_id)
        return True

    if command == "/manuals":
        async with SessionLocal() as session:
            rows = list((await session.scalars(select(ManualPage).where(ManualPage.is_active.is_(True)).order_by(ManualPage.id.desc()).limit(20))).all())
        result = "📚 Мануалы\n\n" + ("\n".join(f"#{r.id} — {r.title}" for r in rows) if rows else "Мануалов нет.")
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/grant_ga":
        if not (is_super_admin or user_id in GA_IDS):
            await answer_message(bot, message, "Только главный админ может выдавать ГА.", business_connection_id)
            return True
        parts = arg.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            await answer_message(bot, message, "Формат: /grant_ga TELEGRAM_ID Имя", business_connection_id)
            return True
        target_id = int(parts[0])
        name = parts[1].strip() if len(parts) > 1 else f"GA_{target_id}"
        async with SessionLocal() as session:
            row = await session.scalar(select(AdminUser).where(AdminUser.telegram_id == target_id))
            if not row:
                row = AdminUser(telegram_id=target_id, name=name, is_active=True, added_by=user_id)
                session.add(row)
            else:
                row.name = name
                row.is_active = True
            await session.commit()
        await answer_message(bot, message, f"✅ Права администратора выданы: {target_id}. Чтобы сделать его главным ГА после рестарта/миграций, добавьте ID в GA_IDS или ADMIN_IDS в Render.", business_connection_id)
        await safe_send_message(bot, target_id, "Вам выданы права администратора. Откройте /admin")
        return True

    if command == "/wallet_payments":
        async with SessionLocal() as session:
            rows = list((await session.scalars(select(WalletPayment).where(WalletPayment.status == "pending").order_by(WalletPayment.id.desc()).limit(20))).all())
        result = "💼 Ожидают оплату на кошелёк\n\n" + ("\n".join(f"#{r.id} purchase={r.purchase_id} {r.amount} {r.currency} memo={r.memo}" for r in rows) if rows else "Нет ожидающих.")
        await answer_message(bot, message, result, business_connection_id)
        return True

    if command == "/wallet_confirm":
        parts = arg.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            await answer_message(bot, message, "Формат: /wallet_confirm PAYMENT_ID [TX_HASH]", business_connection_id)
            return True
        payment_id = int(parts[0])
        tx_hash = parts[1].strip() if len(parts) > 1 else None
        from app.wallet_service import mark_wallet_payment_paid
        ok, result = await mark_wallet_payment_paid(bot, payment_id, tx_hash=tx_hash, source="admin")
        await answer_message(bot, message, result, business_connection_id)
        return True

    return False


async def approve_marketplace_application(bot: Bot, app_id: int, moderator_id: int, category_id: int | None = None) -> str:
    async with SessionLocal() as session:
        app = await session.get(MarketplaceApplication, app_id)
        if not app or app.status != "pending":
            return "Заявка не найдена или уже обработана."
        category = await session.get(ShopCategory, category_id) if category_id else await _get_or_create_market_category(session, app.category_name or "Маркетплейс")
        product = ShopProduct(
            internal_key=await _next_internal_key(session),
            category_id=category.id,
            name=app.title,
            description=(app.description or "") + f"\n\nПродавец: @{app.applicant_username or app.applicant_telegram_id}",
            price=app.price,
            currency=app.currency,
            product_type="static",
            fulfillment_type="digital",
            content_type="text",
            content_text="Товар одобрен маркетплейсом. Администратор должен настроить выдачу перед включением продаж.",
            payment_enabled=False,
            is_active=False,
            note=f"marketplace_application:{app.id}",
        )
        session.add(product)
        await session.flush()
        app.status = "approved"
        app.moderator_id = moderator_id
        app.product_id = product.id
        app.updated_at = _now()
        await session.commit()
        await session.refresh(product)
        applicant_id = app.applicant_telegram_id
    await safe_send_message(bot, applicant_id, f"✅ Ваша заявка #{app_id} одобрена. После настройки выдачи товар появится в маркете.")
    return f"✅ Заявка #{app_id} одобрена. Создан скрытый товар #{product.id}. Настройте выдачу и включите товар."


async def reject_marketplace_application(bot: Bot, app_id: int, moderator_id: int, reason: str) -> str:
    async with SessionLocal() as session:
        app = await session.get(MarketplaceApplication, app_id)
        if not app or app.status != "pending":
            return "Заявка не найдена или уже обработана."
        app.status = "rejected"
        app.moderator_id = moderator_id
        app.reject_reason = reason[:1000]
        app.updated_at = _now()
        applicant_id = app.applicant_telegram_id
        await session.commit()
    await safe_send_message(bot, applicant_id, f"❌ Ваша заявка #{app_id} отклонена. Причина: {reason}")
    return f"❌ Заявка #{app_id} отклонена."


async def handle_marketplace_callback(bot: Bot, callback: CallbackQuery, *, is_admin: bool) -> bool:
    data = callback.data or ""
    if not data.startswith("market:"):
        return False
    if not is_admin or not callback.from_user:
        await callback.answer("Нет доступа.", show_alert=True)
        return True
    parts = data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Некорректная заявка.", show_alert=True)
        return True
    action = parts[1]
    app_id = int(parts[2])
    if action == "approve":
        result = await approve_marketplace_application(bot, app_id, callback.from_user.id)
        if callback.message:
            await callback.message.answer(result)
        await callback.answer("Готово")
        return True
    if action == "reject":
        result = await reject_marketplace_application(bot, app_id, callback.from_user.id, "Отклонено модератором")
        if callback.message:
            await callback.message.answer(result)
        await callback.answer("Готово")
        return True
    await callback.answer("Неизвестное действие.", show_alert=True)
    return True
