from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.keyboards import order_actions
from app.models import OrderStatus
from app.services import (
    add_order_event,
    create_order,
    get_order,
    list_customer_orders,
    upsert_user,
)
from app.states import NewOrderStates

router = Router(name="orders")


@router.message(Command("new_order"))
async def new_order_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(NewOrderStates.product_name)
    await message.answer("Напишите название товара.")


@router.message(NewOrderStates.product_name)
async def new_order_product(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Нужно отправить текст.")
        return
    await state.update_data(product_name=message.text.strip())
    await state.set_state(NewOrderStates.service_name)
    await message.answer("Напишите сервис или поставьте «-», если сервис не нужен.")


@router.message(NewOrderStates.service_name)
async def new_order_service(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Нужно отправить текст.")
        return
    service_name = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(service_name=service_name)
    await state.set_state(NewOrderStates.note)
    await message.answer("Добавьте комментарий или поставьте «-».")


@router.message(NewOrderStates.note)
async def new_order_note(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not message.text:
        await message.answer("Нужно отправить текст.")
        return

    data = await state.get_data()
    note = None if message.text.strip() == "-" else message.text.strip()

    user = await upsert_user(
        session,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        settings.admin_ids,
    )
    order = await create_order(
        session,
        customer=user,
        product_name=data["product_name"],
        service_name=data.get("service_name"),
        note=note,
    )
    await state.clear()

    await message.answer(
        f"Заявка #{order.id} создана.\n"
        f"Товар: {order.product_name}\n"
        f"Сервис: {order.service_name or 'не указан'}\n"
        f"Статус: {order.status.value}"
    )


@router.message(Command("my_orders"))
async def my_orders_handler(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await upsert_user(
        session,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        settings.admin_ids,
    )
    orders = await list_customer_orders(session, user.id)
    if not orders:
        await message.answer("У вас пока нет заявок.")
        return

    for order in orders:
        await message.answer(
            f"Заявка #{order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name or '—'}\n"
            f"Статус: {order.status.value}",
            reply_markup=order_actions(order.id, order.status.value),
        )


@router.callback_query(F.data.startswith("order:confirm:"))
async def confirm_order(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    order_id = int(callback.data.rsplit(":", 1)[1])
    order = await get_order(session, order_id)
    if order is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    if order.customer.telegram_id != callback.from_user.id:
        await callback.answer("Это не ваша заявка.", show_alert=True)
        return

    if order.status != OrderStatus.DELIVERED:
        await callback.answer("Заявка ещё не выдана.", show_alert=True)
        return

    order.status = OrderStatus.COMPLETED
    await add_order_event(
        session,
        order.id,
        "confirmed",
        callback.from_user.id,
    )
    await session.commit()
    await callback.message.edit_text(
        f"Заявка #{order.id} успешно завершена."
    )
    await callback.answer("Получение подтверждено.")


@router.callback_query(F.data.startswith("order:dispute:"))
async def dispute_order(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    order_id = int(callback.data.rsplit(":", 1)[1])
    order = await get_order(session, order_id)
    if order is None or order.customer.telegram_id != callback.from_user.id:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    order.status = OrderStatus.DISPUTED
    await add_order_event(
        session,
        order.id,
        "disputed",
        callback.from_user.id,
    )
    await session.commit()
    await callback.message.edit_text(
        f"По заявке #{order.id} открыт спор. Администратор должен проверить заявку."
    )
    await callback.answer()
