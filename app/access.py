"""Centralized role checks.

Use these helpers in new handlers instead of scattering ADMIN_IDS/SUPPLIER_IDS
comparisons throughout the project.
"""
from app.config import ADMIN_IDS, SUPERADMIN_ID, SUPPLIER_IDS


def is_superadmin(user_id: int | None) -> bool:
    return bool(user_id and SUPERADMIN_ID and user_id == SUPERADMIN_ID)


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def is_supplier(user_id: int | None) -> bool:
    return bool(user_id and user_id in SUPPLIER_IDS)


def bypass_buyer_cooldown(user_id: int | None) -> bool:
    return is_admin(user_id) or is_supplier(user_id)
