"""scrypt password hashes (stdlib). Encoded as scrypt$n$r$p$salt_b64$hash_b64."""
import base64
from functools import cache
import hashlib
import hmac
import secrets

N, R, P = 2 ** 14, 8, 1
MIN_LENGTH, MAX_LENGTH = 12, 1024
_MAXMEM = 64 * 1024 * 1024


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, size: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=size)


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password.strip() or not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        raise ValueError(f"password must have {MIN_LENGTH} to {MAX_LENGTH} characters")
    salt = secrets.token_bytes(16)
    return "$".join(("scrypt", str(N), str(R), str(P), _b64(salt), _b64(_scrypt(password, salt, N, R, P, 32))))


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check; malformed input or hashes simply fail."""
    if not isinstance(password, str) or not password or len(password) > MAX_LENGTH or not isinstance(encoded, str):
        return False
    try:
        scheme, n, r, p, salt, expected = encoded.split("$")
        n, r, p = int(n), int(r), int(p)
        if scheme != "scrypt" or not (2 <= n <= 2 ** 20 and n & (n - 1) == 0 and 1 <= r <= 32 and 1 <= p <= 16):
            return False
        salt, expected = base64.b64decode(salt, validate=True), base64.b64decode(expected, validate=True)
        if not salt or not 16 <= len(expected) <= 64:
            return False
        return hmac.compare_digest(_scrypt(password, salt, n, r, p, len(expected)), expected)
    except ValueError:  # includes binascii.Error, UnicodeEncodeError and scrypt memory limits
        return False


@cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(24))


def dummy_verify(password: str) -> bool:
    """Spend the same work as a real check when the account is unknown. Always False."""
    verify_password(password if isinstance(password, str) and password else "x", _dummy_hash())
    return False
