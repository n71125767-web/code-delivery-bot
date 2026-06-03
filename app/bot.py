import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from app.config import BOT_TOKEN, ADMIN_IDS, SUPPLIER_IDS, SHOP_BOT_USERNAME
from app.database import engine, SessionLocal
from app.models import Base, Order, SupplierRequest
from app.parsers import extract_purchase_data, extract_phone, extract_code
from app.services import (
    create_or_update_order_from_purchase,
    find_waiting_service_order_for_customer,
    find_active_order_for_customer,
    create_supplier_request,
    find_waiting_supplier_request,
    get_order_by_id,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_supplier(user_id: int) -> bool:
    return user_id in SUPPLIER_IDS


def confirm_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Всё успешно", callback_data=f"confirm_success:{order_id}")
    kb.button(text="❌ Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def number_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📩 Код отправлен", callback_data=f"code_sent:{order_id}")
    kb.button(text="❌ Номер не работает", callback_data=f"number_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


@dp.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username

    async with SessionLocal() as session:
        order = await find_active_order_for_customer(session, user_id, username)

        if order and order.status == "waiting_service":
            await message.answer(
                "Оплата получена ✅\n\n"
                "Напишите, для какого сервиса нужен номер.\n"
                "Например: Telegram, WhatsApp, Google."
            )
            return

    await message.answer(
        "Бот запущен ✅\n\n"
        "Если вы оплатили заказ, напишите сюда название сервиса."
    )


@dp.message(Command("status"))
async def status_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with SessionLocal() as session:
        total_orders = await session.scalar(select(func.count(Order.id)))
        waiting_service = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_service")
        )
        waiting_number = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_supplier_number")
        )
        waiting_code = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "waiting_supplier_code")
        )
        confirmed = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "confirmed")
        )
        problem = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "problem")
        )

    await message.answer(
        "📊 Статус бота\n\n"
        f"Всего заказов: {total_orders or 0}\n"
        f"Ждут сервис: {waiting_service or 0}\n"
        f"Ждут номер: {waiting_number or 0}\n"
        f"Ждут код: {waiting_code or 0}\n"
        f"Успешные: {confirmed or 0}\n"
        f"Проблемные: {problem or 0}"
    )


@dp.message(Command("last_orders"))
async def last_orders_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(Order).order_by(Order.created_at.desc()).limit(10)
        )
        orders = result.scalars().all()

    if not orders:
        await message.answer("Заказов пока нет.")
        return

    lines = ["📦 Последние заказы:\n"]

    for order in orders:
        lines.append(
            f"#{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Покупатель ID: {order.customer_telegram_id}\n"
            f"Username: @{order.customer_username or 'нет'}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name or 'не указан'}\n"
            f"Статус: {order.status}\n"
            "--------------------"
        )

    await message.answer("\n".join(lines))


@dp.message(Command("debug_orders"))
async def debug_orders_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(Order)
            .where(Order.status == "waiting_service")
            .order_by(Order.created_at.desc())
            .limit(20)
        )
        orders = result.scalars().all()

    if not orders:
        await message.answer("Нет заказов со статусом waiting_service.")
        return

    text = "🔍 Заказы, которые ждут сервис:\n\n"

    for order in orders:
        text += (
            f"База ID: {order.id}\n"
            f"Операция: #{order.operation_id}\n"
            f"Покупатель ID: {order.customer_telegram_id}\n"
            f"Username: @{order.customer_username or 'нет'}\n"
            f"Товар: {order.product_name}\n"
            f"Статус: {order.status}\n"
            "--------------------\n"
        )

    await message.answer(text)


