"""Catalog shape only: unknown keys, ranges, extra fields, and no default limits."""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from backend.app.policies.catalog import CATALOG, UnknownRuleKey, validate_parameters
from backend.app.policies.schemas import (
    ApproveIn,
    PolicyCreate,
    PolicyListQuery,
    PolicyResolution,
    RejectIn,
    ResolveQuery,
    RevokeIn,
    VersionCreate,
    VersionUpdate,
)

SOURCE = "SINTÉTICO — não é regra jurídica validada"


def _create(**overrides):
    body = {
        "rule_key": "workweek.max_hours",
        "team_id": "team-1",
        "employee_category": None,
        "title": "Jornada semanal sintética",
        "parameters": {"max_hours": "1"},
        "source_kind": "sintetico",
        "source_reference": SOURCE,
        "valid_from": "2026-01-01",
        "valid_until": None,
    }
    body.update(overrides)
    return body


def _resolved(rule_key="workweek.max_hours", parameters=None):
    return {
        "rule_key": rule_key,
        "status": "resolved",
        "version_id": "version-1",
        "version": 1,
        "parameters": {"max_hours": "1"} if parameters is None else parameters,
        "source_reference": SOURCE,
        "valid_from": "2026-01-01",
        "valid_until": None,
        "reason": None,
    }


def _review(rule_key="workweek.max_hours", reason="missing"):
    return {
        "rule_key": rule_key,
        "status": "review_required",
        "version_id": None,
        "version": None,
        "parameters": None,
        "source_reference": None,
        "valid_from": None,
        "valid_until": None,
        "reason": reason,
    }


def _resolution(items, complete):
    return {
        "schema_version": "1.0",
        "tenant_id": "tenant-demo-a",
        "team_id": "team-1",
        "data_snapshot_id": "snap-1",
        "on_date": "2026-11-08",
        "items": items,
        "complete": complete,
    }


def test_catalog_lists_the_five_mvp_rules():
    assert set(CATALOG) == {
        "workweek.max_hours",
        "workday.max_hours",
        "rest.weekly_min_days",
        "contract.modality",
        "internship.counts_as_capacity",
    }
    assert CATALOG["workweek.max_hours"][0] == "jornada"
    assert CATALOG["workday.max_hours"][0] == "jornada"
    assert CATALOG["rest.weekly_min_days"][0] == "repouso"
    assert CATALOG["contract.modality"][0] == "modalidade_contratual"
    assert CATALOG["internship.counts_as_capacity"][0] == "estagio_aprendizagem"


def test_unknown_rule_key():
    with pytest.raises(UnknownRuleKey):
        validate_parameters("workweek.overtime", {"max_hours": "1"})
    with pytest.raises(ValidationError):
        PolicyCreate.model_validate(_create(rule_key="workweek.overtime"))
    with pytest.raises(ValidationError):
        ResolveQuery.model_validate({
            "on_date": "2026-11-08",
            "team_id": "team-1",
            "employee_category": None,
            "rule_keys": ["workweek.max_hours", "not.a.rule"],
        })


def test_parameters_out_of_range():
    rejected = [
        ("workweek.max_hours", {"max_hours": "0"}),
        ("workweek.max_hours", {"max_hours": "-1"}),
        ("workweek.max_hours", {"max_hours": 0}),
        ("workweek.max_hours", {"max_hours": 1.5}),
        ("workweek.max_hours", {"max_hours": True}),
        ("workweek.max_hours", {"max_hours": "NaN"}),
        ("workweek.max_hours", {"max_hours": " 1"}),
        ("workday.max_hours", {"max_hours": "0", "requires_collective_agreement": False}),
        ("workday.max_hours", {"max_hours": "1", "requires_collective_agreement": 0}),
        ("rest.weekly_min_days", {"min_days": 0}),
        ("rest.weekly_min_days", {"min_days": 8}),
        ("rest.weekly_min_days", {"min_days": True}),
        ("rest.weekly_min_days", {"min_days": "1"}),
        ("contract.modality", {
            "modality": "pj",
            "allowed": False,
            "max_duration_days": None,
            "requires_legal_review": True,
        }),
        ("contract.modality", {
            "modality": "temporario",
            "allowed": True,
            "max_duration_days": 0,
            "requires_legal_review": True,
        }),
        ("internship.counts_as_capacity", {"allowed": "true"}),
    ]
    for rule_key, parameters in rejected:
        with pytest.raises(ValidationError):
            validate_parameters(rule_key, parameters)

    week = validate_parameters("workweek.max_hours", {"max_hours": "1000"})
    assert week.max_hours == Decimal("1000")
    assert validate_parameters("rest.weekly_min_days", {"min_days": 1}).min_days == 1
    assert validate_parameters("rest.weekly_min_days", {"min_days": 7}).min_days == 7
    open_ended = validate_parameters("contract.modality", {
        "modality": "estagio",
        "allowed": False,
        "max_duration_days": None,
        "requires_legal_review": True,
    })
    assert open_ended.max_duration_days is None
    assert open_ended.allowed is False


