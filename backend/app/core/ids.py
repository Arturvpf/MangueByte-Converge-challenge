"""Opaque identifier format for ids stored in scope and audit columns.

Same character set as P1 snapshot ids. Rejects spaces, '@' and other free text,
so values such as e-mails never land in columns the audit sanitizer does not see.
"""
import re

ID_PATTERN = r"^[A-Za-z0-9._~-]{1,128}$"
_ID = re.compile(ID_PATTERN)
# Reject CPF-shaped sequences even when embedded in an otherwise opaque id.
_UUID4 = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")


def valid_id(value) -> bool:
    return isinstance(value, str) and value not in {".", ".."} and _ID.fullmatch(value) is not None and (_UUID4.fullmatch(value) is not None or _CPF.search(value) is None)
