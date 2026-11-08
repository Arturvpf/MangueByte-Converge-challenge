"""HS256 access tokens (strict JWT subset) with the stdlib. The key never leaves the server."""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import time
from uuid import uuid4

ISSUER = "alinia"
MIN_SECRET_LENGTH = 32
MAX_TOKEN_LENGTH = 4096
LEEWAY_SECONDS = 30
_HEADER = {"alg": "HS256", "typ": "JWT"}
SEGMENT = re.compile(r"[A-Za-z0-9_-]+")


class InvalidToken(Exception):
    """Deliberately carries no reason: callers answer a generic 401."""


def configured(settings) -> bool:
    secret = settings.auth_secret
    return isinstance(secret, str) and len(secret) >= MIN_SECRET_LENGTH


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(segment: str) -> bytes:
    try:
        data = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except ValueError:
        raise InvalidToken() from None
    if _encode(data) != segment:  # canonical encoding only; no ignored characters or bits
        raise InvalidToken()
    return data


def _json(value) -> str:
    return _encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _sign(settings, signing_input: str) -> bytes:
    return hmac.new(settings.auth_secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()


def issue_token(settings, *, user_id: str, tenant_id: str, token_version: int, now: float | None = None):
    if not configured(settings):
        raise RuntimeError("auth secret is not configured")
    if settings.access_token_ttl_seconds < 1:
        raise RuntimeError("access token ttl must be positive")
    issued = int(time.time() if now is None else now)
    expires = issued + settings.access_token_ttl_seconds
    claims = {"iss": ISSUER, "sub": user_id, "tid": tenant_id, "ver": token_version,
              "iat": issued, "exp": expires, "jti": uuid4().hex}
    signing_input = f"{_json(_HEADER)}.{_json(claims)}"
    return f"{signing_input}.{_encode(_sign(settings, signing_input))}", datetime.fromtimestamp(expires, timezone.utc)


def _int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def verify_token(settings, token: str, *, now: float | None = None) -> dict:
    if not configured(settings) or not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_LENGTH:
        raise InvalidToken()
    parts = token.split(".")
    if len(parts) != 3 or not all(SEGMENT.fullmatch(part) for part in parts):
        raise InvalidToken()
    header_b64, payload_b64, signature_b64 = parts
    # Authenticate first: nothing attacker-controlled is parsed before the HMAC matches.
    if not hmac.compare_digest(_sign(settings, f"{header_b64}.{payload_b64}"), _decode(signature_b64)):
        raise InvalidToken()
    try:
        header, claims = json.loads(_decode(header_b64)), json.loads(_decode(payload_b64))
    except (ValueError, RecursionError):
        raise InvalidToken() from None
    if header != _HEADER:  # rejects alg none/other algorithms and unknown header fields
        raise InvalidToken()
    if (not isinstance(claims, dict) or claims.get("iss") != ISSUER
            or not all(isinstance(claims.get(k), str) and claims[k] for k in ("sub", "tid", "jti"))
            or not all(_int(claims.get(k)) for k in ("ver", "iat", "exp"))):
        raise InvalidToken()
    current = time.time() if now is None else now
    if claims["exp"] <= current or claims["iat"] > current + LEEWAY_SECONDS:
        raise InvalidToken()
    return claims