@dp.message(Command("set_customer"))
async def set_customer_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()

    if len(parts) != 3:
        await message.answer(
            "Формат команды:\n"
            "/set_customer ID_ЗАКАЗА TELEGRAM_ID\n\n"
            "Пример:\n"
            "/set_customer 5 92463179"
        )
        return

    try:
        order_id = int(parts[1])
        customer_id = int(parts[2])
    except ValueError:
        await message.answer("ID заказа и Telegram ID должны быть числами.")
        return

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)

        if not order:
            await message.answer("Заказ не найден.")
            return

        order.customer_telegram_id = customer_id
        order.updated_at = datetime.utcnow()

        await session.commit()

    await message.answer(
        f"✅ Заказ ID {order_id} привязан к покупателю {customer_id}"
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Напишите название сервиса после оплаты.")
        return

    await message.answer(
        "Команды админа:\n\n"
        "/status — статус бота\n"
        "/last_orders — последние 10 заказов\n"
        "/debug_orders — заказы, которые ждут сервис\n"
        "/set_customer ID_ЗАКАЗА TELEGRAM_ID — вручную привязать покупателя\n"
        "/help — помощь\n\n"
        "Команды покупателя:\n"
        "/start — запустить бота"
    )


@dp.business_message(F.text)
async def business_text_handler(message: Message):
    sender = message.from_user
    text = message.text or ""

    if not sender:
        return

    sender_username = sender.username or ""

    logger.info("Business message from @%s: %s", sender_username, text[:200])

    if sender_username.lower() != SHOP_BOT_USERNAME.lower():
        return

    purchase_data = extract_purchase_data(text)

    if not purchase_data:
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                "⚠️ Получил business-сообщение от shop-бота, но не смог распарсить покупку.\n\n"
                f"От: @{sender_username}\n\n"
                f"Текст:\n{text}"
            )
        return

    async with SessionLocal() as session:
        order = await create_or_update_order_from_purchase(session, purchase_data)

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            "✅ Покупка обработана.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Покупатель ID: {order.customer_telegram_id}\n"
            f"Username: @{order.customer_username or 'нет'}\n"
            f"Товар: {order.product_name}\n"
            f"Статус: {order.status}"
        )

    if not order.customer_telegram_id:
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                "⚠️ У заказа нет Telegram ID покупателя.\n"
                "Бот сможет найти покупателя только по username, если он совпадает.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Username: @{order.customer_username or 'нет'}"
            )
        return

    try:
        await bot.send_message(
            order.customer_telegram_id,
            "Оплата получена ✅\n\n"
            "Напишите, для какого сервиса нужен номер.\n"
            "Например: Telegram, WhatsApp, Google."
        )
    except Exception as e:
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                "⚠️ Не смог написать покупателю в личку.\n"
                "Покупатель должен сначала нажать /start в этом боте.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"ID в базе: {order.id}\n"
                f"Покупатель ID: {order.customer_telegram_id}\n"
                f"Ошибка: {e}"
            )


async def handle_supplier_message(message: Message):
    supplier_id = message.from_user.id
    text = message.text or ""

    async with SessionLocal() as session:
        number_request = await find_waiting_supplier_request(
            session=session,
            supplier_telegram_id=supplier_id,
            request_type="number",
        )

        if number_request:
            phone = extract_phone(text)

            if not phone:
                await message.answer(
                    "❌ Не смог найти номер в сообщении.\n"
                    "Пришлите номер в формате +79990000000"
                )
                return

            order = await get_order_by_id(session, number_request.order_id)

            if not order:
                await message.answer("❌ Заказ для этого запроса не найден.")
                return

            order.phone_number = phone
            order.status = "number_sent_to_customer"
            order.updated_at = datetime.utcnow()

            number_request.status = "answered"
            number_request.answered_at = datetime.utcnow()

            await session.commit()

            await bot.send_message(
                order.customer_telegram_id,
                f"{phone}",
                reply_markup=number_keyboard(order.id),
            )

            await message.answer(
                f"✅ Номер принят и отправлен покупателю.\n"
                f"Заказ #{order.operation_id}\n"
                f"Номер: {phone}"
            )

            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    admin_id,
                    f"📲 Номер отправлен покупателю.\n\n"
                    f"Заказ #{order.operation_id}\n"
                    f"Номер: {phone}"
                )

            return

        code_request = await find_waiting_supplier_request(
            session=session,
            supplier_telegram_id=supplier_id,
            request_type="code",
        )

        if code_request:
            code = extract_code(text)

            if not code:
                await message.answer(
                    "❌ Не смог найти код в сообщении.\n"
                    "Пришлите код, например: 123456"
                )
                return

            order = await get_order_by_id(session, code_request.order_id)

            if not order:
                await message.answer("❌ Заказ для этого запроса не найден.")
                return

            order.verification_code = code
            order.status = "code_sent_to_customer"
            order.updated_at = datetime.utcnow()

            code_request.status = "answered"
            code_request.answered_at = datetime.utcnow()

            await session.commit()

            await bot.send_message(
                order.customer_telegram_id,
                f"{code}",
                reply_markup=confirm_keyboard(order.id),
            )

            await message.answer(
                f"✅ Код принят и отправлен покупателю.\n"
                f"Заказ #{order.operation_id}\n"
                f"Код: {code}"
            )

            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    admin_id,
                    f"🔐 Код отправлен покупателю.\n\n"
                    f"Заказ #{order.operation_id}\n"
                    f"Код: {code}"
                )

            return

    await message.answer(
        "Нет активного запроса для вас.\n"
        "Сейчас бот не ждёт от вас номер или код."
    )


