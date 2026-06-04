import asyncio
import logging
import re
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message, CallbackQuery

from app.config import (
    ADMIN_IDS,
    ADMIN_ALERT_CHAT_ID,
    SHOP_BOT_USERNAME,
    IGNORE_OTHER_BOTS,
    ADMIN_BUSINESS_CONNECTION_ID,
    SERVICE_PAGE_SIZE,
    SUPPLIER_PAGE_SIZE,
    PROBLEM_COOLDOWN_SECONDS,
)
from app.database import SessionLocal
from app.keyboards import (
    confirm_keyboard,
    number_keyboard,
    service_keyboard,
    service_keyboard_from_services,
    admin_panel_keyboard,
    supplier_panel_keyboard,
)
from app.parsers import extract_purchase_data, extract_phone, extract_code
from app.senders import safe_send_message, answer_message
from app.services import (
    create_or_update_order_from_purchase,
    find_active_order_for_customer,
    find_waiting_service_order_for_customer,
    create_supplier_request,
    find_waiting_supplier_request,
    get_order_by_id,
    get_status_text,
    get_last_orders_text,
    set_customer_by_order_id,
    add_supplier,
    remove_supplier,
    list_suppliers_text,
    bind_supplier_to_product,
    unbind_supplier_from_product,
    find_supplier_for_order,
    add_service,
    remove_service,
    set_service_emoji,
    get_services_page,
    find_service_by_slug,
    find_service_by_text,
    increment_service_usage,
    services_text,
    get_text,
    set_text,
    texts_text,
    check_cooldown,
    supplier_pending_text,
    add_service_list,
    add_service_to_list,
    lists_text,
)

logger = logging.getLogger(__name__)

CONTACT_PATTERNS = [
    r"@[a-zA-Z0-9_]{3,}",
    r"(?:https?://)?t\.me/[a-zA-Z0-9_]{3,}",
    r"(?:https?://)?telegram\.me/[a-zA-Z0-9_]{3,}",
    r"\b(?:мой|моя|напиши|пиши|свяжись|связь|контакт|личка|лс|л/с)\b.*\b[a-zA-Z0-9_]{4,}\b",
    r"\+?\d[\d\s\-\(\)]{8,}\d",
]
CONTACT_RE = re.compile("|".join(CONTACT_PATTERNS), re.IGNORECASE)


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def get_business_id(message: Message | None, fallback: str | None = None) -> str | None:
    if message is None:
        return fallback or ADMIN_BUSINESS_CONNECTION_ID

    return (
        getattr(message, "business_connection_id", None)
        or fallback
        or ADMIN_BUSINESS_CONNECTION_ID
    )


def contains_forbidden_contact(text: str) -> bool:
    return bool(CONTACT_RE.search(text or ""))


def admin_panel_text() -> str:
    return (
        "Админ-панель\n\n"
        "Панель динамическая: кнопки стараются менять старое сообщение, а не кидать новое.\n"
        "Цвет inline-кнопок Telegram менять не даёт, поэтому различие сделано эмодзи.\n\n"
        "Команды:\n"
        "/status\n/last_orders\n/suppliers\n/services\n/lists\n/texts\n\n"
        "/add_supplier TELEGRAM_ID Имя\n"
        "/bind_supplier TELEGRAM_ID товар_или_лист\n"
        "/remove_supplier TELEGRAM_ID\n"
        "/unbind_supplier TELEGRAM_ID товар_или_лист\n\n"
        "/add_service Название\n/remove_service Название\n"
        "/set_service_emoji Название | 🔥\n"
        "/add_list Название\n"
        "/list_add_service Лист | Сервис\n"
        "/set_text ключ | новый текст"
    )


async def update_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            await callback.message.answer(text, reply_markup=reply_markup)


async def delete_later(bot: Bot, chat_id: int, message_id: int, delay: int = 20) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.info("Message delete skipped chat_id=%s message_id=%s", chat_id, message_id)


async def maybe_delete_message(bot: Bot, message: Message, delay: int = 20) -> None:
    try:
        asyncio.create_task(delete_later(bot, message.chat.id, message.message_id, delay))
    except Exception:
        logger.exception("Failed to schedule delete")


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        await safe_send_message(bot, admin_id, text)
    if ADMIN_ALERT_CHAT_ID:
        await safe_send_message(bot, ADMIN_ALERT_CHAT_ID, text)


