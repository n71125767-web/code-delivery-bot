import hashlib
import hmac


def test_webhook_signature_rejects_missing(monkeypatch):
    import app.cryptopay_service as service
    monkeypatch.setattr(service, "CRYPTO_PAY_TOKEN", "secret")
    assert service.verify_webhook_signature(b"{}", None) is False


def test_webhook_signature_accepts_valid(monkeypatch):
    import app.cryptopay_service as service
    token = "secret"
    body = b'{"update_type":"invoice_paid"}'
    secret = hashlib.sha256(token.encode()).digest()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    monkeypatch.setattr(service, "CRYPTO_PAY_TOKEN", token)
    assert service.verify_webhook_signature(body, signature) is True


def test_centralized_access(monkeypatch):
    import app.access as access
    monkeypatch.setattr(access, "SUPERADMIN_ID", 1)
    monkeypatch.setattr(access, "ADMIN_IDS", [1, 2])
    monkeypatch.setattr(access, "SUPPLIER_IDS", [3])
    assert access.is_superadmin(1)
    assert access.is_admin(2)
    assert access.is_supplier(3)
    assert access.bypass_buyer_cooldown(1)
    assert access.bypass_buyer_cooldown(3)
    assert not access.bypass_buyer_cooldown(4)