def test_extra_field_is_rejected():
    with pytest.raises(ValidationError):
        validate_parameters("workweek.max_hours", {"max_hours": "1", "note": "cap"})
    with pytest.raises(ValidationError):
        validate_parameters("workweek.max_hours", {"max_hours": "1", "requires_collective_agreement": False})
    with pytest.raises(ValidationError):
        PolicyCreate.model_validate(_create(tenant_id="tenant-demo-a"))
    with pytest.raises(ValidationError):
        PolicyCreate.model_validate(_create(status="approved"))
    with pytest.raises(ValidationError):
        PolicyCreate.model_validate(_create(category="jornada"))


def test_limits_have_no_defaults():
    for rule_key, (_category, schema) in CATALOG.items():
        document = schema.model_json_schema()
        assert set(document["required"]) == set(schema.model_fields)
        for name, field in schema.model_fields.items():
            assert field.is_required(), rule_key
            assert field.default is PydanticUndefined
            assert field.default_factory is None
            assert "default" not in document["properties"][name]
        with pytest.raises(ValidationError):
            schema.model_validate({})

    with pytest.raises(ValidationError):
        validate_parameters("workday.max_hours", {"max_hours": "1"})
    with pytest.raises(ValidationError):
        validate_parameters("contract.modality", {
            "modality": "aprendiz",
            "allowed": True,
            "requires_legal_review": False,
        })
    with pytest.raises(ValidationError):
        validate_parameters("internship.counts_as_capacity", {})

    created = PolicyCreate.model_validate(_create())
    assert created.parameters.max_hours == Decimal("1")
    assert created.team_id == "team-1"
    company = dict(_create())
    company["team_id"] = None
    assert PolicyCreate.model_validate(company).team_id is None
    for omitted in ("team_id", "employee_category", "parameters", "valid_until"):
        body = _create()
        del body[omitted]
        with pytest.raises(ValidationError):
            PolicyCreate.model_validate(body)


def test_parameters_must_match_rule_key():
    with pytest.raises(ValidationError):
        PolicyCreate.model_validate(_create(
            parameters={"max_hours": "1", "requires_collective_agreement": True},
        ))
    body = _create(
        rule_key="workday.max_hours",
        parameters={"max_hours": "2", "requires_collective_agreement": True},
    )
    created = PolicyCreate.model_validate(body)
    assert created.parameters.requires_collective_agreement is True
    inverted = _create(valid_from="2026-02-01", valid_until="2026-02-01")
    with pytest.raises(ValidationError):
        PolicyCreate.model_validate(inverted)
    for bad_date in ("2026-01-01T00:00:00", "2026-02-31", "2026-1-01"):
        with pytest.raises(ValidationError):
            PolicyCreate.model_validate(_create(valid_from=bad_date))