async def send_service_keyboard(
    bot: Bot,
    message: Message,
    order_id: int,
    business_connection_id: str | None,
    page: int = 0,
) -> None:
    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order or order.status != "waiting_service":
            closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
            await answer_message(bot, message, closed_text, business_connection_id)
            return
        services, max_page = await get_services_page(session, page, SERVICE_PAGE_SIZE)
        text = await get_text(session, "service_select", "Выберите сервис кнопкой ниже или напишите название из списка.")

    if not services:
        await answer_message(bot, message, "Сервисы не настроены. Админ должен добавить /add_service Название", business_connection_id)
        return

    await answer_message(
        bot,
        message,
        f"{text}\n\nСтраница {page + 1}/{max_page + 1}",
        business_connection_id,
        reply_markup=service_keyboard_from_services(services, page, max_page, order_id),
    )


async def process_admin_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user or not is_admin(message.from_user.id):
        return False

    text = (message.text or "").strip()
    parts = text.split()

    if text in {"/admin", "/panel", "/menu"}:
        await answer_message(bot, message, admin_panel_text(), business_connection_id, reply_markup=admin_panel_keyboard())
        return True

    if text == "/services":
        async with SessionLocal() as session:
            result = await services_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text == "/texts":
        async with SessionLocal() as session:
            result = await texts_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text == "/lists":
        async with SessionLocal() as session:
            result = await lists_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/add_list"):
        name = text.replace("/add_list", "", 1).strip()
        if not name:
            await answer_message(bot, message, "Формат:\n/add_list Название\n\nПример:\n/add_list numbers", business_connection_id)
            return True
        async with SessionLocal() as session:
            result = await add_service_list(session, name)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/list_add_service"):
        payload = text.replace("/list_add_service", "", 1).strip()
        if "|" not in payload:
            await answer_message(bot, message, "Формат:\n/list_add_service Лист | Сервис", business_connection_id)
            return True
        list_name, service_name = [x.strip() for x in payload.split("|", 1)]
        async with SessionLocal() as session:
            result = await add_service_to_list(session, list_name, service_name)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/add_service"):
        name = text.replace("/add_service", "", 1).strip()
        if not name:
            await answer_message(bot, message, "Формат:\n/add_service Название\n\nПример:\n/add_service Telegram", business_connection_id)
            return True

        async with SessionLocal() as session:
            result = await add_service(session, name)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/remove_service"):
        name = text.replace("/remove_service", "", 1).strip()
        if not name:
            await answer_message(bot, message, "Формат:\n/remove_service Название", business_connection_id)
            return True

        async with SessionLocal() as session:
            result = await remove_service(session, name)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/set_service_emoji"):
        payload = text.replace("/set_service_emoji", "", 1).strip()
        if "|" not in payload:
            await answer_message(
                bot,
                message,
                "Формат:\n/set_service_emoji Название | эмодзи\n\nПример:\n/set_service_emoji Telegram | 🔥",
                business_connection_id,
            )
            return True

        name, emoji = [x.strip() for x in payload.split("|", 1)]

        async with SessionLocal() as session:
            result = await set_service_emoji(session, name, emoji)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/set_text"):
        payload = text.replace("/set_text", "", 1).strip()
        if "|" not in payload:
            await answer_message(
                bot,
                message,
                "Формат:\n/set_text ключ | новый текст\n\n"
                "Ключи:\n"
                "thank_you\nservice_accepted\nservice_select\norder_not_found\ncontact_forbidden\n"
                "\nПример:\n/set_text thank_you | Спасибо за покупку!",
                business_connection_id,
            )
            return True

        key, value = [x.strip() for x in payload.split("|", 1)]

        async with SessionLocal() as session:
            result = await set_text(session, key, value)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text == "/suppliers":
        async with SessionLocal() as session:
            result = await list_suppliers_text(session)
        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/add_supplier"):
        if len(parts) < 3:
            await answer_message(bot, message, "Формат:\n/add_supplier TELEGRAM_ID Имя", business_connection_id)
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True

        name = " ".join(parts[2:]).strip()

        async with SessionLocal() as session:
            supplier = await add_supplier(session, supplier_id, name)

        await answer_message(bot, message, f"OK. Поставщик добавлен.\nID: {supplier.telegram_id}\nИмя: {supplier.name}", business_connection_id)
        return True

    if text.startswith("/remove_supplier"):
        if len(parts) != 2:
            await answer_message(bot, message, "Формат:\n/remove_supplier TELEGRAM_ID", business_connection_id)
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True

        async with SessionLocal() as session:
            ok = await remove_supplier(session, supplier_id)

        await answer_message(bot, message, "OK. Поставщик выключен." if ok else "Поставщик не найден.", business_connection_id)
        return True

    if text.startswith("/bind_supplier"):
        if len(parts) < 3:
            await answer_message(bot, message, "Формат:\n/bind_supplier TELEGRAM_ID товар_или_ключ", business_connection_id)
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True

        product_key = " ".join(parts[2:]).strip()
        async with SessionLocal() as session:
            result = await bind_supplier_to_product(session, supplier_id, product_key)

        await answer_message(bot, message, result, business_connection_id)
        return True

    if text.startswith("/unbind_supplier"):
        if len(parts) < 3:
            await answer_message(bot, message, "Формат:\n/unbind_supplier TELEGRAM_ID товар_или_ключ", business_connection_id)
            return True

        try:
            supplier_id = int(parts[1])
        except ValueError:
            await answer_message(bot, message, "TELEGRAM_ID должен быть числом.", business_connection_id)
            return True

        product_key = " ".join(parts[2:]).strip()
        async with SessionLocal() as session:
            result = await unbind_supplier_from_product(session, supplier_id, product_key)

        await answer_message(bot, message, result, business_connection_id)
        return True

    return False


