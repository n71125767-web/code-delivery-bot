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

# За сколько часов покупка считается актуальной.
# Это нужно, чтобы бот не выдал товар человеку по старому заказу.
PURCHASE_LOOKBACK_HOURS = 24


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_supplier_from_env(user_id: int) -> bool:
    return user_id in SUPPLIER_IDS


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


async def send_business_text(
    chat_id: int,
    business_connection_id: str | None,
    text: str,
    reply_markup=None,
) -> bool:
    """
    Отправка сообщения через Telegram Business.

    Важно:
    если business_connection_id нет, бот НЕ пытается писать как обычный бот,
    чтобы не ловить Bad Request: chat not found.
    """

    if not business_connection_id:
        return False

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            business_connection_id=business_connection_id,
        )
        return True

    except TypeError:
        await send_to_admins(
            "⚠️ aiogram не поддерживает business_connection_id.\n\n"
            "Обнови requirements.txt:\n"
            "aiogram>=3.10.0\n\n"
            "Потом сделай git push и Clear build cache & deploy на Render."
        )
        return False

    except Exception as e:
        await send_to_admins(
            "⚠️ Не смог отправить Business-сообщение.\n\n"
            f"Получатель: {chat_id}\n"
            f"Ошибка: {e}"
        )
        return False


async def send_to_customer(order: Order, text: str, reply_markup=None) -> bool:
    """
    Отправка покупателю.

    Отправляем только через business_connection_id покупателя.
    Не используем обычный bot.send_message без business_connection_id,
    чтобы не было ошибки chat not found.
    """

    if not order.business_connection_id:
        await send_to_admins(
            "⚠️ Не могу написать покупателю.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"Покупатель: {order.customer_username or order.customer_telegram_id}\n\n"
            "Причина: покупатель ещё не написал в ваш Telegram-аккаунт, "
            "поэтому нет business_connection_id покупателя."
        )
        return False

    return await send_business_text(
        chat_id=order.customer_telegram_id,
        business_connection_id=order.business_connection_id,
        text=text,
        reply_markup=reply_markup,
    )


async def get_active_supplier_by_user_id(session, user_id: int):
    suppliers = await list_suppliers(session)

    for supplier in suppliers:
        if supplier.telegram_id == user_id:
            return supplier

    return None


def get_day_limit() -> datetime:
    """
    Возвращает время, начиная с которого покупка считается актуальной.
    Сейчас используется последние 24 часа.
    """

    return datetime.utcnow() - timedelta(hours=PURCHASE_LOOKBACK_HOURS)


async def find_waiting_service_order_for_today_customer(
    session,
    customer_telegram_id: int,
) -> Order | None:
    """
    Ищем заказ покупателя, который:
    - создан за последние 24 часа;
    - принадлежит именно этому Telegram ID;
    - ждёт название сервиса.

    Это главная защита от ошибки выдачи товара не тому человеку.
    """

    result = await session.scalars(
        select(Order)
        .where(Order.customer_telegram_id == customer_telegram_id)
        .where(Order.status == "waiting_service")
        .where(Order.created_at >= get_day_limit())
        .order_by(Order.id.desc())
    )

    return result.first()


async def find_number_sent_order_for_today_customer(
    session,
    customer_telegram_id: int,
) -> Order | None:
    """
    Ищем заказ покупателя за последние 24 часа,
    которому уже выдали номер и который может запросить код.
    """

    result = await session.scalars(
        select(Order)
        .where(Order.customer_telegram_id == customer_telegram_id)
        .where(Order.status == "number_sent_to_customer")
        .where(Order.created_at >= get_day_limit())
        .order_by(Order.id.desc())
    )

    return result.first()


async def find_any_active_order_for_today_customer(
    session,
    customer_telegram_id: int,
) -> Order | None:
    """
    Ищем любой активный заказ за последние 24 часа.
    Это нужно, чтобы не путать старые заказы и не отвечать левым людям.
    """

    result = await session.scalars(
        select(Order)
        .where(Order.customer_telegram_id == customer_telegram_id)
        .where(Order.created_at >= get_day_limit())
        .where(
            Order.status.in_(
                [
                    "waiting_service",
                    "waiting_supplier_number",
                    "number_sent_to_customer",
                    "waiting_supplier_code",
                    "code_sent_to_customer",
                ]
            )
        )
        .order_by(Order.id.desc())
    )

    return result.first()


