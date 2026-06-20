from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from app.config import (
    CRYPTO_PAY_ACCEPTED_ASSETS,
    CRYPTO_PAY_ENABLED,
    CRYPTO_PAY_NETWORK,
)
from app.models import CryptoPayment, DigitalPurchase


def payment_methods_text() -> str:
    return (
        "🪙 Способы оплаты\n\n"
        "Основная платежная система: CryptoBot / Crypto Pay\n\n"
        f"Статус: {'🟢 настроена' if CRYPTO_PAY_ENABLED else '🔴 токен не задан'}\n"
        f"Сеть: {CRYPTO_PAY_NETWORK}\n"
        f"Активы: {CRYPTO_PAY_ACCEPTED_ASSETS}\n"
        "Webhook: защищён официальной HMAC-подписью"
    )


def payment_methods_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="admin:payment_methods")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


async def payments_text(session) -> str:
    total = int(await session.scalar(select(func.count(DigitalPurchase.id))) or 0)
    pending = int(
        await session.scalar(
            select(func.count(DigitalPurchase.id)).where(
                DigitalPurchase.status.in_(
                    ("new", "creating_invoice", "pending_payment")
                )
            )
        )
        or 0
    )
    paid = int(
        await session.scalar(
            select(func.count(DigitalPurchase.id)).where(
                DigitalPurchase.status.in_(("paid", "delivering", "delivered"))
            )
        )
        or 0
    )
    delivered = int(
        await session.scalar(
            select(func.count(DigitalPurchase.id)).where(
                DigitalPurchase.status == "delivered"
            )
        )
        or 0
    )
    errors = int(
        await session.scalar(
            select(func.count(DigitalPurchase.id)).where(
                DigitalPurchase.status.in_(
                    ("delivery_failed", "delivery_review_required", "invoice_failed")
                )
            )
        )
        or 0
    )
    invoices = int(await session.scalar(select(func.count(CryptoPayment.id))) or 0)

    return (
        "📊 Оплата\n\n"
        f"Всего заказов: {total}\n"
        f"Счетов CryptoBot: {invoices}\n"
        f"Ожидают оплаты: {pending}\n"
        f"Оплачено: {paid}\n"
        f"Выдано: {delivered}\n"
        f"Ошибки: {errors}"
    )


def payments_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="admin:payments")
    kb.button(text="⚠️ Проблемы", callback_data="admin:problems")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def store_settings_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Вид товаров", callback_data="v25:view_settings")
    kb.button(text="👮 Администраторы", callback_data="admin:admins")
    kb.button(text="⚠️ Проблемы", callback_data="admin:problems")
    kb.button(text="⬅️ Назад", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def broadcast_preview_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Запустить рассылку",
        callback_data="v28:broadcast_confirm",
    )
    kb.button(text="❌ Отмена", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()