def test_new_version_rejects_partial_content():
    with pytest.raises(ValidationError):
        VersionCreate.model_validate({
            "copy_from_version_id": None,
            "parameters": None,
            "source_kind": None,
            "source_reference": None,
            "valid_from": None,
            "valid_until": None,
        })
    with pytest.raises(ValidationError):
        VersionCreate.model_validate({
            "copy_from_version_id": "version-1",
            "parameters": {"max_hours": "1"},
            "source_kind": None,
            "source_reference": None,
            "valid_from": None,
            "valid_until": None,
        })
    with pytest.raises(ValidationError):
        VersionCreate.model_validate({
            "copy_from_version_id": "version-1",
            "parameters": None,
            "source_kind": None,
            "source_reference": None,
            "valid_from": None,
            "valid_until": "2026-12-31",
        })
    copied = VersionCreate.model_validate({
        "copy_from_version_id": "version-1",
        "parameters": None,
        "source_kind": None,
        "source_reference": None,
        "valid_from": None,
        "valid_until": None,
    })
    assert copied.parameters is None
    written = VersionCreate.model_validate({
        "copy_from_version_id": None,
        "parameters": {"min_days": 7},
        "source_kind": "sintetico",
        "source_reference": SOURCE,
        "valid_from": "2026-01-01",
        "valid_until": None,
    })
    assert written.parameters.min_days == 7
    with pytest.raises(ValidationError):
        VersionUpdate.model_validate({
            "expected_revision": 1,
            "source_kind": "sintetico",
            "source_reference": SOURCE,
            "valid_from": "2026-01-01",
            "valid_until": None,
        })


def test_transitions_do_not_default_the_required_text():
    with pytest.raises(ValidationError):
        ApproveIn.model_validate({"expected_revision": 1})
    with pytest.raises(ValidationError):
        ApproveIn.model_validate({"expected_revision": 1, "legal_review_reference": "  "})
    approved = ApproveIn.model_validate({"expected_revision": 1, "legal_review_reference": "parecer-sintetico-1"})
    assert approved.legal_review_reference == "parecer-sintetico-1"
    with pytest.raises(ValidationError):
        RejectIn.model_validate({"expected_revision": 1, "review_note": ""})
    with pytest.raises(ValidationError):
        RevokeIn.model_validate({"expected_revision": 1})
    with pytest.raises(ValidationError):
        ApproveIn.model_validate({"legal_review_reference": "parecer-sintetico-1"})


def test_resolution_rejects_partial_rules():
    ok = PolicyResolution.model_validate(_resolution([_resolved()], True))
    assert ok.complete is True
    assert ok.on_date == date(2026, 11, 8)
    assert ok.items[0].parameters.max_hours == Decimal("1")

    partial = _review()
    partial["version_id"] = "version-1"
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([partial], False))

    missing_reason = _review()
    missing_reason["reason"] = None
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([missing_reason], False))

    leaked = _review(reason="pinned_not_found")
    leaked["version_id"] = "version-x"
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([leaked], False))
    hidden = _review(rule_key=None, reason="pinned_not_found")
    hidden["version_id"] = "version-x"
    found = PolicyResolution.model_validate(_resolution([hidden], False))
    assert found.items[0].rule_key is None
    assert found.items[0].version_id == "version-x"
    assert found.items[0].parameters is None
    assert found.complete is False
    revoked = _review(reason="pinned_revoked")
    revoked["version_id"] = "version-1"
    revoked["version"] = 2
    pinned = PolicyResolution.model_validate(_resolution([revoked], False))
    assert pinned.items[0].parameters is None
    revoked["parameters"] = {"max_hours": "1"}
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([revoked], False))
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([_review("not.a.rule")], False))

    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([_resolved(), _review()], True))
    mixed = PolicyResolution.model_validate(_resolution(
        [_resolved(), _review("rest.weekly_min_days")],
        False,
    ))
    assert [item.rule_key for item in mixed.items] == ["workweek.max_hours", "rest.weekly_min_days"]
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([_resolved(), _resolved()], True))
    other = _resolved("rest.weekly_min_days", {"min_days": 1})
    other["version_id"] = "version-1"
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([_resolved(), other], True))
    with pytest.raises(ValidationError):
        PolicyResolution.model_validate(_resolution([_resolved()], True) | {"surprise": 1})


def test_list_filters_do_not_invent_a_category():
    with pytest.raises(ValidationError):
        PolicyListQuery.model_validate({
            "rule_key": None,
            "category": "clt",
            "team_id": None,
            "status": None,
        })
    filters = PolicyListQuery.model_validate({
        "rule_key": "contract.modality",
        "category": None,
        "team_id": None,
        "status": "approved",
    })
    assert filters.status == "approved"
    with pytest.raises(ValidationError):
        PolicyListQuery.model_validate({"status": "approved"})
