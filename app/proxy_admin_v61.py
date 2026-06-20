from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    PROXYLINE_ENABLED, PROXYLINE_API_KEY, PROXYS_ENABLED, PROXYS_API_KEY,
    PROXY_BALANCE_WARN_USD, PROXY_BALANCE_CRITICAL_USD,
)
from app.models import ShopProduct, DigitalPurchase
from app.proxyline import ProxylineService
from app.proxys import ProxysService
from app.proxy_pricing_v39 import (
    get_proxy_markup_multiplier_for_category,
    set_proxy_markup_multiplier_for_category,
    apply_proxy_markup, multiplier_label,
)

PROXY_KIND_META = {
    # ВАЖНО: те же эмодзи и названия, что видит покупатель.
    "mtproxy": {"provider": "proxyline", "title": "🔐 MTProxy", "item": "🔑 MTProxy • [1 мес.]"},
    "premium": {"provider": "proxyline", "title": "🏆 PREMIUM", "item": "🪐 Прокси [1 мес.]"},
    "standard": {"provider": "proxys", "title": "💯 STANDART", "item": "🎲 Прокси [1 мес.]"},
    "residential": {"provider": "proxys", "title": "🏠 RESIDENTIAL", "item": "🏠 Резидентские прокси [1 мес.]"},
}

def fmt_amount(value: object, currency: str = "USD") -> str:
    try:
        amount = Decimal(str(value).replace(",", "."))
    except Exception:
        return f"— {currency}"
    q = amount.quantize(Decimal("0.01"))
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text} {currency}"

def _extract_balance(payload: Any) -> tuple[Decimal | None, str]:
    currency = "USD"
    def walk(obj: Any):
        nonlocal currency
        if isinstance(obj, dict):
            for ck in ("currency", "asset", "coin"):
                if obj.get(ck):
                    currency = str(obj.get(ck)).upper()[:10]
                    break
            for key in ("balance", "amount", "money", "usd", "available", "value"):
                if key in obj and obj[key] not in (None, ""):
                    try:
                        return Decimal(str(obj[key]).replace(",", "."))
                    except Exception:
                        pass
            for val in obj.values():
                found = walk(val)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for val in obj:
                found = walk(val)
                if found is not None:
                    return found
        elif isinstance(obj, (int, float, str)):
            try:
                return Decimal(str(obj).replace(",", "."))
            except Exception:
                return None
        return None
    return walk(payload), currency

async def get_provider_balance(provider: str) -> tuple[Decimal | None, str, str | None]:
    try:
        if provider == "proxyline":
            if not (PROXYLINE_ENABLED and PROXYLINE_API_KEY):
                return None, "USD", "не настроен"
            payload = await ProxylineService(PROXYLINE_API_KEY).balance()
        else:
            if not (PROXYS_ENABLED and PROXYS_API_KEY):
                return None, "USD", "не настроен"
            payload = await ProxysService(PROXYS_API_KEY).balance()
        amount, currency = _extract_balance(payload)
        return amount, currency, None
    except Exception as exc:
        return None, "USD", str(exc)[:120]

async def balances_text() -> str:
    p_amount, p_cur, p_err = await get_provider_balance("proxyline")
    x_amount, x_cur, x_err = await get_provider_balance("proxys")
    def line(name, amount, cur, err):
        if err:
            return f"{name}: ⚠️ {err}"
        label = fmt_amount(amount, cur) if amount is not None else f"— {cur}"
        warn = "🔴" if amount is not None and amount < Decimal(str(PROXY_BALANCE_CRITICAL_USD)) else ("🟡" if amount is not None and amount < Decimal(str(PROXY_BALANCE_WARN_USD)) else "🟢")
        return f"{name}: {warn} {label}"
    return line("Proxyline", p_amount, p_cur, p_err) + "\n" + line("Proxys", x_amount, x_cur, x_err)

async def proxy_admin_text(session: AsyncSession, include_balances: bool = True) -> str:
    balances = await balances_text() if include_balances else "Proxyline: —\nProxys: —"
    return (
        "🌐 Прокси\n\n"
        "Балансы:\n" + balances + "\n\n"
        "Выберите раздел кнопкой ниже."
    )

