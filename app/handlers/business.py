import logging
import re

from aiogram import Router
from aiogram.types import BusinessConnection, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BusinessConnectionRecord, OrderEvent

router = Router(name="business")
logger = logging.getLogger(__name__)


@router.business_connection()
async def business_connection_handler(
    connection: BusinessConnection,
    session: AsyncSession,
) -> None:
    record = await session.scalar(
        select(BusinessConnectionRecord).where(
            BusinessConnectionRecord.connection_id == connection.id
        )
    )
    if record is None:
        record = BusinessConnectionRecord(
            connection_id=connection.id,
            user_chat_id=connection.user_chat_id,
            is_enabled=connection.is_enabled,
        )
        session.add(record)
    else:
        record.user_chat_id = connection.user_chat_id
        record.is_enabled = connection.is_enabled

    await session.commit()
    logger.info(
        "Business connection updated: id=%s enabled=%s",
        connection.id,
        connection.is_enabled,
    )


@router.business_message()
async def business_message_handler(
    message: Message,
    session: AsyncSession,
) -> None:
    # Не обрабатываем сообщения, отправленные самим ботом.
    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption or ""
    logger.info(
        "Business message: chat_id=%s connection_id=%s text=%r",
        message.chat.id,
        message.business_connection_id,
        text[:500],
    )

    # Базовый пример распознавания номера заказа.
    order_match = re.search(
        r"(?:заказ|order)\s*[#№:]?\s*(\d{3,})",
        text,
        re.IGNORECASE,
    )
    if order_match:
        session.add(
            OrderEvent(
                order_id=0,  # Заменяется после настройки реального парсера Admaker.
                actor_telegram_id=(
                    message.from_user.id if message.from_user else None
                ),
                event_type="unmatched_business_order_message",
                payload=text[:4000],
            )
        )
        # Не коммитим запись с order_id=0, потому что FK не разрешит её.
        await session.rollback()

    await message.answer(
        "Сообщение получено. Для создания заявки используйте /new_order.",
        business_connection_id=message.business_connection_id,
    )
