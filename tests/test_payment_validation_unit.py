from decimal import Decimal
from types import SimpleNamespace
import pytest


@pytest.mark.asyncio
async def test_paid_invoice_rejects_wrong_amount():
    from app.cryptopay_service import PaymentValidationError, _validate_paid_invoice
    payment = SimpleNamespace(
        invoice_id=10,
        payload='{"purchase_id":1}',
        amount=Decimal("10.00"),
        currency_type="crypto",
        asset="USDT",
        fiat=None,
    )
    invoice = {
        "invoice_id": 10,
        "status": "paid",
        "payload": payment.payload,
        "amount": "9.99",
        "asset": "USDT",
    }
    with pytest.raises(PaymentValidationError, match="Amount mismatch"):
        await _validate_paid_invoice(payment, invoice)


@pytest.mark.asyncio
async def test_paid_invoice_rejects_wrong_payload():
    from app.cryptopay_service import PaymentValidationError, _validate_paid_invoice
    payment = SimpleNamespace(
        invoice_id=10,
        payload='{"purchase_id":1}',
        amount=Decimal("10.00"),
        currency_type="crypto",
        asset="USDT",
        fiat=None,
    )
    invoice = {
        "invoice_id": 10,
        "status": "paid",
        "payload": "wrong",
        "amount": "10.00",
        "asset": "USDT",
    }
    with pytest.raises(PaymentValidationError, match="Payload mismatch"):
        await _validate_paid_invoice(payment, invoice)
