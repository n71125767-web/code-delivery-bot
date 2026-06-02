import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.config import BOT_TOKEN, ADMIN_IDS, SUPPLIER_IDS
from app.database import SessionLocal, engine
from app.models import Base, Order
from app.parsers import extract_purchase_data, extract_phone, extract_code
from app.services import (
    create_order_from_purchase,
    create_supplier_request,
    add_supplier,
    delete_supplier,
    get_supplier_for_service,
    list_suppliers,
    find_waiting_service_order_by_id_or_username_today,
    find_number_sent_order_by_id_or_username_today,
    notify_no_supplier
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

PURCHASE_LOOKBACK_HOURS = 24

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    username = username.strip().lower()
    if username.startswith("@"):
        username = username[1:]
    return username or None

async def send_to_admins(text: str):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logging.error("Не смог отправить админу %s сообщение: %s", admin_id, e)

async def send_business_text(chat_id: int, business_connection_id: str | None, text: str, reply_markup=None):
    if not business_connection_id:
        return False
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            business_connection_id=business_connection_id
        )
        return True
    except Exception as e:
        await send_to_admins(f"⚠️ Не удалось отправить сообщение пользователю {chat_id}\nОшибка: {e}")
        return False

# ------------------ Business-сообщения ------------------
@dp.business_message(F.text)
@dp.business_message(F.text)
async def business_text_handler(message: Message):
    sender = message.from_user
    text = (message.text or "").strip()
    business_connection_id = getattr(message, "business_connection_id", None)

    if not sender or not text or getattr(sender, "is_bot", False):
        return

    async with SessionLocal() as session:
        # ищем заказ покупателя за последние 24 часа по ID и username
        order = await find_waiting_service_order_by_id_or_username_today(
            session=session,
            customer_telegram_id=sender.id,
            customer_username=sender.username,
            hours=24
        )

        if not order:
            return

        # сохраняем business_connection_id покупателя
        order.business_connection_id = business_connection_id
        order.service_name = text
        order.status = "waiting_supplier_number"
        await session.commit()

        # находим поставщика
        supplier = await get_supplier_for_service(session, text)
        if not supplier:
            await notify_no_supplier(order, text, business_connection_id)
            return

        # создаём запрос поставщику
        await create_supplier_request(
            session=session,
            order=order,
            supplier_telegram_id=supplier.telegram_id,
            request_type="number"
        )

        # Отправляем сообщение **поставщику** обычным методом
        try:
            await bot.send_message(
                chat_id=supplier.telegram_id,
                text=(
                    f"📦 Новый заказ #{order.operation_id}\n"
                    f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                    f"Telegram ID: {order.customer_telegram_id}\n"
                    f"Сервис: {text}\n\n"
                    "Нужно выдать номер покупателю."
                )
            )
        except Exception as e:
            await send_to_admins(f"⚠️ Не смог написать поставщику {supplier.telegram_id}: {e}")

        # Отправка **покупателю** через business_connection_id
        if business_connection_id:
            await send_business_text(
                chat_id=sender.id,
                business_connection_id=business_connection_id,
                text=(
                    f"✅ Ваш заказ принят.\nСервис: {text}\n"
                    "Скоро вам придёт номер от поставщика."
                )
            )
        else:
            await send_to_admins(
                f"⚠️ Не могу написать покупателю {sender.id}, business_connection_id пустой"
            )
        # подтверждение покупателю
        await send_business_text(
            chat_id=sender.id,
            business_connection_id=business_connection_id,
            text=(
                f"✅ Ваш заказ принят.\nСервис: {text}\n"
                "Скоро вам придёт номер от поставщика."
            )
        )

# ------------------ Команды админа ------------------
@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Бот запущен ✅\n\n"
        "Админ: /status, /suppliers\n"
        "Поставщик: дождитесь запроса и отправьте номер/код.\n"
        "Покупатель пишет на обычный Telegram-аккаунт с Business-ботом."
    )

@dp.message(Command("status"))
async def status_handler(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("✅ Сервис работает")

@dp.message(Command("suppliers"))
async def suppliers_help_handler(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Управление поставщиками:\n\n"
        "/add_supplier ID СЕРВИС ИМЯ\n"
        "/del_supplier ID\n"
        "/list_suppliers"
    )

@dp.message(Command("add_supplier"))
async def add_supplier_handler(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Неверный формат. /add_supplier ID СЕРВИС ИМЯ")
        return
    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("ID поставщика должен быть числом.")
        return
    service_name = parts[2]
    supplier_name = parts[3] if len(parts) >= 4 else None
    async with SessionLocal() as session:
        supplier = await add_supplier(session, telegram_id, service_name, supplier_name)
    await message.answer(f"✅ Поставщик добавлен/обновлён\nID: {supplier.telegram_id}\nСервис: {supplier.service_name}")

@dp.message(Command("del_supplier"))
async def del_supplier_handler(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Неверный формат. /del_supplier ID")
        return
    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("ID поставщика должен быть числом.")
        return
    async with SessionLocal() as session:
        deleted = await delete_supplier(session, telegram_id)
    if deleted:
        await message.answer(f"✅ Поставщик {telegram_id} удалён.")
    else:
        await message.answer("Поставщик с таким ID не найден.")

@dp.message(Command("list_suppliers"))
async def list_suppliers_handler(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with SessionLocal() as session:
        suppliers = await list_suppliers(session)
    if not suppliers:
        await message.answer("Поставщиков пока нет.")
        return
    text = "📋 Список поставщиков:\n\n"
    for s in suppliers:
        text += f"ID: {s.telegram_id}\nСервис: {s.service_name}\n---\n"
    await message.answer(text)

# ------------------ Основной запуск ------------------
async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "business_message"])

if __name__ == "__main__":
    asyncio.run(main())