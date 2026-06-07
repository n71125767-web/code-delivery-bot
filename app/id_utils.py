import secrets

def generate_internal_key() -> int:
    """Positive 62-bit identifier; collision probability is negligible."""
    return secrets.randbits(62) or 1
