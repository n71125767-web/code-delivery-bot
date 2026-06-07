from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


def category_asset(name: str):
    value = (name or "").lower()
    mapping = (
        (("номер", "sim", "телефон"), "numbers.jpg"),
        (("инструмент", "работ"), "tools.jpg"),
        (("подтверж",), "confirmations.jpg"),
        (("маркет",), "market.jpg"),
        (("разное", "прочее"), "misc.jpg"),
        (("прокси", "vpn", "безопас"), "tools.jpg"),
    )
    for words, filename in mapping:
        if any(word in value for word in words):
            path = ASSET_DIR / filename
            if path.exists():
                return FSInputFile(path)
    return None


def category_caption(category) -> str:
    description = (getattr(category, "description", None) or "").strip()
    title = f"{category.emoji} {category.name}"
    if description:
        return f"{title}\n\n{description}\n\nВыберите тариф или категорию из списка ниже 👇"
    return f"{title}\n\nВыберите тариф или категорию из списка ниже 👇"


def product_caption(product, provider_type: str | None = None) -> str:
    lines = [f"{product.name}", f"Цена: {product.price} {product.currency}"]
    if product.description:
        lines.extend(["", product.description])
    if product.payment_description:
        lines.extend(["", product.payment_description])
    if provider_type == "proxyline":
        lines.extend(["", "⚡ Автоматическая выдача после оплаты"])
    elif provider_type == "supplier":
        lines.extend(["", "⏳ Выдача через поставщика после оплаты"])
    return "\n".join(lines).strip()