async def is_supplier_user(user_id: int) -> bool:
    async with SessionLocal() as session:
        from app.models import Supplier
        from sqlalchemy import select
        result = await session.execute(select(Supplier).where(Supplier.telegram_id == user_id, Supplier.is_active == True))
        return result.scalars().first() is not None


async def process_supplier_command(bot: Bot, message: Message, business_connection_id: str | None) -> bool:
    if not message.from_user:
        return False
    if not await is_supplier_user(message.from_user.id):
        return False

    text = (message.text or "").strip()
    if text in {"/supplier", "/work", "/pending"}:
        async with SessionLocal() as session:
            pending_text, max_page = await supplier_pending_text(session, message.from_user.id, 0, SUPPLIER_PAGE_SIZE)
        await answer_message(bot, message, pending_text, business_connection_id, reply_markup=supplier_panel_keyboard(0, max_page))
        return True
    return False


async def process_command_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    text = (message.text or "").strip()
    user_id = message.from_user.id
    username = message.from_user.username

    if await process_admin_command(bot, message, business_connection_id):
        return

    if await process_supplier_command(bot, message, business_connection_id):
        return

    if text == "/start":
        async with SessionLocal() as session:
            order = await find_active_order_for_customer(session, user_id, username)

        if order and order.status == "waiting_service":
            await send_service_keyboard(bot, message, order.id, business_connection_id, page=0)
            return

        if await is_supplier_user(user_id):
            async with SessionLocal() as session:
                pending_text, max_page = await supplier_pending_text(session, user_id, 0, SUPPLIER_PAGE_SIZE)
            await answer_message(bot, message, pending_text, business_connection_id, reply_markup=supplier_panel_keyboard(0, max_page))
            return

        await answer_message(bot, message, "Бот работает.\n\nПроверка: /ping\nАдмин-панель: /admin", business_connection_id)
        return

    if text == "/ping":
        await answer_message(bot, message, "pong OK", business_connection_id)
        return

    if text == "/status":
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        async with SessionLocal() as session:
            status_text = await get_status_text(session)
        await answer_message(bot, message, status_text, business_connection_id)
        return

    if text == "/last_orders":
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        async with SessionLocal() as session:
            last_orders = await get_last_orders_text(session)
        await answer_message(bot, message, last_orders, business_connection_id)
        return

    if text.startswith("/set_customer"):
        if not is_admin(user_id):
            await answer_message(bot, message, "Команда только для админа.", business_connection_id)
            return
        parts = text.split()
        if len(parts) != 3:
            await answer_message(bot, message, "Формат: /set_customer ID_ЗАКАЗА TELEGRAM_ID", business_connection_id)
            return
        try:
            order_id = int(parts[1])
            telegram_id = int(parts[2])
        except ValueError:
            await answer_message(bot, message, "ID должны быть числами.", business_connection_id)
            return
        async with SessionLocal() as session:
            result_text = await set_customer_by_order_id(session, order_id, telegram_id)
        await answer_message(bot, message, result_text, business_connection_id)
        return

    await answer_message(bot, message, "Неизвестная команда. Напишите /ping или /admin", business_connection_id)