async def handle_customer_message(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    text = message.text.strip()

    async with SessionLocal() as session:
        order = await find_waiting_service_order_for_customer(
            session=session,
            telegram_id=user_id,
            username=username,
        )

        if not order:
            await message.answer(
                "❌ Заказ не найден.\n\n"
                "Возможные причины:\n"
                "1. Оплата ещё не пришла в систему.\n"
                "2. В заказе другой Telegram ID.\n"
                "3. Вы пишете не с того аккаунта.\n\n"
                "Напишите админу, чтобы он проверил заказ."
            )

            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    admin_id,
                    "⚠️ Покупатель написал, но заказ не найден.\n\n"
                    f"Telegram ID: {user_id}\n"
                    f"Username: @{username or 'нет'}\n"
                    f"Текст: {text}\n\n"
                    "Проверь /debug_orders и при необходимости используй:\n"
                    f"/set_customer ID_ЗАКАЗА {user_id}"
                )
            return

        order.service_name = text
        order.status = "waiting_supplier_number"
        order.updated_at = datetime.utcnow()

        supplier_id = SUPPLIER_IDS[0]

        await create_supplier_request(
            session=session,
            order_id=order.id,
            supplier_telegram_id=supplier_id,
            request_type="number",
        )

        await session.commit()

    await message.answer(
        "✅ Сервис принят.\n\n"
        "Ожидайте номер."
    )

    await bot.send_message(
        supplier_id,
        "📦 Новый заказ.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Товар: {order.product_name}\n"
        f"Сервис: {order.service_name}\n\n"
        "Пришлите номер для покупателя.\n"
        "Можно в любом формате, например:\n"
        "+79990000000"
    )

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            "📨 Запрос поставщику отправлен.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"Покупатель: @{order.customer_username or 'нет'} / {order.customer_telegram_id}\n"
            f"Сервис: {order.service_name}"
        )


@dp.callback_query(F.data.startswith("code_sent:"))
async def code_sent_callback(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if callback.from_user.id != order.customer_telegram_id:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return

        order.status = "waiting_supplier_code"
        order.updated_at = datetime.utcnow()

        supplier_id = SUPPLIER_IDS[0]

        await create_supplier_request(
            session=session,
            order_id=order.id,
            supplier_telegram_id=supplier_id,
            request_type="code",
        )

        await session.commit()

    await callback.message.answer(
        "✅ Понял.\n\n"
        "Запросил код у поставщика. Ожидайте."
    )

    await bot.send_message(
        supplier_id,
        "🔐 Покупатель отправил код на номер.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Сервис: {order.service_name}\n"
        f"Номер: {order.phone_number}\n\n"
        "Пришлите код."
    )

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🔐 Запрос кода отправлен поставщику.\n\n"
            f"Заказ #{order.operation_id}"
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_success:"))
async def confirm_success_callback(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if callback.from_user.id != order.customer_telegram_id:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return

        order.status = "confirmed"
        order.updated_at = datetime.utcnow()

        await session.commit()

    await callback.message.answer("✅ Отлично, заказ завершён.")
    await callback.answer()

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"✅ Заказ успешно завершён.\n\n"
            f"Заказ #{order.operation_id}"
        )


@dp.callback_query(F.data.startswith("number_invalid:"))
async def number_invalid_callback(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        order.status = "problem"
        order.updated_at = datetime.utcnow()

        await session.commit()

    await callback.message.answer(
        "⚠️ Понял. Передал админу проблему с номером."
    )
    await callback.answer()

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"❌ Покупатель сообщил, что номер не работает.\n\n"
            f"Заказ #{order.operation_id}\n"
            f"Номер: {order.phone_number}"
        )


@dp.callback_query(F.data.startswith("code_invalid:"))
async def code_invalid_callback(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        order.status = "problem"
        order.updated_at = datetime.utcnow()

        await session.commit()

    await callback.message.answer(
        "⚠️ Понял. Передал админу проблему с кодом."
    )
    await callback.answer()

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"❌ Покупатель сообщил, что код не работает.\n\n"
            f"Заказ #{order.operation_id}\n"
            f"Код: {order.verification_code}"
        )


@dp.message(F.text)
async def text_router(message: Message):
    if not message.from_user:
        return

    if message.text.startswith("/"):
        return

    user_id = message.from_user.id

    if is_supplier(user_id):
        await handle_supplier_message(message)
        return

    await handle_customer_message(message)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Bot started")

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
        ],
    )


if __name__ == "__main__":
    asyncio.run(main())