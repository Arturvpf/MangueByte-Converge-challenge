"""Policy Store request and response bodies.

Request bodies forbid extra fields and have no tenant_id: the company always
comes from the authenticated principal. Nullable fields are present and null;
nothing fills in a legal limit when a field is omitted.
"""
import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, field_validator, model_validator
from typing_extensions import Self

from backend.app.contracts.v1 import Contract, Scope, aware, nonempty
from backend.app.policies.catalog import (
    CATALOG,
    RuleParameters,
    UnknownRuleKey,
    category_for,
    parameter_model,
)

RULE_KEY_MAX = 64
TITLE_MAX = 200
SOURCE_REFERENCE_MAX = 500
REVIEW_NOTE_MAX = 1000
REVOCATION_REASON_MAX = 1000
LEGAL_REVIEW_MAX = 500
TEAM_ID_MAX = 128
EMPLOYEE_CATEGORY_MAX = 64
ID_MAX = 36
CATEGORY_MAX = 32

SourceKind = Literal["lei", "emenda", "cct", "act", "politica_interna", "sintetico"]
PolicyStatus = Literal["draft", "in_review", "approved", "revoked"]
ReviewReason = Literal["missing", "conflict", "pinned_revoked", "pinned_not_found"]
ResolutionStatus = Literal["resolved", "review_required"]


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return nonempty(value)


def calendar_date(value: object) -> date:
    """YYYY-MM-DD only. A timestamp must not be truncated into a validity date."""
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("expected a calendar date") from None
    raise ValueError("expected a calendar date")


CalendarDate = Annotated[date, BeforeValidator(calendar_date, json_schema_input_type=date)]


def optional_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return aware(value)


