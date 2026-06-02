import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import BOT_TOKEN, ADMIN_IDS, SUPPLIER_IDS
from app.database import SessionLocal, engine
from app.models import Base, Order
from app.parsers import extract_purchase_data, extract_phone, extract_code
from app.services import (
    create_order_from_purchase,
    find_waiting_service_order,
    find_order_waiting_supplier_number,
    find_order_waiting_supplier_code,
    create_supplier_request,
    close_supplier_request,
    add_supplier,
    delete_supplier,
    get_supplier_for_service,
    list_suppliers,
)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SHOP_BOT_USERNAME = "MrvlShopXBot"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_supplier_from_env(user_id: int) -> bool:
    return user_id in SUPPLIER_IDS


async def get_active_supplier_by_user_id(session, user_id: int):
    suppliers = await list_suppliers(session)

    for supplier in suppliers:
        if supplier.telegram_id == user_id:
            return supplier

    return None


def code_sent_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📩 Код отправлен", callback_data=f"customer_code_sent:{order_id}")
    kb.button(text="❌ Номер не работает", callback_data=f"number_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


def confirm_keyboard(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Всё успешно", callback_data=f"confirm_success:{order_id}")
    kb.button(text="❌ Код не работает", callback_data=f"code_invalid:{order_id}")
    kb.adjust(1)
    return kb.as_markup()


async def send_to_admins(text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logging.error("Не смог отправить админу %s сообщение: %s", admin_id, e)


async def send_to_customer(order: Order, text: str, reply_markup=None) -> bool:
    """
    Отправка покупателю через Telegram Business.

    ВАЖНО:
    Нельзя писать покупателю, пока он сам не написал
    в ваш Telegram-аккаунт с подключённым Business-ботом.

    Если business_connection_id пустой — бот НЕ пытается писать как обычный бот,
    потому что это вызывает ошибку chat not found.
    """

    if not order.business_connection_id:
        await send_to_admins(
            "⚠️ Не могу написать покупателю через Business.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"Покупатель: {order.customer_username or order.customer_telegram_id}\n\n"
            "Причина: покупатель ещё не написал в ваш Telegram-аккаунт, "
            "поэтому нет business_connection_id покупателя."
        )
        return False

    try:
        await bot.send_message(
            chat_id=order.customer_telegram_id,
            text=text,
            reply_markup=reply_markup,
            business_connection_id=order.business_connection_id,
        )
        return True

    except TypeError:
        await send_to_admins(
            "⚠️ Установленная версия aiogram не поддерживает business_connection_id.\n\n"
            "Выполни локально:\n"
            "pip install -U aiogram\n\n"
            "Потом обнови requirements.txt и залей на GitHub."
        )
        return False

    except Exception as e:
        await send_to_admins(
            "⚠️ Не смог отправить сообщение покупателю через Business.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
            f"business_connection_id: {order.business_connection_id}\n"
            f"Ошибка: {e}"
        )
        return False

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Бот запущен ✅\n\n"
        "Покупатель пишет на обычный Telegram-аккаунт с подключённым Business-ботом.\n"
        "Поставщик пишет номер/код сюда, в обычного бота.\n"
        "Админ управляет поставщиками командами /suppliers."
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
        "Добавить или обновить поставщика.\n\n"
        "Пример:\n"
        "/add_supplier 123456789 Telegram Иван\n\n"
        "/del_supplier ID\n"
        "Удалить поставщика.\n\n"
        "Пример:\n"
        "/del_supplier 123456789\n\n"
        "/list_suppliers\n"
        "Показать список поставщиков."
    )


@dp.message(Command("add_supplier"))
async def add_supplier_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=3)

    if len(parts) < 3:
        await message.answer(
            "Неверный формат.\n\n"
            "Используй так:\n"
            "/add_supplier ID СЕРВИС ИМЯ\n\n"
            "Пример:\n"
            "/add_supplier 123456789 Telegram Иван"
        )
        return

    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("ID поставщика должен быть числом.")
        return

    service_name = parts[2]
    supplier_name = parts[3] if len(parts) >= 4 else None

    async with SessionLocal() as session:
        supplier = await add_supplier(
            session=session,
            telegram_id=telegram_id,
            service_name=service_name,
            name=supplier_name,
        )

    await message.answer(
        "✅ Поставщик добавлен/обновлён.\n\n"
        f"ID: {supplier.telegram_id}\n"
        f"Имя: {supplier.name or '-'}\n"
        f"Сервис: {supplier.service_name}"
    )


@dp.message(Command("del_supplier"))
async def del_supplier_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Неверный формат.\n\n"
            "Используй так:\n"
            "/del_supplier ID\n\n"
            "Пример:\n"
            "/del_supplier 123456789"
        )
        return

    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("ID поставщика должен быть числом.")
        return

    async with SessionLocal() as session:
        deleted = await delete_supplier(
            session=session,
            telegram_id=telegram_id,
        )

    if not deleted:
        await message.answer("Поставщик с таким ID не найден.")
        return

    await message.answer(f"✅ Поставщик {telegram_id} удалён.")


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

    for supplier in suppliers:
        text += (
            f"ID: {supplier.telegram_id}\n"
            f"Имя: {supplier.name or '-'}\n"
            f"Сервис: {supplier.service_name}\n"
            f"---\n"
        )

    await message.answer(text)


