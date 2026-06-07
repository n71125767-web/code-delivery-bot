from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services import upsert_user

router = Router(name="common")


@router.message(CommandStart())
async def start_handler(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await upsert_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        admin_ids=settings.admin_ids,
    )
    await message.answer(
        "Бот запущен.\n\n"
        f"Ваша роль: {user.role.value}\n\n"
        "Команды:\n"
        "/profile — профиль\n"
        "/new_order — создать заявку\n"
        "/my_orders — мои заявки\n"
        "/available_orders — свободные заявки поставщика"
    )


@router.message(Command("profile"))
async def profile_handler(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    user = await upsert_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        admin_ids=settings.admin_ids,
    )
    username = f"@{user.username}" if user.username else "отсутствует"
    await message.answer(
        f"ID: {user.telegram_id}\n"
        f"Имя: {user.full_name}\n"
        f"Username: {username}\n"
        f"Роль: {user.role.value}"
    )