async def process_admaker_message(bot: Bot, message: Message) -> None:
    text = message.text or ""
    data = extract_purchase_data(text)

    if not data:
        await notify_admins(bot, f"Shop-бот прислал сообщение, но покупку распарсить не удалось.\n\nТекст:\n{text}")
        return

    async with SessionLocal() as session:
        order = await create_or_update_order_from_purchase(session, data)

    await notify_admins(
        bot,
        "OK. Покупка обработана.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Покупатель ID: {order.customer_telegram_id}\n"
        f"Username: @{order.customer_username or 'нет'}\n"
        f"Товар ID: {order.product_id or 'нет'}\n"
        f"Товар: {order.product_name}\n"
        f"Статус: {order.status}",
    )


async def send_supplier_request_for_order(bot: Bot, order, business_connection_id: str | None) -> bool:
    actual_business_id = business_connection_id or getattr(order, "business_connection_id", None)

    async with SessionLocal() as session:
        db_order = await get_order_by_id(session, order.id)
        if not db_order:
            return False
        supplier = await find_supplier_for_order(session, db_order)

    if not supplier:
        await notify_admins(
            bot,
            "Нет активного поставщика для заказа.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"Товар: {order.product_name}\n"
            "Добавь поставщика и привяжи товар:\n"
            "/add_supplier TELEGRAM_ID Имя\n"
            "/bind_supplier TELEGRAM_ID товар_или_ID",
        )
        return False

    supplier_text = (
        "Новый заказ.\n\n"
        f"Заказ: #{order.operation_id}\n"
        f"ID в базе: {order.id}\n"
        f"Товар ID: {order.product_id or 'нет'}\n"
        f"Товар: {order.product_name}\n"
        f"Сервис: {order.service_name}\n\n"
        "Пришлите номер для покупателя.\n"
        "Пример: +79990000000"
    )

    ok = await safe_send_message(bot, supplier.telegram_id, supplier_text, actual_business_id)
    if not ok:
        ok = await safe_send_message(bot, supplier.telegram_id, supplier_text)

    if not ok:
        await notify_admins(bot, f"Не смог отправить заявку поставщику {supplier.telegram_id} по заказу #{order.operation_id}")
        return False

    async with SessionLocal() as session:
        await create_supplier_request(session, order.id, supplier.telegram_id, "number")

    return True


async def accept_service_for_order(bot: Bot, message: Message | None, order_id: int, service_name: str, business_connection_id: str | None) -> None:
    async with SessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        if not order:
            if message:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
            return

        if order.status != "waiting_service":
            if message:
                await answer_message(bot, message, "Этот заказ уже в обработке или закрыт.", business_connection_id or order.business_connection_id)
            return

        if order.status != "waiting_service":
            if message:
                closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
                await answer_message(bot, message, closed_text, business_connection_id or order.business_connection_id)
            return

        order.service_name = service_name
        order.status = "waiting_supplier_number"

        if message and message.from_user:
            order.buyer_chat_id = message.chat.id
            order.customer_telegram_id = message.from_user.id

        if business_connection_id:
            order.business_connection_id = business_connection_id

        order.updated_at = datetime.utcnow()
        await increment_service_usage(session, service_name)
        await session.commit()
        await session.refresh(order)

    actual_business_id = business_connection_id or order.business_connection_id
    ok = await send_supplier_request_for_order(bot, order, actual_business_id)

    async with SessionLocal() as session:
        service_accepted_text = await get_text(session, "service_accepted", "OK. Сервис принят. Ожидайте номер.")

    if message:
        if ok:
            await answer_message(bot, message, service_accepted_text, actual_business_id)
        else:
            await answer_message(
                bot,
                message,
                "Сервис принят, но поставщик для этого товара не найден или недоступен. Админ уведомлён.",
                actual_business_id,
            )


