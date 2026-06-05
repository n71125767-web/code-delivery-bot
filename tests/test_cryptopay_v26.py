import hashlib
import hmac
import json
import os

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test-v26.db")
os.environ.setdefault("CRYPTO_PAY_TOKEN", "123:TESTTOKEN")

from app.cryptopay_service import verify_webhook_signature


def test_webhook_signature():
    body = json.dumps({"update_type": "invoice_paid"}, separators=(",", ":")).encode()
    secret = hashlib.sha256(os.environ["CRYPTO_PAY_TOKEN"].encode()).digest()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, signature)
    assert not verify_webhook_signature(body, "bad")


def test_requirements_has_aiocryptopay():
    content = open("requirements.txt", encoding="utf-8").read()
    assert "aiocryptopay==" in content