def proxy_admin_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔐 MTProxy", callback_data="admin:proxy:kind:mtproxy")
    kb.button(text="🏆 PREMIUM", callback_data="admin:proxy:kind:premium")
    kb.button(text="💯 STANDART", callback_data="admin:proxy:kind:standard")
    kb.button(text="🏠 RESIDENTIAL", callback_data="admin:proxy:kind:residential")
    kb.button(text="💰 Балансы", callback_data="admin:proxy:balances")
    kb.button(text="🌍 Страны", callback_data="admin:proxy:countries:0")
    kb.button(text="📅 Сроки", callback_data="admin:proxy:periods")
    kb.button(text="🔄 Создать/обновить", callback_data="admin:proxy:autofix")
    kb.button(text="🔙 Назад", callback_data="admin:panel")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()

def provider_keyboard(provider: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if provider == "proxyline":
        kb.button(text="🔐 MTProxy", callback_data="admin:proxy:kind:mtproxy")
        kb.button(text="🏆 PREMIUM", callback_data="admin:proxy:kind:premium")
    else:
        kb.button(text="💯 STANDART", callback_data="admin:proxy:kind:standard")
        kb.button(text="🏠 RESIDENTIAL", callback_data="admin:proxy:kind:residential")
    kb.button(text="💰 Балансы", callback_data="admin:proxy:balances")
    kb.button(text="🔙 К прокси", callback_data="admin:proxy")
    kb.adjust(2)
    return kb.as_markup()

async def find_proxy_product(session: AsyncSession, kind: str) -> ShopProduct | None:
    return await session.scalar(select(ShopProduct).where(ShopProduct.note == f"proxy_autofix:{kind}"))

async def proxy_kind_text(session: AsyncSession, kind: str) -> str:
    meta = PROXY_KIND_META.get(kind, PROXY_KIND_META["standard"])
    product = await find_proxy_product(session, kind)
    markup = await get_proxy_markup_multiplier_for_category(session, kind)
    lines = [f"{meta['title']}", ""]
    lines.append(f"Провайдер: {'Proxyline' if meta['provider']=='proxyline' else 'Proxys'}")
    if product:
        final = apply_proxy_markup(product.price, markup)
        lines.append(f"Товар: #{product.id} — {product.name}")
        lines.append(f"База: {fmt_amount(product.price, product.currency)}")
        lines.append(f"Наценка: {multiplier_label(markup)}")
        lines.append(f"Покупателю: {fmt_amount(final, product.currency)} за 1 мес.")
        lines.append(f"Оплата: {'включена' if product.payment_enabled else 'выключена'}")
    else:
        lines.append("Товар ещё не создан. Нажмите «Создать/обновить». ")
    return "\n".join(lines)

def proxy_kind_keyboard(kind: str, product_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Цена", callback_data=f"admin:proxy:price:{kind}")
    kb.button(text="📈 Наценка", callback_data=f"admin:proxy:markup:{kind}")
    kb.button(text="📝 Текст", callback_data=f"admin:proxy:text:{kind}")
    kb.button(text="🔄 Создать/обновить", callback_data="admin:proxy:autofix")
    if product_id:
        kb.button(text="📦 Карточка товара", callback_data=f"admin:shop:product:{product_id}")
    kb.button(text="🔙 К прокси", callback_data="admin:proxy")
    kb.adjust(2)
    return kb.as_markup()

async def set_proxy_kind_price(session: AsyncSession, kind: str, raw: str) -> str:
    product = await find_proxy_product(session, kind)
    if not product:
        return "Товар не найден. Сначала нажмите «Создать/обновить»."
    parts = raw.replace(",", ".").split()
    if not parts:
        return "Введите цену, например: 120 RUB"
    try:
        price = Decimal(parts[0])
    except (InvalidOperation, ValueError):
        return "Цена должна быть числом."
    if price < 0:
        return "Цена не может быть отрицательной."
    currency = parts[1].upper()[:10] if len(parts) > 1 else product.currency
    product.price = price
    product.currency = currency
    await session.commit()
    return f"✅ Цена сохранена: {fmt_amount(price, currency)}"

async def set_proxy_kind_markup(session: AsyncSession, kind: str, raw: str) -> str:
    value = raw.replace(",", ".").strip()
    try:
        markup = await set_proxy_markup_multiplier_for_category(session, kind, value)
    except Exception as exc:
        return str(exc)
    await session.commit()
    return f"✅ Наценка сохранена: {multiplier_label(markup)}"