async def handle_buyer_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    username = message.from_user.username
    text = (message.text or "").strip()

    async with SessionLocal() as session:
        contact_forbidden_text = await get_text(session, "contact_forbidden", "Нельзя отправлять контакты, username, ссылки или номера для связи.")
        order_not_found_text = await get_text(session, "order_not_found", "Заказ не найден.\n\nЕсли вы уже оплатили, напишите админу.")

    if not text:
        await answer_message(bot, message, "Пришлите только название сервиса текстом или выберите кнопку. Фото/файлы поставщику не отправляются.", business_connection_id)
        await maybe_delete_message(bot, message)
        return

    if contains_forbidden_contact(text):
        await answer_message(bot, message, contact_forbidden_text, business_connection_id)
        await maybe_delete_message(bot, message)
        return

    async with SessionLocal() as session:
        order = await find_waiting_service_order_for_customer(session, user_id, username)

        if not order:
            await answer_message(bot, message, order_not_found_text, business_connection_id)
            await notify_admins(
                bot,
                "Покупатель написал, но заказ не найден.\n\n"
                f"Telegram ID: {user_id}\n"
                f"Username: @{username or 'нет'}\n"
                f"Текст: {text}\n\n"
                f"Команда для привязки: /set_customer ID_ЗАКАЗА {user_id}",
            )
            return

        order.buyer_chat_id = message.chat.id
        order.customer_telegram_id = user_id
        if business_connection_id:
            order.business_connection_id = business_connection_id

        service = await find_service_by_text(session, text)
        await session.commit()
        await session.refresh(order)

    if not service:
        await send_service_keyboard(bot, message, order.id, business_connection_id or order.business_connection_id, page=0)
        await maybe_delete_message(bot, message)
        return

    await accept_service_for_order(bot, message, order.id, service.name, business_connection_id or order.business_connection_id)
    await maybe_delete_message(bot, message)