async def notify_no_supplier(order: Order, service_name: str, customer_business_connection_id: str | None = None):
    order.status = "problem"

    await send_to_admins(
        f"⚠️ Нет поставщика для сервиса: {service_name}\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
        f"Товар: {order.product_name}"
    )

    if customer_business_connection_id:
        await send_business_text(
            chat_id=order.customer_telegram_id,
            business_connection_id=customer_business_connection_id,
            text=(
                "⚠️ Сейчас нет поставщика для этого сервиса.\n"
                "Администратор уже получил уведомление."
            ),
        )


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
    Business-сообщения с обычного Telegram-аккаунта.

    Логика:
    1. Если сообщение похоже на покупку — создаём заказ.
    2. Если пишет бот и это не покупка — игнорируем, чтобы не было циклов.
    3. Если пишет админ — игнорируем в Business, админ работает через обычного бота.
    4. Если пишет покупатель — сверяем его Telegram ID с покупками за последние 24 часа.
    """

    sender = message.from_user
    text = (message.text or "").strip()

    if not sender or not text:
        return

    business_connection_id = getattr(message, "business_connection_id", None)
    sender_is_bot = getattr(sender, "is_bot", False)

    async with SessionLocal() as session:
        purchase_data = extract_purchase_data(text)

        if purchase_data:
            # Это сообщение от шоп-бота/системы покупки.
            # business_connection_id тут НЕ покупателя, поэтому его не сохраняем.
            purchase_data["business_connection_id"] = None

            order = await create_order_from_purchase(session, purchase_data)

            await send_to_admins(
                "✅ Покупка обработана.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                f"Telegram ID покупателя: {order.customer_telegram_id}\n"
                f"Товар: {order.product_name}\n\n"
                "Покупатель должен написать в ваш аккаунт название сервиса.\n"
                f"Проверка выдачи будет только по покупкам за последние {PURCHASE_LOOKBACK_HOURS} ч."
            )
            return

        # Если сообщение от бота, но это не покупка — игнорируем.
        # Это защита от дублей и ответов самому себе.
        if sender_is_bot:
            return

        # Админа в Business-чате не обрабатываем как покупателя.
        if is_admin(sender.id):
            return

        lower_text = text.lower()

        # Покупатель пишет "код отправлен".
        if lower_text in ["код отправлен", "отправил код", "код пришел", "код пришёл"]:
            order = await find_number_sent_order_for_today_customer(session, sender.id)

            if not order:
                # Не отвечаем постоянно, чтобы не спамить.
                return

            order.business_connection_id = business_connection_id
            order.status = "waiting_supplier_code"
            await session.commit()

            supplier = await get_supplier_for_service(session, order.service_name or "")

            if not supplier:
                await notify_no_supplier(order, order.service_name or "-", business_connection_id)
                await session.commit()
                return

            await create_supplier_request(
                session=session,
                order=order,
                supplier_telegram_id=supplier.telegram_id,
                request_type="code",
            )

            try:
                await bot.send_message(
                    supplier.telegram_id,
                    f"📩 По заказу #{order.operation_id} покупатель отправил код на номер:\n\n"
                    f"{order.phone_number}\n\n"
                    f"Выдайте код.\n"
                    f"Можно прислать любой текст, покупателю уйдут только цифры."
                )
            except Exception as e:
                order.status = "problem"
                await session.commit()

                await send_to_admins(
                    "⚠️ Не смог написать поставщику для запроса кода.\n\n"
                    f"Поставщик ID: {supplier.telegram_id}\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"Ошибка: {e}"
                )
                return

            await send_business_text(
                chat_id=sender.id,
                business_connection_id=business_connection_id,
                text=(
                    "Принято ✅\n\n"
                    "Сообщил поставщику, что код отправлен.\n"
                    "Жду код."
                ),
            )
            return

        # Покупатель пишет название сервиса.
        order = await find_waiting_service_order_for_today_customer(session, sender.id)

        if order:
            service_name = text.strip()

            if len(service_name) < 2:
                await send_business_text(
                    chat_id=sender.id,
                    business_connection_id=business_connection_id,
                    text="Напишите название сервиса, например: Telegram",
                )
                return

            order.business_connection_id = business_connection_id
            order.service_name = service_name
            order.status = "waiting_supplier_number"
            await session.commit()

            supplier = await get_supplier_for_service(session, service_name)

            if not supplier:
                await notify_no_supplier(order, service_name, business_connection_id)
                await session.commit()
                return

            await create_supplier_request(
                session=session,
                order=order,
                supplier_telegram_id=supplier.telegram_id,
                request_type="number",
            )

            try:
                await bot.send_message(
                    supplier.telegram_id,
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

                await send_business_text(
                    chat_id=sender.id,
                    business_connection_id=business_connection_id,
                    text=(
                        "⚠️ Не смог отправить запрос поставщику.\n"
                        "Администратор уже получил уведомление."
                    ),
                )

                await send_to_admins(
                    "⚠️ Не смог написать поставщику.\n\n"
                    f"Поставщик ID: {supplier.telegram_id}\n"
                    f"Заказ: #{order.operation_id}\n"
                    f"Ошибка: {e}\n\n"
                    "Поставщик должен открыть обычного бота и нажать /start."
                )
                return

            await send_business_text(
                chat_id=sender.id,
                business_connection_id=business_connection_id,
                text=(
                    "Принято ✅\n\n"
                    "Запрос поставщику отправлен.\n"
                    "Скоро пришлю номер."
                ),
            )
            return

        # Если у человека есть активный заказ за сегодня, но не на этом этапе.
        active_order = await find_any_active_order_for_today_customer(session, sender.id)

        if active_order:
            # Не спамим на каждое сообщение, отвечаем только нейтрально.
            await send_business_text(
                chat_id=sender.id,
                business_connection_id=business_connection_id,
                text=(
                    "Ваш заказ уже в обработке ✅\n\n"
                    f"Текущий статус: {active_order.status}"
                ),
            )
            return

        # Если человек не покупал за последние 24 часа — ничего не выдаём и не спамим.
        return


@dp.message(F.text)
async def text_handler(message: Message):
    """
    Обычные сообщения обычному боту.

    Здесь работают:
    - админ;
    - поставщик;
    - ручной тест покупки от админа.
    """

    user_id = message.from_user.id
    text = message.text or ""

    async with SessionLocal() as session:
        purchase_data = extract_purchase_data(text)

        if purchase_data and is_admin(user_id):
            purchase_data["business_connection_id"] = None

            order = await create_order_from_purchase(session, purchase_data)

            await message.answer(
                f"✅ Покупка обработана вручную.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                f"Telegram ID покупателя: {order.customer_telegram_id}\n"
                f"Товар: {order.product_name}\n\n"
                f"Статус: ждём сервис от покупателя."
            )
            return

        db_supplier = await get_active_supplier_by_user_id(session, user_id)
        is_supplier = db_supplier is not None or is_supplier_from_env(user_id)

        if is_supplier:
            order_for_number = await find_order_waiting_supplier_number(session, user_id)

            if order_for_number:
                phone = extract_phone(text)

                if not phone:
                    await message.answer(
                        "Не нашёл номер в сообщении.\n"
                        "Можно прислать любой текст, но в нём должен быть номер.\n"
                        "Пример: номер +79990000000"
                    )
                    return

                order_for_number.phone_number = phone
                order_for_number.status = "number_sent_to_customer"

                await close_supplier_request(
                    session=session,
                    order=order_for_number,
                    supplier_telegram_id=user_id,
                    request_type="number",
                )

                await session.commit()

                await send_to_customer(
                    order_for_number,
                    f"Ваш номер для сервиса {order_for_number.service_name}:\n\n"
                    f"{phone}\n\n"
                    f"Введите этот номер в сервисе.\n"
                    f"Когда сервис отправит код, напишите: Код отправлен.",
                    reply_markup=code_sent_keyboard(order_for_number.id),
                )

                await message.answer(
                    f"✅ Номер принят и отправлен покупателю.\n"
                    f"Заказ #{order_for_number.operation_id}"
                )
                return

            order_for_code = await find_order_waiting_supplier_code(session, user_id)

            if order_for_code:
                code = extract_code(text)

                if not code:
                    await message.answer(
                        "Не нашёл код в сообщении.\n"
                        "Можно прислать любой текст, но в нём должны быть цифры кода.\n"
                        "Пример: код 123456"
                    )
                    return

                order_for_code.verification_code = code
                order_for_code.status = "code_sent_to_customer"

                await close_supplier_request(
                    session=session,
                    order=order_for_code,
                    supplier_telegram_id=user_id,
                    request_type="code",
                )

                await session.commit()

                await send_to_customer(
                    order_for_code,
                    f"Ваш код:\n\n{code}\n\n"
                    f"Введите его в сервисе.\n"
                    f"После успешной привязки нажмите кнопку ниже.",
                    reply_markup=confirm_keyboard(order_for_code.id),
                )

                await message.answer(
                    f"✅ Код принят и отправлен покупателю.\n"
                    f"Заказ #{order_for_code.operation_id}"
                )
                return

            await message.answer(
                "Вы поставщик, но сейчас нет активного запроса на номер или код."
            )
            return

        await message.answer(
            "Не понял сообщение.\n\n"
            "Если вы поставщик — дождитесь запроса от бота.\n"
            "Если вы админ — используйте /status или /suppliers."
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

        if order.created_at < get_day_limit():
            await callback.answer("Заказ устарел", show_alert=True)
            return

        if order.status != "number_sent_to_customer":
            await callback.answer("Сейчас нельзя запросить код", show_alert=True)
            return

        order.status = "waiting_supplier_code"
        await session.commit()

        supplier = await get_supplier_for_service(session, order.service_name or "")

        if not supplier:
            await notify_no_supplier(order, order.service_name or "-")
            await session.commit()
            await callback.answer()
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