class DraftContent(Contract):
    """Full draft body. Every limit is required; valid_until null means open-ended."""

    parameters: RuleParameters
    source_kind: SourceKind
    source_reference: str = Field(min_length=1, max_length=SOURCE_REFERENCE_MAX)
    valid_from: CalendarDate
    valid_until: CalendarDate | None

    _source = field_validator("source_reference")(nonempty)

    @model_validator(mode="after")
    def open_interval(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        return self


class PolicyCreate(DraftContent):
    rule_key: str = Field(min_length=1, max_length=RULE_KEY_MAX)
    team_id: str | None = Field(min_length=1, max_length=TEAM_ID_MAX)
    employee_category: str | None = Field(min_length=1, max_length=EMPLOYEE_CATEGORY_MAX)
    title: str = Field(min_length=1, max_length=TITLE_MAX)

    _text = field_validator("rule_key", "title")(nonempty)
    _optional = field_validator("team_id", "employee_category")(optional_text)

    @model_validator(mode="after")
    def parameters_match_key(self) -> Self:
        try:
            expected = parameter_model(self.rule_key)
        except UnknownRuleKey as exc:
            raise ValueError(f"unknown rule_key: {exc.rule_key}") from exc
        if type(self.parameters) is not expected:
            raise ValueError("parameters do not match rule_key")
        return self


class VersionCreate(Contract):
    """New draft. Send full content, or null content fields with copy_from_version_id.

    A pure copy does not accept a partial override: valid_until null together with
    other nulls means 'copy the source', not 'open-ended'.
    """

    copy_from_version_id: str | None = Field(min_length=1, max_length=ID_MAX)
    parameters: RuleParameters | None
    source_kind: SourceKind | None
    source_reference: str | None = Field(min_length=1, max_length=SOURCE_REFERENCE_MAX)
    valid_from: CalendarDate | None
    valid_until: CalendarDate | None

    _optional = field_validator("copy_from_version_id", "source_reference")(optional_text)

    @model_validator(mode="after")
    def copy_or_full_content(self) -> Self:
        content = (self.parameters, self.source_kind, self.source_reference, self.valid_from)
        if all(part is None for part in content):
            if self.copy_from_version_id is None:
                raise ValueError("new version requires content or copy_from_version_id")
            if self.valid_until is not None:
                raise ValueError("pure copy cannot override valid_until")
            return self
        if any(part is None for part in content):
            raise ValueError("content must be complete; partial parameters are not accepted")
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        return self


class VersionUpdate(DraftContent):
    expected_revision: int = Field(ge=0)


class RevisionCommand(Contract):
    expected_revision: int = Field(ge=0)


class RejectIn(RevisionCommand):
    review_note: str = Field(min_length=1, max_length=REVIEW_NOTE_MAX)

    _note = field_validator("review_note")(nonempty)


class ApproveIn(RevisionCommand):
    legal_review_reference: str = Field(min_length=1, max_length=LEGAL_REVIEW_MAX)

    _reference = field_validator("legal_review_reference")(nonempty)


class RevokeIn(RevisionCommand):
    revocation_reason: str = Field(min_length=1, max_length=REVOCATION_REASON_MAX)

    _reason = field_validator("revocation_reason")(nonempty)


class PolicyOut(Contract):
    policy_id: str = Field(min_length=1, max_length=ID_MAX)
    tenant_id: str = Field(min_length=1, max_length=TEAM_ID_MAX)
    rule_key: str = Field(min_length=1, max_length=RULE_KEY_MAX)
    category: str = Field(min_length=1, max_length=CATEGORY_MAX)
    team_id: str | None = Field(min_length=1, max_length=TEAM_ID_MAX)
    employee_category: str | None = Field(min_length=1, max_length=EMPLOYEE_CATEGORY_MAX)
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    created_by: str = Field(min_length=1, max_length=ID_MAX)
    created_at: datetime

    _text = field_validator("policy_id", "tenant_id", "rule_key", "category", "title", "created_by")(nonempty)
    _optional = field_validator("team_id", "employee_category")(optional_text)
    _time = field_validator("created_at")(aware)

    @model_validator(mode="after")
    def category_matches(self) -> Self:
        try:
            expected = category_for(self.rule_key)
        except UnknownRuleKey as exc:
            raise ValueError(f"unknown rule_key: {exc.rule_key}") from exc
        if self.category != expected:
            raise ValueError("category does not match rule_key")
        return self


class PolicyVersionOut(Contract):
    version_id: str = Field(min_length=1, max_length=ID_MAX)
    policy_id: str = Field(min_length=1, max_length=ID_MAX)
    version: int = Field(gt=0)
    status: PolicyStatus
    parameters: RuleParameters
    source_kind: SourceKind
    source_reference: str = Field(min_length=1, max_length=SOURCE_REFERENCE_MAX)
    valid_from: CalendarDate
    valid_until: CalendarDate | None
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=0)
    author_user_id: str = Field(min_length=1, max_length=ID_MAX)
    created_at: datetime
    submitted_by: str | None = Field(min_length=1, max_length=ID_MAX)
    submitted_at: datetime | None
    approved_by: str | None = Field(min_length=1, max_length=ID_MAX)
    approved_at: datetime | None
    legal_review_reference: str | None = Field(min_length=1, max_length=LEGAL_REVIEW_MAX)
    review_note: str | None = Field(min_length=1, max_length=REVIEW_NOTE_MAX)
    revoked_by: str | None = Field(min_length=1, max_length=ID_MAX)
    revoked_at: datetime | None
    revocation_reason: str | None = Field(min_length=1, max_length=REVOCATION_REASON_MAX)

    _text = field_validator("version_id", "policy_id", "source_reference", "content_hash", "author_user_id")(nonempty)
    _optional = field_validator(
        "submitted_by", "approved_by", "legal_review_reference", "review_note", "revoked_by", "revocation_reason",
    )(optional_text)
    _times = field_validator("created_at", "submitted_at", "approved_at", "revoked_at")(optional_aware)

    @model_validator(mode="after")
    def open_interval(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        return self


class PolicyDetail(PolicyOut):
    versions: list[PolicyVersionOut]

    @model_validator(mode="after")
    def unique_versions(self) -> Self:
        numbers = [item.version for item in self.versions]
        if len(numbers) != len(set(numbers)):
            raise ValueError("duplicate version number")
        ids = [item.version_id for item in self.versions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate version id")
        return self


class PolicyList(Contract):
    items: list[PolicyOut]


class ResolvedRule(Contract):
    """One catalog key. review_required never carries parameters or validity.

    missing and conflict select no version. pinned_revoked names the revoked
    version. pinned_not_found echoes only the requested version id, so a rule
    from another company is not revealed.
    """

    rule_key: str | None = Field(min_length=1, max_length=RULE_KEY_MAX)
    status: ResolutionStatus
    version_id: str | None = Field(min_length=1, max_length=ID_MAX)
    version: int | None = Field(gt=0)
    parameters: RuleParameters | None
    source_reference: str | None = Field(min_length=1, max_length=SOURCE_REFERENCE_MAX)
    valid_from: CalendarDate | None
    valid_until: CalendarDate | None
    reason: ReviewReason | None

    _optional = field_validator("rule_key", "version_id", "source_reference")(optional_text)

    @model_validator(mode="after")
    def complete_or_reason(self) -> Self:
        if self.status == "resolved":
            return self._resolved()
        return self._unresolved()

    def _known_key(self) -> str:
        if self.rule_key is None or self.rule_key not in CATALOG:
            raise ValueError("review_required requires a known rule_key")
        return self.rule_key

    def _without_content(self) -> None:
        content = (self.parameters, self.source_reference, self.valid_from, self.valid_until)
        if any(part is not None for part in content):
            raise ValueError("review_required does not carry rule content")

    def _resolved(self) -> Self:
        if self.reason is not None or self.rule_key is None:
            raise ValueError("resolved rule requires rule_key and no review reason")
        if self.version_id is None or self.version is None or self.parameters is None or self.source_reference is None or self.valid_from is None:
            raise ValueError("resolved rule requires version, parameters, source and valid_from")
        try:
            expected = parameter_model(self.rule_key)
        except UnknownRuleKey as exc:
            raise ValueError(f"unknown rule_key: {exc.rule_key}") from exc
        if type(self.parameters) is not expected:
            raise ValueError("parameters do not match rule_key")
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        return self

    def _unresolved(self) -> Self:
        if self.reason is None:
            raise ValueError("review_required needs a reason")
        self._without_content()
        if self.reason in ("missing", "conflict"):
            self._known_key()
            if self.version_id is not None or self.version is not None:
                raise ValueError("missing or conflict does not select a version")
            return self
        if self.reason == "pinned_revoked":
            self._known_key()
            if self.version_id is None or self.version is None:
                raise ValueError("pinned_revoked identifies the revoked version")
            return self
        if self.rule_key is not None or self.version is not None or self.version_id is None:
            raise ValueError("pinned_not_found echoes only the requested version id")
        return self


class PolicyResolution(Scope):
    data_snapshot_id: str = Field(min_length=1, max_length=TEAM_ID_MAX)
    on_date: CalendarDate
    items: list[ResolvedRule] = Field(min_length=1)
    complete: bool

    _snapshot = field_validator("data_snapshot_id")(nonempty)

    @model_validator(mode="after")
    def completeness(self) -> Self:
        keys = [item.rule_key for item in self.items if item.rule_key is not None]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate rule_key")
        version_ids = [item.version_id for item in self.items if item.version_id is not None]
        if len(version_ids) != len(set(version_ids)):
            raise ValueError("duplicate version_id")
        if self.complete != all(item.status == "resolved" for item in self.items):
            raise ValueError("complete must reflect whether every rule resolved")
        return self


class ResolveQuery(Contract):
    on_date: CalendarDate
    team_id: str = Field(min_length=1, max_length=TEAM_ID_MAX)
    employee_category: str | None = Field(min_length=1, max_length=EMPLOYEE_CATEGORY_MAX)
    rule_keys: list[str] = Field(min_length=1)

    _team = field_validator("team_id")(nonempty)
    _category = field_validator("employee_category")(optional_text)

    @field_validator("rule_keys")
    @classmethod
    def known_unique_keys(cls, values: list[str]) -> list[str]:
        for value in values:
            nonempty(value)
            if value not in CATALOG:
                raise ValueError(f"unknown rule_key: {value}")
        if len(values) != len(set(values)):
            raise ValueError("rule_keys must be unique")
        return values


class PolicyListQuery(Contract):
    """Absent filters are null. They are not legal defaults."""

    rule_key: str | None = Field(min_length=1, max_length=RULE_KEY_MAX)
    category: str | None = Field(min_length=1, max_length=CATEGORY_MAX)
    team_id: str | None = Field(min_length=1, max_length=TEAM_ID_MAX)
    status: PolicyStatus | None

    _optional = field_validator("rule_key", "category", "team_id")(optional_text)

    @model_validator(mode="after")
    def known_filters(self) -> Self:
        if self.rule_key is not None and self.rule_key not in CATALOG:
            raise ValueError(f"unknown rule_key: {self.rule_key}")
        categories = {entry[0] for entry in CATALOG.values()}
        if self.category is not None and self.category not in categories:
            raise ValueError("unknown category")
        return self
