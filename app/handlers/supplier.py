from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.keyboards import order_actions
from app.models import Order, OrderStatus, UserRole
from app.services import (
    add_order_event,
    get_order,
    list_available_orders,
    list_supplier_orders,
    upsert_user,
)
from app.states import SupplierDeliveryStates

router = Router(name="supplier")


async def require_supplier(
    message: Message,
    session: AsyncSession,
    settings: Settings,
):
    user = await upsert_user(
        session,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        settings.admin_ids,
    )
    if user.role not in {UserRole.SUPPLIER, UserRole.ADMIN}:
        await message.answer("Эта команда доступна только поставщику.")
        return None
    return user


@router.message(Command("supplier"))
async def supplier_panel(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await require_supplier(message, session, settings)
    if user is None:
        return
    await message.answer(
        "Панель поставщика:\n"
        "/available_orders — свободные заявки\n"
        "/my_supplier_orders — мои принятые заявки"
    )


@router.message(Command("available_orders"))
async def available_orders(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await require_supplier(message, session, settings)
    if user is None:
        return

    orders = await list_available_orders(session)
    if not orders:
        await message.answer("Свободных заявок нет.")
        return

    for order in orders:
        await message.answer(
            f"Заявка #{order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name or '—'}\n"
            f"Комментарий: {order.customer_note or '—'}",
            reply_markup=order_actions(order.id, order.status.value),
        )


@router.message(Command("my_supplier_orders"))
async def my_supplier_orders(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await require_supplier(message, session, settings)
    if user is None:
        return

    orders = await list_supplier_orders(session, user.id)
    if not orders:
        await message.answer("Принятых заявок нет.")
        return

    for order in orders:
        await message.answer(
            f"Заявка #{order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Статус: {order.status.value}",
            reply_markup=order_actions(order.id, order.status.value),
        )


@router.callback_query(F.data.startswith("order:accept:"))
async def accept_order(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    supplier = await upsert_user(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
        settings.admin_ids,
    )
    if supplier.role not in {UserRole.SUPPLIER, UserRole.ADMIN}:
        await callback.answer("Только для поставщика.", show_alert=True)
        return

    order_id = int(callback.data.rsplit(":", 1)[1])

    # Блокируем строку, чтобы два поставщика не приняли одну заявку.
    from sqlalchemy import select

    result = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
    )
    order = result.scalar_one_or_none()

    if order is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    if order.supplier_id is not None or order.status != OrderStatus.WAITING_SUPPLIER:
        await callback.answer("Заявка уже занята.", show_alert=True)
        await session.rollback()
        return

    order.supplier_id = supplier.id
    order.status = OrderStatus.ACCEPTED
    await add_order_event(
        session,
        order.id,
        "accepted",
        callback.from_user.id,
    )
    await session.commit()

    await callback.message.edit_text(
        f"Вы приняли заявку #{order.id}.\n"
        "Нажмите «Передать товар», когда он будет готов.",
        reply_markup=order_actions(order.id, order.status.value),
    )
    await callback.answer("Заявка принята.")


@router.callback_query(F.data.startswith("order:deliver:"))
async def start_delivery(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    order_id = int(callback.data.rsplit(":", 1)[1])
    order = await get_order(session, order_id)

    if order is None or order.supplier is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    if order.supplier.telegram_id != callback.from_user.id:
        await callback.answer("Заявка назначена другому поставщику.", show_alert=True)
        return

    await state.set_state(SupplierDeliveryStates.payload)
    await state.update_data(order_id=order_id)
    await callback.message.answer(
        "Отправьте товар, номер, аккаунт, прокси или код одним сообщением."
    )
    await callback.answer()


@router.message(SupplierDeliveryStates.payload)
async def finish_delivery(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not message.text:
        await message.answer("В MVP выдача поддерживает только текст.")
        return

    data = await state.get_data()
    order = await get_order(session, int(data["order_id"]))

    if (
        order is None
        or order.supplier is None
        or order.supplier.telegram_id != message.from_user.id
    ):
        await state.clear()
        await message.answer("Заявка не найдена.")
        return

    order.supplier_payload = message.text
    order.status = OrderStatus.DELIVERED
    await add_order_event(
        session,
        order.id,
        "delivered",
        message.from_user.id,
    )
    await session.commit()
    await state.clear()

    await message.bot.send_message(
        chat_id=order.customer.telegram_id,
        text=(
            f"Товар по заявке #{order.id}:\n\n"
            f"{order.supplier_payload}\n\n"
            "Проверьте товар и подтвердите получение."
        ),
        reply_markup=order_actions(order.id, order.status.value),
    )
    await message.answer(f"Товар по заявке #{order.id} отправлен покупателю.")