@dp.business_message(F.text)
async def business_text_handler(message: Message):
    """
    Все сообщения, которые приходят в ваш обычный Telegram-аккаунт
    с подключённым Business-ботом.

    Тут обрабатываем:
    1. сообщение о покупке от шоп-бота;
    2. сообщение покупателя с сервисом;
    3. сообщение покупателя "код отправлен".
    """

    sender = message.from_user
    text = message.text or ""

    if not sender:
        await send_to_admins(
            "⚠️ Получил Business-сообщение, но sender пустой.\n\n"
            f"Текст:\n{text}"
        )
        return

    business_connection_id = getattr(message, "business_connection_id", None)

    await send_to_admins(
        "📩 Business-сообщение получено.\n\n"
        f"От ID: {sender.id}\n"
        f"Username: @{sender.username if sender.username else '-'}\n"
        f"Имя: {sender.full_name}\n"
        f"Business connection: {business_connection_id or '-'}\n\n"
        f"Текст:\n{text[:1500]}"
    )

    async with SessionLocal() as session:
        # 1. Сначала проверяем: это сообщение о покупке от шоп-бота?
        purchase_data = extract_purchase_data(text)

        if purchase_data:
            # ВАЖНО:
            # Это business_connection_id шоп-бота, НЕ покупателя.
            # Поэтому в заказ его НЕ сохраняем как buyer connection.
            purchase_data["business_connection_id"] = None

            order = await create_order_from_purchase(session, purchase_data)

            await send_to_admins(
                "✅ Покупка от шоп-бота обработана.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                f"Telegram ID покупателя: {order.customer_telegram_id}\n"
                f"Товар: {order.product_name}\n\n"
                "Теперь покупатель должен написать в ваш Telegram-аккаунт, "
                "например: Telegram / WhatsApp / Google."
            )

            # НЕ ПИШЕМ покупателю тут.
            # Потому что пока покупатель сам не написал в ваш аккаунт,
            # у нас нет его business_connection_id.
            return

        # 2. Проверяем, есть ли заказ, который ждёт сервис от этого покупателя.
        order = await find_waiting_service_order(session, sender.id)

        if order:
            order.business_connection_id = business_connection_id

            service_name = text.strip()

            if len(service_name) < 2:
                await bot.send_message(
                    chat_id=sender.id,
                    text="Напишите название сервиса, например: Telegram",
                    business_connection_id=business_connection_id,
                )
                return

            order.service_name = service_name
            order.status = "waiting_supplier_number"
            await session.commit()

            supplier = await get_supplier_for_service(session, service_name)

            if not supplier:
                order.status = "problem"
                await session.commit()

                await bot.send_message(
                    chat_id=sender.id,
                    text=(
                        "⚠️ Сейчас нет поставщика для этого сервиса.\n"
                        "Администратор уже получил уведомление."
                    ),
                    business_connection_id=business_connection_id,
                )

                await send_to_admins(
                    f"⚠️ Нет поставщика для сервиса: {service_name}\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"Покупатель: {order.customer_username or order.customer_telegram_id}"
                )
                return

            supplier_id = supplier.telegram_id

            await create_supplier_request(
                session=session,
                order=order,
                supplier_telegram_id=supplier_id,
                request_type="number",
            )

            try:
                await bot.send_message(
                    supplier_id,
                    f"📦 Новый заказ #{order.operation_id}\n\n"
                    f"Товар: {order.product_name}\n"
                    f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                    f"Сервис: {service_name}\n\n"
                    f"Нужен номер для получения кода.\n"
                    f"Можете прислать сообщение в любом формате — "
                    f"бот отправит покупателю только номер."
                )
            except Exception as e:
                order.status = "problem"
                await session.commit()

                await bot.send_message(
                    chat_id=sender.id,
                    text=(
                        "⚠️ Не смог отправить запрос поставщику.\n"
                        "Администратор уже получил уведомление."
                    ),
                    business_connection_id=business_connection_id,
                )

                await send_to_admins(
                    "⚠️ Не смог написать поставщику.\n\n"
                    f"Поставщик ID: {supplier_id}\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"Ошибка: {e}\n\n"
                    "Поставщик должен сначала открыть обычного бота и нажать /start."
                )
                return

            await bot.send_message(
                chat_id=sender.id,
                text=(
                    "Принято ✅\n\n"
                    "Запрос поставщику отправлен.\n"
                    "Скоро пришлю номер."
                ),
                business_connection_id=business_connection_id,
            )
            return

        # 3. Покупатель написал "код отправлен" текстом.
        lower_text = text.lower().strip()

        if lower_text in ["код отправлен", "отправил код", "код пришел", "код пришёл"]:
            from sqlalchemy import select

            result = await session.scalars(
                select(Order)
                .where(Order.customer_telegram_id == sender.id)
                .where(Order.status == "number_sent_to_customer")
                .order_by(Order.id.desc())
            )

            order = result.first()

            if not order:
                await bot.send_message(
                    chat_id=sender.id,
                    text=(
                        "Не нашёл активный заказ с выданным номером.\n"
                        "Если номер уже был выдан, напишите администратору."
                    ),
                    business_connection_id=business_connection_id,
                )
                return

            order.business_connection_id = business_connection_id
            order.status = "waiting_supplier_code"
            await session.commit()

            supplier = await get_supplier_for_service(session, order.service_name or "")

            if not supplier:
                order.status = "problem"
                await session.commit()

                await bot.send_message(
                    chat_id=sender.id,
                    text=(
                        "⚠️ Сейчас нет поставщика для этого сервиса.\n"
                        "Администратор уже получил уведомление."
                    ),
                    business_connection_id=business_connection_id,
                )

                await send_to_admins(
                    f"⚠️ Нет поставщика для сервиса: {order.service_name}\n"
                    f"Заказ: #{order.operation_id}"
                )
                return

            await create_supplier_request(
                session=session,
                order=order,
                supplier_telegram_id=supplier.telegram_id,
                request_type="code",
            )

            await bot.send_message(
                supplier.telegram_id,
                f"📩 По заказу #{order.operation_id} покупатель отправил код на номер:\n\n"
                f"{order.phone_number}\n\n"
                f"Выдайте код.\n"
                f"Можно прислать любой текст, покупателю уйдут только цифры."
            )

            await bot.send_message(
                chat_id=sender.id,
                text=(
                    "Принято ✅\n\n"
                    "Сообщил поставщику, что код отправлен.\n"
                    "Жду код."
                ),
                business_connection_id=business_connection_id,
            )
            return

        # 4. Сообщение пришло, но заказа под этого покупателя нет.
        await bot.send_message(
            chat_id=sender.id,
            text=(
                "Сообщение получено ✅\n\n"
                "Но я не нашёл активный заказ на ваш Telegram ID.\n"
                "Если вы уже оплатили, дождитесь сообщения о покупке или напишите администратору."
            ),
            business_connection_id=business_connection_id,
        )

        await send_to_admins(
            "⚠️ Business-сообщение пришло, но активный заказ не найден.\n\n"
            f"От ID: {sender.id}\n"
            f"Username: @{sender.username if sender.username else '-'}\n"
            f"Текст:\n{text}"
        )

