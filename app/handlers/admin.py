from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Order, User, UserRole

router = Router(name="admin")


def is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def admin_panel(message: Message, settings: Settings) -> None:
    if not is_admin(message.from_user.id, settings):
        return
    await message.answer(
        "Админ-панель:\n"
        "/make_supplier ID\n"
        "/make_customer ID\n"
        "/orders"
    )


async def change_role(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
    role: UserRole,
) -> None:
    if not is_admin(message.from_user.id, settings):
        return
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Укажите Telegram ID.")
        return

    telegram_id = int(command.args.strip())
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )
    if user is None:
        await message.answer("Пользователь сначала должен нажать /start.")
        return

    user.role = role
    await session.commit()
    await message.answer(f"Роль пользователя {telegram_id}: {role.value}")


@router.message(Command("make_supplier"))
async def make_supplier(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await change_role(
        message,
        command,
        session,
        settings,
        UserRole.SUPPLIER,
    )


@router.message(Command("make_customer"))
async def make_customer(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await change_role(
        message,
        command,
        session,
        settings,
        UserRole.CUSTOMER,
    )


@router.message(Command("orders"))
async def admin_orders(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not is_admin(message.from_user.id, settings):
        return

    orders = list(
        await session.scalars(
            select(Order).order_by(Order.id.desc()).limit(30)
        )
    )
    if not orders:
        await message.answer("Заявок нет.")
        return

    text = "\n".join(
        f"#{order.id} | {order.status.value} | {order.product_name}"
        for order in orders
    )
    await message.answer(text)
