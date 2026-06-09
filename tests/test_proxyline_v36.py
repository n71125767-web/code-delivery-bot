from decimal import Decimal

from app.proxy_catalog_v36 import (
    PROXY_PERIODS,
    build_provider_key,
)

def test_proxy_periods():
    assert PROXY_PERIODS == {1: 30, 3: 90, 6: 180, 9: 270, 12: 360}

def test_provider_key_override():
    raw = build_provider_key(
        '{"count":1,"ip_version":4,"type":"dedicated"}',
        "de",
        6,
    )
    assert '"country":"de"' in raw
    assert '"period":180' in raw
    assert '"months":6' in raw

def test_monthly_price_math():
    monthly = Decimal("3.10")
    assert monthly * 12 == Decimal("37.20")
