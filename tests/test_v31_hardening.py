import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test-v31.db")
os.environ.setdefault("CRYPTO_PAY_TOKEN", "123:TESTTOKEN")

from app.database import SessionLocal, init_db
from app.models import (
    DigitalPurchase,
    ProductProvider,
    ProductStockItem,
    ShopCategory,
    ShopProduct,
)
import app.cryptopay_service as cryptopay


class FakeCryptoClient:
    _global = 800000

    def __init__(self):
        self.calls = 0

    async def create_invoice(self, **kwargs):
        self.calls += 1
        type(self)._global += 1
        return SimpleNamespace(
            invoice_id=type(self)._global,
            bot_invoice_url=f"https://pay.test/{self.calls}",
            payload=kwargs["payload"],
            amount=kwargs["amount"],
            status="active",
            asset=kwargs.get("asset"),
            fiat=kwargs.get("fiat"),
            currency_type=kwargs.get("currency_type"),
        )


@pytest.mark.asyncio
async def test_stock_is_reserved_before_invoice_and_invoice_is_reused():
    await init_db()
    suffix = uuid4().hex[:10]
    async with SessionLocal() as session:
        category = ShopCategory(name=f"Category-{suffix}")
        session.add(category)
        await session.flush()
        product = ShopProduct(
            internal_key=int("9" + str(abs(hash(suffix)))[:10]),
            category_id=category.id,
            name=f"Stock-{suffix}",
            price=1,
            currency="USDT",
            product_type="quantity",
            is_active=True,
            payment_enabled=True,
        )
        session.add(product)
        await session.flush()
        session.add(
            ProductStockItem(
                product_id=product.id,
                content_type="text",
                content_text="UNIQUE-KEY",
                status="available",
            )
        )
        await session.commit()
        product_id = product.id

    fake = FakeCryptoClient()
    cryptopay._client = fake
    first_purchase, first_payment = await cryptopay.create_purchase_invoice(
        100001, "buyer", product_id
    )
    second_purchase, second_payment = await cryptopay.create_purchase_invoice(
        100001, "buyer", product_id
    )

    assert first_purchase.id == second_purchase.id
    assert first_payment.invoice_id == second_payment.invoice_id
    assert fake.calls == 1

    async with SessionLocal() as session:
        purchase = await session.get(DigitalPurchase, first_purchase.id)
        stock = await session.get(ProductStockItem, purchase.stock_item_id)
        assert purchase.fulfillment_type == "stock"
        assert stock.status == "reserved"


@pytest.mark.asyncio
async def test_provider_changes_fulfillment_route():
    await init_db()
    suffix = uuid4().hex[:10]
    fake = FakeCryptoClient()
    cryptopay._client = fake

    async with SessionLocal() as session:
        category = ShopCategory(name=f"Providers-{suffix}")
        session.add(category)
        await session.flush()
        proxy = ShopProduct(
            internal_key=int("8" + str(abs(hash(suffix)))[:10]),
            category_id=category.id,
            name="Proxy RU 30",
            price=3,
            currency="USDT",
            is_active=True,
            payment_enabled=True,
        )
        supplier = ShopProduct(
            internal_key=int("7" + str(abs(hash(suffix)))[:10]),
            category_id=category.id,
            name="SMS Number",
            price=2,
            currency="USDT",
            is_active=True,
            payment_enabled=True,
        )
        session.add_all([proxy, supplier])
        await session.flush()
        session.add_all(
            [
                ProductProvider(
                    internal_key=proxy.internal_key,
                    provider_type="proxyline",
                    provider_key='{"country":"ru","period":30}',
                    enabled=True,
                ),
                ProductProvider(
                    internal_key=supplier.internal_key,
                    provider_type="supplier",
                    provider_key="555000",
                    enabled=True,
                ),
            ]
        )
        await session.commit()
        proxy_id, supplier_id = proxy.id, supplier.id

    proxy_purchase, _ = await cryptopay.create_purchase_invoice(
        100002, "proxy_buyer", proxy_id
    )
    supplier_purchase, _ = await cryptopay.create_purchase_invoice(
        100003, "number_buyer", supplier_id
    )

    assert proxy_purchase.fulfillment_type == "proxyline"
    assert supplier_purchase.fulfillment_type == "supplier"


def test_external_shop_runtime_removed():
    sources = "\n".join(
        open(path, encoding="utf-8").read()
        for path in ("app/handlers.py", "app/shop.py", "app/config.py")
    )
    assert "SHOP_BOT_USERNAME" not in sources
    assert "PROXY_PACKAGE_PRODUCT_IDS" not in sources
    assert "Admaker" not in sources
