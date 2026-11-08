"""PRD v4.2 acceptance tests independent of any generative model."""
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.app.contracts.v42 import (
    Assignment, CoverageNeed, DemandFlow, HiringLeadTime, ManagerReport,
    ReadyCapacity, ScenarioReadiness,
)
from backend.app.optimization.validator_v42 import verify_interval

UTC = timezone.utc


def test_incoming_not_confused_with_completed_and_backlog_reconciles():
    ledger = DemandFlow(
        team_id="team-a", skill_id="tickets", period_start=date(2026, 11, 2),
        period_end_exclusive=date(2026, 11, 9), unit="cases_per_period",
        incoming_cases=120, completed_cases=95, cancelled_cases=5, reopened_cases=3,
        unmet_cases=9, backlog_start=15, backlog_end=38, source_version="csv-v42",
    )
    assert ledger.demand_exposure == 129
    with pytest.raises(ValidationError):
        ledger.model_copy(update={"backlog_end": 0}).model_validate(
            {**ledger.model_dump(), "backlog_end": 0}
        )


def test_manager_report_is_never_a_verified_fact():
    report = ManagerReport(author_user_id="manager-1",
                           reported_at=datetime(2026, 11, 8, tzinfo=UTC),
                           statement="A alta de chamados parece sazonal.")
    assert report.verification == "unverified"
    with pytest.raises(ValidationError):
        ManagerReport(author_user_id="manager-1", reported_at=datetime(2026, 11, 8),
                      statement="Relato sem data verificável.")


def test_mandatory_and_operational_goals_are_distinct():
    start = datetime(2026, 11, 9, 8, tzinfo=UTC)
    need = CoverageNeed(skill_id="helpdesk", shift_id="morning", interval_start=start,
                        interval_end=start + timedelta(hours=4), mandatory_hours=2, target_hours=4)
    capacity = [ReadyCapacity(pool_id="pool-a", skill_id="helpdesk", shift_id="morning",
                              available_hours=3, ready_at=start, qualification_verified=True,
                              approved_work_schedule=True)]
    allocations = [Assignment(pool_id="pool-a", skill_id="helpdesk", shift_id="morning", hours=2)]
    readiness = ScenarioReadiness(policy_evidence_id="policy-approved-1", policy_rules_current=True,
                                  rest_and_daily_limits_verified=True, budget_approved=True,
                                  legal_modality_verified=True)
    checked = verify_interval(scenario_id="scenario-a", need=need, capacity=capacity,
                              assignments=allocations, readiness=readiness)
    assert checked.status == "valid" and checked.mandatory_coverage_met
    assert checked.operational_residual_hours == 2

    late = capacity[0].model_copy(update={"ready_at": start + timedelta(days=20)})
    blocked = verify_interval(scenario_id="scenario-b", need=need, capacity=[late],
                              assignments=allocations, readiness=readiness)
    assert blocked.status == "blocked"
    assert "CAPACITY_ARRIVES_TOO_LATE" in blocked.violations
    assert "MANDATORY_COVERAGE_MISSING" in blocked.violations

    unapproved = verify_interval(
        scenario_id="scenario-c", need=need, capacity=capacity,
        assignments=allocations, readiness=ScenarioReadiness(),
    )
    assert unapproved.status == "blocked" and "POLICY_REVIEW_REQUIRED" in unapproved.violations


def test_extra_hours_and_unqualified_people_never_pass():
    start = datetime(2026, 11, 9, tzinfo=UTC)
    need = CoverageNeed(skill_id="helpdesk", shift_id="morning", interval_start=start,
                        interval_end=start + timedelta(hours=4), mandatory_hours=3, target_hours=4)
    capacity = [ReadyCapacity(pool_id="pool-a", skill_id="helpdesk", shift_id="morning",
                              available_hours=2, ready_at=start, qualification_verified=False,
                              approved_work_schedule=True)]
    verified = ScenarioReadiness(policy_evidence_id="p", policy_rules_current=True,
                                 rest_and_daily_limits_verified=True, budget_approved=True,
                                 legal_modality_verified=True)
    result = verify_interval(
        scenario_id="s", need=need, capacity=capacity,
        assignments=[Assignment(pool_id="pool-a", skill_id="helpdesk",
                                shift_id="morning", hours=3)],
        readiness=verified,
    )
    assert {"TRAINING_NOT_COMPLETED", "POOL_HOURS_EXCEEDED",
            "MANDATORY_COVERAGE_MISSING"}.issubset(result.violations)


def test_lead_time_and_training_make_capacity_future_dated():
    lead = HiringLeadTime(
        requested_at=date(2026, 11, 8), recruitment_days=10, admission_days=3,
        training_days=14, mentor_hours=16, ramp_up_fraction="0.5",
    )
    assert lead.first_eligible_day == date(2026, 12, 5)