@dp.business_message(F.text)
async def business_text_handler(message: Message):
    """
    Сообщения, которые приходят на обычный Telegram-аккаунт
    с подключённым Business-ботом.

    Тут ловим:
    1. сообщения от шоп-бота;
    2. сообщения от покупателя;
    3. любые business-сообщения для диагностики.
    """

    sender = message.from_user
    text = message.text or ""

    if not sender:
        await send_to_admins(
            "⚠️ Получил business-сообщение, но sender пустой.\n\n"
            f"Текст:\n{text}"
        )
        return

    business_connection_id = getattr(message, "business_connection_id", None)

    # ВАЖНО: диагностический лог.
    # Теперь админ будет видеть, кто именно написал в Business-аккаунт.
    await send_to_admins(
        "📩 Получено Business-сообщение.\n\n"
        f"От ID: {sender.id}\n"
        f"Username: @{sender.username if sender.username else '-'}\n"
        f"Имя: {sender.full_name}\n"
        f"Business connection: {business_connection_id or '-'}\n\n"
        f"Текст:\n{text[:1500]}"
    )

    async with SessionLocal() as session:
        # 1. Сначала пробуем понять, это покупка от шоп-бота или нет.
        purchase_data = extract_purchase_data(text)

        if purchase_data:
            purchase_data["business_connection_id"] = business_connection_id

            order = await create_order_from_purchase(session, purchase_data)

            await send_to_admins(
                "✅ Покупка из Business обработана.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                f"Товар: {order.product_name}\n\n"
                f"Статус: ждём сервис от покупателя."
            )

            await send_to_customer(
                order,
                "Оплата получена ✅\n\n"
                "Напишите, для какого сервиса нужен номер.\n"
                "Например: Telegram, WhatsApp, Google."
            )
            return

        # 2. Если это не покупка, значит это может быть сообщение покупателя с сервисом.
        order = await find_waiting_service_order(session, sender.id)

        if order:
            service_name = text.strip()

            if len(service_name) < 2:
                await message.answer("Напишите название сервиса, например: Telegram")
                return

            order.service_name = service_name
            order.business_connection_id = business_connection_id
            order.status = "waiting_supplier_number"
            await session.commit()

            supplier = await get_supplier_for_service(session, service_name)

            if not supplier:
                order.status = "problem"
                await session.commit()

                await message.answer(
                    "⚠️ Сейчас нет поставщика для этого сервиса.\n"
                    "Администратор уже получил уведомление."
                )

                await send_to_admins(
                    f"⚠️ Нет поставщика для сервиса: {service_name}\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"Покупатель: {order.customer_username or order.customer_telegram_id}"
                )
                return

            supplier_id = supplier.telegram_id

            await create_supplier_request(
                session=session,
                order=order,
                supplier_telegram_id=supplier_id,
                request_type="number",
            )

            await bot.send_message(
                supplier_id,
                f"📦 Новый заказ #{order.operation_id}\n\n"
                f"Товар: {order.product_name}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                f"Сервис: {service_name}\n\n"
                f"Нужен номер для получения кода.\n"
                f"Можете прислать сообщение в любом формате — "
                f"бот отправит покупателю только номер."
            )

            await message.answer(
                "Принято ✅\n\n"
                "Запрос поставщику отправлен.\n"
                "Скоро пришлю номер."
            )
            return

        # 3. Если покупатель пишет "код отправлен" текстом.
        lower_text = text.lower().strip()

        if lower_text in ["код отправлен", "отправил код", "код пришел", "код пришёл"]:
            await message.answer(
                "Не нашёл активный заказ с выданным номером.\n"
                "Если номер уже был выдан, напишите администратору."
            )
            return

        # 4. Если сообщение пришло, но бот его не понял.
        await send_to_admins(
            "⚠️ Business-сообщение пришло, но бот не понял его как покупку или сервис.\n\n"
            f"От: @{sender.username if sender.username else sender.id}\n"
            f"Текст:\n{text}"
        )

        await message.answer(
            "Сообщение получено ✅\n\n"
            "Если вы уже оплатили заказ, дождитесь обработки покупки."
        )

