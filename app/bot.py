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
)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_supplier(user_id: int) -> bool:
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


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Бот запущен.\n\n"
        "Покупатель после покупки пишет сюда сервис.\n"
        "Поставщик присылает номер/код.\n"
        "Админ может отправить тестовое сообщение о покупке."
    )


@dp.message(Command("status"))
async def status_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("✅ Сервис работает")


@dp.message(F.text)
async def text_handler(message: Message):
    user_id = message.from_user.id
    text = message.text or ""

    async with SessionLocal() as session:
        purchase_data = extract_purchase_data(text)

        if purchase_data and is_admin(user_id):
            order = await create_order_from_purchase(session, purchase_data)

            await message.answer(
                f"✅ Покупка обработана.\n\n"
                f"Заказ: #{order.operation_id}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                f"Товар: {order.product_name}\n\n"
                f"Статус: ждём сервис от покупателя."
            )

            try:
                await bot.send_message(
                    order.customer_telegram_id,
                    "Оплата получена ✅\n\n"
                    "Напишите, для какого сервиса нужен номер.\n"
                    "Например: Telegram, WhatsApp, Google."
                )
            except Exception as e:
                await message.answer(
                    "⚠️ Не смог написать покупателю в личку.\n"
                    "Покупатель должен сначала нажать /start в боте.\n\n"
                    f"Ошибка: {e}"
                )

            return

        if is_supplier(user_id):
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

                await bot.send_message(
                    order_for_number.customer_telegram_id,
                    f"Ваш номер для сервиса {order_for_number.service_name}:\n\n"
                    f"{phone}\n\n"
                    f"Введите этот номер в сервисе.\n"
                    f"Когда сервис отправит код, нажмите кнопку ниже.",
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

                await bot.send_message(
                    order_for_code.customer_telegram_id,
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

        order = await find_waiting_service_order(session, user_id)

        if order:
            service_name = text.strip()

            if len(service_name) < 2:
                await message.answer("Напишите название сервиса, например: Telegram")
                return

            order.service_name = service_name
            order.status = "waiting_supplier_number"
            await session.commit()

            if not SUPPLIER_IDS:
                await message.answer("⚠️ Нет поставщика в SUPPLIER_IDS.")
                return

            supplier_id = SUPPLIER_IDS[0]

            await create_supplier_request(
                session=session,
                order=order,
                supplier_telegram_id=supplier_id,
                request_type="number",
            )

            await bot.send_message(
                supplier_id,
                f"Новый заказ #{order.operation_id}\n\n"
                f"Товар: {order.product_name}\n"
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

        await message.answer(
            "Не понял сообщение.\n\n"
            "Если вы покупатель — дождитесь обработки покупки.\n"
            "Если вы поставщик — дождитесь запроса от бота."
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

        order.status = "waiting_supplier_code"
        await session.commit()

        supplier_id = SUPPLIER_IDS[0]

        await create_supplier_request(
            session=session,
            order=order,
            supplier_telegram_id=supplier_id,
            request_type="code",
        )

        await bot.send_message(
            supplier_id,
            f"По заказу #{order.operation_id} покупатель отправил код на номер:\n\n"
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

        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
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

        order.status = "problem"
        await session.commit()

        await callback.message.answer(
            "Понял. Передал проблему администратору."
        )

        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
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

        order.status = "problem"
        await session.commit()

        await callback.message.answer(
            "Понял. Передал проблему администратору."
        )

        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                f"⚠️ Проблема с кодом по заказу #{order.operation_id}\n"
                f"Покупатель: {order.customer_username or order.customer_telegram_id}\n"
                f"Номер: {order.phone_number}\n"
                f"Код: {order.verification_code}"
            )

        await callback.answer()


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())