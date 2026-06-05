from enum import StrEnum


class OrderStatus(StrEnum):
    WAITING_SERVICE = "waiting_service"
    WAITING_PROXY_COUNTRY = "waiting_proxy_country"
    WAITING_PROXY_PERIOD = "waiting_proxy_period"
    WAITING_PROXY_CONFIRM = "waiting_proxy_confirm"
    PROXY_PROCESSING = "proxy_processing"
    WAITING_SUPPLIER_NUMBER = "waiting_supplier_number"
    NUMBER_SENT_TO_CUSTOMER = "number_sent_to_customer"
    WAITING_SUPPLIER_CODE = "waiting_supplier_code"
    CODE_SENT_TO_CUSTOMER = "code_sent_to_customer"
    CONFIRMED = "confirmed"
    PROBLEM = "problem"
    CANCELLED = "cancelled"

TERMINAL_ORDER_STATUSES = {OrderStatus.CONFIRMED.value, OrderStatus.CANCELLED.value}
