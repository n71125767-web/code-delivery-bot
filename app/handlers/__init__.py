from aiogram import Router

from app.handlers.admin import router as admin_router
from app.handlers.business import router as business_router
from app.handlers.common import router as common_router
from app.handlers.orders import router as orders_router
from app.handlers.supplier import router as supplier_router


def build_router() -> Router:
    root = Router()
    root.include_router(common_router)
    root.include_router(orders_router)
    root.include_router(supplier_router)
    root.include_router(admin_router)
    root.include_router(business_router)
    return root
