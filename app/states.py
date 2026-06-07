from aiogram.fsm.state import State, StatesGroup


class NewOrderStates(StatesGroup):
    product_name = State()
    service_name = State()
    note = State()


class SupplierDeliveryStates(StatesGroup):
    payload = State()
