from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Membership, Principal, Role
from backend.app.core.config import Settings
from alembic import command
from alembic.config import Config
from backend.app.flow.models import DataImport, InvestigationRun, JiraCollection
from backend.app.ingestion.collection import collect_jira
from backend.app.ingestion.csvparse import parse_csv
from backend.app.ingestion.demo import PROFILES, demo_csv
from backend.app.ingestion.jira import IntegrationUnavailable
from backend.app.ingestion.service import confirm_import, submit_csv
from backend.app.main import create_app
from backend.app.optimization.cpsat_v42 import ExistingPool, HiringOption, IntervalDemand, solve_capacity

PASSWORD = "synthetic-test-password"
TEAM = "team-demo"


@pytest.fixture
def app(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'planning.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("backend/alembic.ini"), "head")
    application = create_app(Settings(url, auth_secret="s" * 40))
    sessions = application.state.session_factory
    for tenant in ("first", "second"):
        create_tenant(sessions, tenant, tenant)
        create_user(sessions, tenant, "rh@demo.test", Role.RH, None, PASSWORD)
    create_user(sessions, "first", "manager@demo.test", Role.GESTOR, "restricted", PASSWORD)
    return application


def _headers(client, tenant="first", email="rh@demo.test"):
    result = client.post("/api/auth/login", json={"tenant_id": tenant, "email": email, "password": PASSWORD})
    assert result.is_success, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def _request(client, method, path, headers, body=None, status=200):
    kwargs = {} if body is None else {"json": body}
    response = client.request(method, path, headers=headers, **kwargs)
    assert response.status_code == status, response.text
    return response.json()


@pytest.mark.parametrize("profile", PROFILES)
def test_generated_shift_history_and_flow_conserve_totals(profile):
    content = demo_csv(profile)
    assert content == demo_csv(profile)
    parsed = parse_csv(content, tenant_id="demo", team_id=TEAM, snapshot_id="snapshot", reference="demo")
    assert parsed["errors"] == []
    assert len(parsed["history"]) == 88
    previous = None
    for row in parsed["history"]:
        numbers = {key: Decimal(value) for key, value in row.items()
                   if key.endswith("_cases") or key.startswith("backlog_")}
        assert numbers["backlog_end"] == (numbers["backlog_start"] + numbers["incoming_cases"]
                                          + numbers["reopened_cases"] - numbers["completed_cases"]
                                          - numbers["cancelled_cases"])
        if previous is not None:
            assert numbers["backlog_start"] == previous
        previous = numbers["backlog_end"]
        for use_shifts in (False, True):
            assert sum(Decimal(s["quantity"]) for s in row["segments"] if bool(s["shift_id"]) == use_shifts) == Decimal(row["quantity"])


def test_full_demo_replans_and_follows_human_baseline_decision(app):
    with TestClient(app) as client:
        headers = _headers(client)
        other = _headers(client, "second")
        manager = _headers(client, email="manager@demo.test")
        load = lambda **params: _request(client, "POST", "/api/imports/synthetic", headers, {"team_id": TEAM, **params})
        snapshot = load()["snapshot_id"]
        assert load()["snapshot_id"] == snapshot
        body = dict(team_id=TEAM, snapshot_id=snapshot, idempotency_key="demo-one", cycle_limit=3)
        opened = _request(client, "POST", "/api/investigations", headers, body, 202)
        path = f"/api/investigations/{opened['run_id']}"
        run = _request(client, "POST", path + "/advance", headers)
        assert run["state"] == "AWAITING_HUMAN"
        forecast = run["forecast"]
        assert forecast["status"] == "calibrated"
        assert len(forecast["points"]) == 4
        assert len([s for s in forecast["segments"] if s["shift_id"]]) == 6
        assert forecast["backtest"]["calibration_through"] <= forecast["backtest"]["evaluation_starts"]
        assert "seasonal_naive_13" in forecast["backtest"]["benchmarks"]
        assert all(p["p10"] <= p["p50"] <= p["p90"] for p in forecast["points"])
        items = _request(client, "GET", path + "/scenarios", headers)["items"]
        assert len(items) == 5 and all(not item["conclusive"] for item in items)
        by_kind = {item["kind"]: item for item in items}
        q = {key: item["quantitative"] for key, item in by_kind.items()}
        assert len({value["residual_hours"] for value in q.values()}) == 5
        targets = [[week["target_hours"] for week in value["weeks"]] for value in q.values()]
        assert all(series == targets[0] for series in targets)
        assert all(value["validation"]["mathematical_status"] == "verified" for value in q.values())
        assert all(value["synthetic"] and value["source_snapshot"] == snapshot for value in q.values())
        assert q["temporary"]["lead_time"]["ends_before"] == q["temporary"]["weeks"][-1]["starts"]
        assert q["temporary"]["weeks"][-1]["incremental_cost_brl"] == 0
        assert q["hire"]["weeks"][1]["available_hours"] <= q["do_nothing"]["weeks"][1]["available_hours"]
        assert q["hire"]["weeks"][2]["available_hours"] > q["do_nothing"]["weeks"][2]["available_hours"]
        for kind in ("reallocate", "redesign"):
            assert any(week["moved_hours"] for week in q[kind]["weeks"])
            assert all(a["available_hours"] <= b["available_hours"]
                       for a, b in zip(q[kind]["weeks"], q["do_nothing"]["weeks"]))
        assert all(value["queue"]["runs"] == 12 for value in q.values())
        repeat = _request(client, "POST", "/api/investigations", headers, {**body, "idempotency_key": "demo-repeat"}, 202)
        repeat_path = f"/api/investigations/{repeat['run_id']}"
        _request(client, "POST", repeat_path + "/advance", headers)
        again = _request(client, "GET", repeat_path + "/scenarios", headers)["items"]
        assert q == {item["kind"]: item["quantitative"] for item in again}

        for forbidden in (other, manager):
            _request(client, "GET", path + "/planning-summary", forbidden, status=404)
        agent = _request(client, "GET", path + "/planning-summary", headers)
        assert len(agent["scenarios"]) == 5
        assert "assumptions" not in str(agent) and "dependencies" not in str(agent)
        baseline = by_kind["do_nothing"]
        route = f"/api/scenarios/{baseline['scenario_id']}"
        decide = {"decision": "approve", "expected_hash": baseline["content_hash"], "reason": "Revisão",
                  "idempotency_key": "deny-exploration"}
        assert _request(client, "POST", route + "/decisions", headers, decide, 409)["detail"]["code"] == "NOT_CONCLUSIVE"
        _request(client, "POST", route + "/decisions", headers,
                 {**decide, "decision": "defer", "idempotency_key": "defer-baseline"})
        week = q["do_nothing"]["weeks"][0]["starts"]
        observed = {"week_start": week, "arrival_cases": 800, "backlog_end": 200, "sla_fraction": 0.2,
                    "incremental_cost_brl": 0.0, "adverse_effect": True, "justification": "Observação sintética"}
        outcome = _request(client, "POST", route + "/observations", headers, observed)
        assert outcome["recommend_investigation"] and outcome["delta"]["sla_fraction"] is not None
        assert outcome == _request(client, "POST", route + "/observations", headers, observed)
        assert _request(client, "GET", route + "/observations", headers)["items"] == [outcome]
        _request(client, "GET", route + "/observations", other, status=404)

        newer = load(profile="turnos", extra_weeks=1)["snapshot_id"]
        revision = {"snapshot_id": newer, "expected_version": run["version"], "idempotency_key": "v2",
                    "reason": "Novo recorte conferido"}
        replanned = _request(client, "POST", path + "/replan", headers, revision)
        assert replanned["state"] == "AWAITING_HUMAN" and replanned["snapshot_id"] == newer
        assert replanned["forecast"]["history_end_exclusive"] > forecast["history_end_exclusive"]
        revised = _request(client, "GET", path + "/scenarios", headers)["items"]
        assert {item["version"] for item in revised} == {2}
        assert q["hire"]["residual_hours"] != next(item["quantitative"]["residual_hours"] for item in revised if item["kind"] == "hire")
        assert _request(client, "POST", path + "/replan", headers, revision) == replanned
        assert _request(client, "GET", path + "/evidence", headers)["items"][0]["previous_snapshot_id"] == snapshot
        stale = by_kind["hire"]
        rejection = _request(client, "POST", f"/api/scenarios/{stale['scenario_id']}/decisions", headers,
                             {**decide, "expected_hash": stale["content_hash"]}, 409)
        assert rejection["detail"]["code"] == "MATERIAL_CHANGE"
        limited = _request(client, "POST", path + "/replan", headers, {
            "snapshot_id": newer, "expected_version": replanned["version"], "idempotency_key": "budget",
            "reason": "Sem verba no horizonte", "premises": {"hiring_budget_brl": 0.0},
        })
        assert limited["snapshot_id"] == newer
        budget_items = _request(client, "GET", path + "/scenarios", headers)["items"]
        hiring = next(item for item in budget_items if item["kind"] == "hire")["quantitative"]
        assert hiring["headcount"] == 0 and hiring["hiring_budget_brl"] == 0
        assert hiring["premise_source"] == "rh_reviewed"
        assert any(item["quantitative"]["transitions"] for item in budget_items if item["kind"] == "redesign")


def test_solver_weekly_caps_expiry_and_unknown_timeout():
    start = date(2026, 11, 2)
    windows = [(start + timedelta(weeks=i), start + timedelta(weeks=i + 1)) for i in range(3)]
    needs = [IntervalDemand(f"{i}-{skill}", *window, skill, "day", 0, 6)
             for i, window in enumerate(windows) for skill in ("a", "b")]
    shared = ExistingPool("shared", ("a", "b"), ("day",), 24, {n.interval_id: 6 for n in needs},
                          schedule_verified=True, caps_by_window=dict.fromkeys(windows, 8))
    hire = HiringOption("temp", ("a",), ("day",), windows[1][0], 4, 1, 1, 100,
                        modality_verified=True, ends_before=windows[1][1])
    params = dict(needs=needs, pools=[shared], options=[hire], budget_cents=1, policy_evidence_id=None,
                  policy_verified=False, simulation_only=True)
    solved = solve_capacity(**params)
    assert solved.status == "optimal"
    assert solved.hire_allocations == {"temp": {"1-a": 4}}
    assert [sum(hours for key, hours in solved.pool_allocations["shared"].items() if key.startswith(str(i)))
            for i in range(3)] == [8, 8, 8]
    assert solve_capacity(**params, timeout_seconds=1e-12).status == "unknown"


def test_jira_collection_scopes_deduplicates_and_uses_metadata_only(app):
    instant = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
    principal = Principal("worker", "first", (Membership(Role.RH, None),))
    settings = replace(app.state.settings, jira_base_url="https://jira.invalid", jira_project_key="OPS",
                       jira_api_token="unit-test", jira_team_id=TEAM, jira_tenant_id="first", jira_skill_map='{"10":"atendimento"}')
    with app.state.session_factory() as session:
        seed = submit_csv(session, principal, team_id=TEAM, filename="cap.csv", content=demo_csv())
        confirm_import(session, principal, seed.import_id)
        settings = replace(settings, jira_capacity_snapshot_id=seed.snapshot_id)
        session.commit()
    calls = []

    def transport(method, url, params, headers):
        assert method == "GET" and url.endswith("/search/jql")
        assert params["fields"] == "created,issuetype,project"
        assert "created >=" in params["jql"]
        calls.append(params)
        issue = {"id": "1", "fields": {"created": "2026-11-01T20:00:00-03:00", "issuetype": {"id": "10"},
                                        "project": {"key": "OPS"}, "summary": "contact private@example.test"}}
        if "nextPageToken" not in params:
            return {"issues": [issue], "isLast": False, "nextPageToken": "next"}
        return {"issues": [issue], "isLast": True}

    with app.state.session_factory() as session:
        first = collect_jira(session, principal, settings, transport=transport, now=instant)
        session.commit()
        assert first["status"] == "complete" and not first["duplicated"]
    with app.state.session_factory() as session:
        row = session.scalar(select(DataImport).where(DataImport.snapshot_id == first["snapshot_id"]))
        assert "private@example" not in str(row.history) + str(row.preview)
        assert sum(Decimal(w["quantity"]) for w in row.history) == 1
        assert row.history[-1]["demand_semantics"] == "jira_created_arrivals"
        retry = collect_jira(session, principal, settings, transport=transport, now=instant)
        session.commit()
        assert retry["duplicated"] and retry["snapshot_id"] == first["snapshot_id"]
        assert len(list(session.scalars(select(JiraCollection)))) == 1
        assert len(calls) == 4
    with app.state.session_factory() as session, pytest.raises(IntegrationUnavailable):
        collect_jira(session, principal, settings, now=instant,
                     transport=lambda *args: {"issues": [], "isLast": False})


def test_missing_cost_and_queue_inputs_stay_unknown(app):
    with TestClient(app) as client:
        headers = _headers(client)
        content = demo_csv().replace(",BRL,", ",,").replace(",24,37,,", ",,,,").replace(",32,54,,", ",,,,")
        imported = _request(client, "POST", "/api/imports", headers,
                            {"team_id": TEAM, "filename": "alinia-demo-impostor.csv", "content": content})
        assert imported["status"] == "ready"
        snapshot = _request(client, "POST", f"/api/imports/{imported['import_id']}/confirm", headers)["snapshot_id"]
        opened = _request(client, "POST", "/api/investigations", headers,
                          dict(team_id=TEAM, snapshot_id=snapshot, idempotency_key="missing", cycle_limit=2), 202)
        with app.state.session_factory() as session:
            row = session.scalar(select(DataImport).where(DataImport.snapshot_id == snapshot))
            row.aggregates = {**row.aggregates, "queue_sla_hours": None}
            session.commit()
        path = f"/api/investigations/{opened['run_id']}"
        _request(client, "POST", path + "/advance", headers)
        items = _request(client, "GET", path + "/scenarios", headers)["items"]
        hiring = next(item for item in items if item["kind"] == "hire")["quantitative"]
        assert hiring["headcount"] is None and hiring["cost_range_brl"] is None
        assert hiring["incremental_cost_brl"] is None and hiring["cost_status"] == "unavailable"
        assert hiring["queue"]["status"] == "unavailable" and not hiring["synthetic"]

        # A captured upstream low-volume series, even with an authorized token,
        # is withheld from the model-facing endpoint.
        with app.state.session_factory() as session:
            run = session.get(InvestigationRun, opened["run_id"])
            run.forecast = {**run.forecast, "points": [
                {**point, "point_estimate": 2} for point in run.forecast["points"]
            ]}
            session.commit()
        blocked = _request(client, "GET", path + "/planning-summary", headers, status=409)
        assert blocked["detail"]["code"] == "AGGREGATION_REQUIRED"
