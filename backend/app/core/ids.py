"""Opaque identifier format for ids stored in scope and audit columns.

Same character set as P1 snapshot ids. Rejects spaces, '@' and other free text,
so values such as e-mails never land in columns the audit sanitizer does not see.
"""
import re

ID_PATTERN = r"^[A-Za-z0-9._~-]{1,128}$"
_ID = re.compile(ID_PATTERN)
# Reject CPF-shaped sequences even when embedded in an otherwise opaque id.
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")


def valid_id(value) -> bool:
    return isinstance(value, str) and value not in {".", ".."} and _ID.fullmatch(value) is not None and _CPF.search(value) is None
