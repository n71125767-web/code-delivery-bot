from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SUPPLIER_IDS
from app.models import Order
from app.services import create_supplier_request, mark_order_waiting_supplier
from app.utils import safe_send_message


def choose_supplier_for_order(order: Order, buyer_message: str) -> int | None:
    if not SUPPLIER_IDS:
        return None

    return SUPPLIER_IDS[0]


async def send_supplier_request(
    bot: Bot,
    session: AsyncSession,
    order: Order,
    buyer_message: str,
    buyer_business_connection_id: str | None = None,
) -> tuple[bool, str | None]:
    supplier_id = choose_supplier_for_order(order, buyer_message)

    if not supplier_id:
        return False, "SUPPLIER_IDS пустой. Добавь ID поставщика в Render Environment."

    await mark_order_waiting_supplier(
        session=session,
        order=order,
        supplier_id=supplier_id,
        buyer_message=buyer_message,
        business_connection_id=buyer_business_connection_id,
    )

    await create_supplier_request(
        session=session,
        order_id=order.id,
        supplier_telegram_id=supplier_id,
        request_type="product",
        buyer_message=buyer_message,
    )

    text = (
        "Новый заказ:\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"Покупатель: @{order.customer_username or 'нет'} / {order.customer_telegram_id or 'нет ID'}\n"
        f"Товар: {order.product_name or 'не указан'}\n"
        f"Запрос покупателя: {buyer_message}\n\n"
        "Пожалуйста, выдайте товар/код/номер для этого заказа."
    )

    return await safe_send_message(
        bot=bot,
        chat_id=supplier_id,
        text=text,
        business_connection_id=buyer_business_connection_id,
    )