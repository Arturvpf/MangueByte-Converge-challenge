"""Audit details allow-list: flat, short, non-personal metadata only.

Pseudonymize before calling: ids and counts are fine; names, contact data,
salaries, health/union data, raw prompts and free text are not.
"""
import math
import re

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
SENSITIVE_FRAGMENTS = ("email", "password", "senha", "token", "secret", "cpf", "name", "nome", "phone",
                       "telefone", "salary", "salario", "prompt", "message", "content", "address", "endereco",
                       "health", "saude", "union", "sindic", "birth", "nascimento")
# Short fragments only match at the start of a key token, so "target" or "incident" survive.
SENSITIVE_TOKENS = ("rg", "cid")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")
CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
REDACTED = "[redacted]"
INVALID_KEY = "[invalid_key]"
MAX_KEYS, MAX_LIST, MAX_STR, SCAN_STR = 32, 20, 256, 1024


def _sensitive(key: str) -> bool:
    return any(f in key for f in SENSITIVE_FRAGMENTS) or \
        any(t.startswith(SENSITIVE_TOKENS) for t in re.split(r"[_.]", key))


_DROP = object()


def _scalar(value):
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP
    if isinstance(value, str):
        head = value[:SCAN_STR]  # bounded scan; stored text is shorter anyway
        return REDACTED if EMAIL.search(head) or CPF.search(head) else str(value[:MAX_STR])
    return _DROP


def sanitize_details(details: dict | None) -> dict:
    """Return a safe copy; never raises for content, only for a non-dict input."""
    if details is None:
        return {}
    if not isinstance(details, dict):
        raise TypeError("audit details must be a dict")
    clean, redacted = {}, []
    for key, value in details.items():
        if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
            redacted.append(INVALID_KEY)  # never echo a malformed key: it may itself be personal data
            continue
        if _sensitive(key):
            redacted.append(key)
            continue
        if isinstance(value, (list, tuple)):
            items = [_scalar(v) for v in value[:MAX_LIST]]
            value = _DROP if any(v is _DROP for v in items) else items
        else:
            value = _scalar(value)
        if value is _DROP or len(clean) >= MAX_KEYS:
            redacted.append(key)
            continue
        clean[key] = value
    if redacted:
        clean["_redacted"] = list(dict.fromkeys(redacted))[:MAX_LIST]
    return clean