@dp.callback_query(F.data.startswith("customer_code_sent:"))
async def customer_code_sent_handler(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await session.get(Order, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if callback.from_user.id != order.customer_telegram_id:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return

        if order.status != "number_sent_to_customer":
            await callback.answer("Сейчас нельзя запросить код", show_alert=True)
            return

        order.status = "waiting_supplier_code"
        await session.commit()

        supplier = await get_supplier_for_service(session, order.service_name or "")

        if not supplier:
            order.status = "problem"
            await session.commit()

            await callback.message.answer(
                "⚠️ Сейчас нет поставщика для этого сервиса.\n"
                "Администратор уже получил уведомление."
            )

            await send_to_admins(
                f"⚠️ Нет поставщика для сервиса: {order.service_name}\n"
                f"Заказ: #{order.operation_id}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}"
            )

            await callback.answer()
            return

        supplier_id = supplier.telegram_id

        await create_supplier_request(
            session=session,
            order=order,
            supplier_telegram_id=supplier_id,
            request_type="code",
        )

        await bot.send_message(
            supplier_id,
            f"📩 По заказу #{order.operation_id} покупатель отправил код на номер:\n\n"
            f"{order.phone_number}\n\n"
            f"Выдайте код.\n"
            f"Можно прислать любой текст, но покупателю уйдут только цифры."
        )

        await callback.message.answer(
            "Принято ✅\n\n"
            "Сообщил поставщику, что код отправлен.\n"
            "Жду код."
        )

        await callback.answer()


@dp.callback_query(F.data.startswith("confirm_success:"))
async def confirm_success_handler(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await session.get(Order, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if callback.from_user.id != order.customer_telegram_id:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return

        order.status = "confirmed"
        await session.commit()

        await callback.message.answer(
            "Спасибо за подтверждение ✅\n\n"
            "Заказ завершён."
        )

        await send_to_admins(
            f"✅ Заказ #{order.operation_id} успешно завершён.\n"
            f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
            f"Сервис: {order.service_name}\n"
            f"Номер: {order.phone_number}\n"
            f"Код: {order.verification_code}"
        )

        await callback.answer()


@dp.callback_query(F.data.startswith("number_invalid:"))
async def number_invalid_handler(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await session.get(Order, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if callback.from_user.id != order.customer_telegram_id:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return

        order.status = "problem"
        await session.commit()

        await callback.message.answer(
            "Понял. Передал проблему администратору."
        )

        await send_to_admins(
            f"⚠️ Проблема с номером по заказу #{order.operation_id}\n"
            f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
            f"Номер: {order.phone_number}"
        )

        await callback.answer()


@dp.callback_query(F.data.startswith("code_invalid:"))
async def code_invalid_handler(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        order = await session.get(Order, order_id)

        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if callback.from_user.id != order.customer_telegram_id:
            await callback.answer("Это не ваш заказ", show_alert=True)
            return

        order.status = "problem"
        await session.commit()

        await callback.message.answer(
            "Понял. Передал проблему администратору."
        )

        await send_to_admins(
            f"⚠️ Проблема с кодом по заказу #{order.operation_id}\n"
            f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
            f"Номер: {order.phone_number}\n"
            f"Код: {order.verification_code}"
        )

        await callback.answer()


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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