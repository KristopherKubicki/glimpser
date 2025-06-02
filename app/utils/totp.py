import pyotp


def generate_totp_secret() -> str:
    """Return a new random base32 secret for TOTP."""
    return pyotp.random_base32()


def verify_totp_code(secret: str, code: str) -> bool:
    """Verify a user-provided TOTP code against the secret."""
    if not secret or not code:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    except Exception:
        return False