async def handle_supplier_message(bot: Bot, message: Message, business_connection_id: str | None) -> None:
    if not message.from_user:
        return

    supplier_id = message.from_user.id
    text = message.text or ""

    async with SessionLocal() as session:
        number_request = await find_waiting_supplier_request(session, supplier_id, "number")

        if number_request:
            phone = extract_phone(text)
            if not phone:
                await answer_message(bot, message, "Не смог найти номер. Пример: +79990000000", business_connection_id)
                return

            order = await get_order_by_id(session, number_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
                return

            order.phone_number = phone
            order.status = "number_sent_to_customer"
            order.updated_at = datetime.utcnow()
            number_request.status = "answered"
            number_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id or business_connection_id or ADMIN_BUSINESS_CONNECTION_ID

            ok = False
            if target_chat_id:
                ok = await safe_send_message(bot, target_chat_id, phone, business_connection_id=target_business_id, reply_markup=number_keyboard(order.id))

            if not ok:
                await answer_message(bot, message, "Номер принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(bot, f"Не смог отправить номер покупателю.\nЗаказ #{order.operation_id}\nbusiness_connection_id: {target_business_id}")
                return

            await answer_message(bot, message, "OK. Номер отправлен покупателю.", business_connection_id)
            return

        code_request = await find_waiting_supplier_request(session, supplier_id, "code")

        if code_request:
            code = extract_code(text)
            if not code:
                await answer_message(bot, message, "Не смог найти код. Пример: 123456", business_connection_id)
                return

            order = await get_order_by_id(session, code_request.order_id)
            if not order:
                await answer_message(bot, message, "Заказ не найден.", business_connection_id)
                return

            order.verification_code = code
            order.status = "code_sent_to_customer"
            order.updated_at = datetime.utcnow()
            code_request.status = "answered"
            code_request.answered_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

            target_chat_id = order.buyer_chat_id or order.customer_telegram_id
            target_business_id = order.business_connection_id or business_connection_id or ADMIN_BUSINESS_CONNECTION_ID

            ok = False
            if target_chat_id:
                ok = await safe_send_message(bot, target_chat_id, code, business_connection_id=target_business_id, reply_markup=confirm_keyboard(order.id))

            if not ok:
                await answer_message(bot, message, "Код принят, но не смог отправить покупателю.", business_connection_id)
                await notify_admins(bot, f"Не смог отправить код покупателю.\nЗаказ #{order.operation_id}\nbusiness_connection_id: {target_business_id}")
                return

            await answer_message(bot, message, "OK. Код отправлен покупателю.", business_connection_id)
            return

    await answer_message(bot, message, "Нет активного запроса для вас.", business_connection_id)


async def route_message(bot: Bot, message: Message, is_business: bool) -> None:
    if not message.from_user:
        return

    me = await bot.me()
    sender = message.from_user
    user_id = sender.id
    username = (sender.username or "").replace("@", "").lower()
    text = (message.text or "").strip()
    business_connection_id = get_business_id(message) if is_business else None

    logger.info(
        "HANDLED_TEXT is_business=%s from_id=%s username=%s is_bot=%s chat_id=%s business_id=%s text=%s",
        is_business, user_id, username, sender.is_bot, message.chat.id, business_connection_id, text[:200],
    )

    if user_id == me.id:
        logger.info("IGNORED: own bot message")
        return

    if is_admin(user_id) and not text.startswith("/"):
        logger.info("IGNORED: admin non-command message to avoid self-cycle")
        return

    if IGNORE_OTHER_BOTS and sender.is_bot and username != SHOP_BOT_USERNAME:
        logger.info("IGNORED: other bot username=%s", username)
        return

    if text.startswith("/"):
        await process_command_message(bot, message, business_connection_id)
        return

    if username == SHOP_BOT_USERNAME:
        await process_admaker_message(bot, message)
        return

    async with SessionLocal() as session:
        from app.models import Supplier
        from sqlalchemy import select
        result = await session.execute(select(Supplier).where(Supplier.telegram_id == user_id, Supplier.is_active == True))
        supplier = result.scalars().first()

    if supplier:
        await handle_supplier_message(bot, message, business_connection_id)
        return

    await handle_buyer_message(bot, message, business_connection_id)


async def resend_problem_to_supplier(bot: Bot, order, problem_type: str) -> None:
    async with SessionLocal() as session:
        supplier = await find_supplier_for_order(session, order)

    if not supplier:
        await notify_admins(bot, f"Проблема по заказу #{order.operation_id}, но поставщик не найден.")
        return

    if problem_type == "code":
        request_type = "code"
        supplier_text = (
            "Проблема: код не работает.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name}\n"
            f"Номер: {order.phone_number or 'нет'}\n"
            f"Старый код: {order.verification_code or 'нет'}\n\n"
            "Проверьте цифры и пришлите новый/правильный код.\n"
            "Панель поставщика: /supplier"
        )
    else:
        request_type = "number"
        supplier_text = (
            "Проблема: номер не работает.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name}\n"
            f"Старый номер: {order.phone_number or 'нет'}\n\n"
            "Пришлите новый номер.\n"
            "Панель поставщика: /supplier"
        )

    ok = await safe_send_message(bot, supplier.telegram_id, supplier_text, order.business_connection_id)
    if not ok:
        ok = await safe_send_message(bot, supplier.telegram_id, supplier_text)

    if ok:
        async with SessionLocal() as session:
            await create_supplier_request(session, order.id, supplier.telegram_id, request_type)


async def handle_admin_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user or not is_admin(callback.from_user.id):
        return False

    data = callback.data or ""

    if data == "admin:panel":
        await update_or_send(callback, admin_panel_text(), reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:status":
        async with SessionLocal() as session:
            text = await get_status_text(session)
        await update_or_send(callback, text, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:last_orders":
        async with SessionLocal() as session:
            text = await get_last_orders_text(session)
        await update_or_send(callback, text, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:suppliers":
        async with SessionLocal() as session:
            text = await list_suppliers_text(session)
        await update_or_send(callback, text, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:services":
        async with SessionLocal() as session:
            text = await services_text(session)
        await update_or_send(callback, text, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:texts":
        async with SessionLocal() as session:
            text = await texts_text(session)
        await update_or_send(callback, text, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    if data == "admin:lists":
        async with SessionLocal() as session:
            text = await lists_text(session)
        await update_or_send(callback, text, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    help_texts = {
        "admin:add_supplier_help": "Добавить поставщика:\n/add_supplier TELEGRAM_ID Имя\n\nПример:\n/add_supplier 123456789 proxy_supplier",
        "admin:bind_supplier_help": "Привязать товар:\n/bind_supplier TELEGRAM_ID товар_или_ID\n\nПример:\n/bind_supplier 123456789 proxy",
        "admin:add_service_help": "Добавить сервис:\n/add_service Название\n\nПример:\n/add_service Telegram",
        "admin:service_emoji_help": "Эмодзи сервиса:\n/set_service_emoji Название | эмодзи\n\nПример:\n/set_service_emoji Telegram | 🔥",
        "admin:set_text_help": "Изменить текст:\n/set_text ключ | новый текст\n\nКлючи:\nthank_you\nservice_accepted\nservice_select\norder_not_found\ncontact_forbidden\norder_closed\nproblem_sent",
        "admin:list_help": "Листы сервисов:\n/add_list Название\n/list_add_service Лист | Сервис\n\nПоставщика можно привязать к листу:\n/bind_supplier TELEGRAM_ID НазваниеЛиста",
        "admin:commands": admin_panel_text(),
    }

    if data in help_texts:
        await update_or_send(callback, help_texts[data], reply_markup=admin_panel_keyboard())
        await callback.answer()
        return True

    return False


async def handle_supplier_callback(bot: Bot, callback: CallbackQuery) -> bool:
    if not callback.from_user or not await is_supplier_user(callback.from_user.id):
        return False

    data = callback.data or ""
    if data.startswith("supplier:pending:"):
        page = int(data.split(":")[2])
        async with SessionLocal() as session:
            text, max_page = await supplier_pending_text(session, callback.from_user.id, page, SUPPLIER_PAGE_SIZE)
        await update_or_send(callback, text, reply_markup=supplier_panel_keyboard(page, max_page))
        await callback.answer()
        return True

    return False


async def handle_callback(bot: Bot, callback: CallbackQuery) -> None:
    data = callback.data or ""
    logger.info("HANDLED_CALLBACK from_id=%s data=%s", callback.from_user.id if callback.from_user else None, data)

    if data.startswith("admin:"):
        handled = await handle_admin_callback(bot, callback)
        if handled:
            return
        await callback.answer("Команда только для админа", show_alert=True)
        return

    if data.startswith("svcpage:"):
        _, order_id_raw, page_raw = data.split(":")
        order_id = int(order_id_raw)
        page = int(page_raw)

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id) if order_id else None
            if not order or order.status != "waiting_service":
                closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
                await callback.answer(closed_text, show_alert=True)
                return
            services, max_page = await get_services_page(session, page, SERVICE_PAGE_SIZE)
            text = await get_text(session, "service_select", "Выберите сервис кнопкой ниже или напишите название из списка.")

        await update_or_send(callback, f"{text}\n\nСтраница {page + 1}/{max_page + 1}", reply_markup=service_keyboard_from_services(services, page, max_page, order_id))
        await callback.answer()
        return

    if data.startswith("service:"):
        _, order_id_raw, service_slug = data.split(":", 2)
        order_id = int(order_id_raw)
        message = callback.message if isinstance(callback.message, Message) else None

        async with SessionLocal() as session:
            service = await find_service_by_slug(session, service_slug)
            order = await get_order_by_id(session, order_id) if order_id else None
            if not order or order.status != "waiting_service":
                closed_text = await get_text(session, "order_closed", "Заказ уже закрыт или уже в обработке.")
                await callback.answer(closed_text, show_alert=True)
                return
            business_id = order.business_connection_id

        if not service:
            await callback.answer("Сервис не найден", show_alert=True)
            return

        await accept_service_for_order(bot, message, order_id, service.name, business_id)
        await callback.answer("Сервис выбран")
        return

    if data.startswith("code_sent:"):
        order_id = int(data.split(":")[1])

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            if order.status == "waiting_supplier_code":
                await callback.answer("Код уже запрошен. Подождите ответ поставщика.", show_alert=True)
                return

            order.status = "waiting_supplier_code"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)

        async with SessionLocal() as session:
            db_order = await get_order_by_id(session, order_id)
            supplier = await find_supplier_for_order(session, db_order)

        if not supplier:
            if callback.message:
                await callback.message.answer("Поставщик для этого товара не найден.")
            await callback.answer()
            return

        supplier_text = (
            "Нужен код.\n\n"
            f"Заказ: #{order.operation_id}\n"
            f"ID в базе: {order.id}\n"
            f"Товар: {order.product_name}\n"
            f"Сервис: {order.service_name}\n"
            f"Номер: {order.phone_number}\n\n"
            "Пришлите код. Пример: 123456\n"
            "Панель поставщика: /supplier"
        )

        ok = await safe_send_message(bot, supplier.telegram_id, supplier_text, order.business_connection_id)
        if not ok:
            ok = await safe_send_message(bot, supplier.telegram_id, supplier_text)

        if ok:
            async with SessionLocal() as session:
                await create_supplier_request(session, order.id, supplier.telegram_id, "code")

        if callback.message:
            await callback.message.answer("OK. Запросил код у поставщика." if ok else "Не смог написать поставщику.")

        await callback.answer()
        return

    if data.startswith("confirm_success:"):
        order_id = int(data.split(":")[1])

        async with SessionLocal() as session:
            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            order.status = "confirmed"
            order.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)
            thank_you_text = await get_text(session, "thank_you", "Спасибо за покупку!")

        target_chat_id = order.buyer_chat_id or order.customer_telegram_id
        target_business_id = order.business_connection_id or ADMIN_BUSINESS_CONNECTION_ID

        thanks_sent = False
        if target_chat_id:
            thanks_sent = await safe_send_message(bot, target_chat_id, thank_you_text, business_connection_id=target_business_id)

        if not thanks_sent and callback.message:
            await callback.message.answer(thank_you_text)

        await callback.answer("Заказ завершён")
        return

    if data.startswith("number_invalid:") or data.startswith("code_invalid:"):
        order_id = int(data.split(":")[1])
        user_id = callback.from_user.id if callback.from_user else 0

        async with SessionLocal() as session:
            ok_cd, remaining = await check_cooldown(session, user_id, "problem", PROBLEM_COOLDOWN_SECONDS)

            if not ok_cd:
                minutes = max(1, remaining // 60)
                await callback.answer(f"Проблему можно отправлять раз в 10 минут. Осталось примерно {minutes} мин.", show_alert=True)
                return

            order = await get_order_by_id(session, order_id)
            if not order:
                await callback.answer("Заказ не найден", show_alert=True)
                return

            if order.status == "confirmed":
                await callback.answer("Заказ уже закрыт", show_alert=True)
                return

            order.status = "problem"
            order.updated_at = datetime.utcnow()
            await session.commit()

        if callback.message:
            await callback.message.answer("Понял. Передал админу проблему.")

        await notify_admins(bot, f"Покупатель сообщил о проблеме. Заказ ID в базе: {order_id}")
        await callback.answer()
        return

    await callback.answer("Неизвестная кнопка", show_alert=True)


async def on_message(message: Message, bot: Bot) -> None:
    logger.info("DISPATCHER_MESSAGE text=%s", message.text)
    await route_message(bot, message, is_business=False)


async def on_business_message(message: Message, bot: Bot) -> None:
    logger.info("DISPATCHER_BUSINESS_MESSAGE text=%s", message.text)
    await route_message(bot, message, is_business=True)


async def on_callback_query(callback: CallbackQuery, bot: Bot) -> None:
    logger.info("DISPATCHER_CALLBACK data=%s", callback.data)
    await handle_callback(bot, callback)


async def on_business_connection(event, bot: Bot) -> None:
    logger.info("DISPATCHER_BUSINESS_CONNECTION event=%s", event)


async def on_edited_business_message(message: Message, bot: Bot) -> None:
    logger.info("DISPATCHER_EDITED_BUSINESS_MESSAGE ignored text=%s", message.text)


async def on_deleted_business_messages(event, bot: Bot) -> None:
    logger.info("DISPATCHER_DELETED_BUSINESS_MESSAGES ignored event=%s", event)
