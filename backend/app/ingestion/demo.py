"""Reproducible weekly fixtures consumed through the aggregate CSV import path."""
import argparse
import csv
from dataclasses import astuple, dataclass
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from random import Random
from typing import Literal, get_args

from backend.app.ingestion.csvparse import REQUIRED, OPTIONAL

DemoProfile = Literal["gargalo", "pico", "estrutural", "turnos", "pico-e-retomada"]
PROFILES = get_args(DemoProfile)
SEASON = (0, 2, 3, 5, 7, 9, 5, 3, 0, -2, -3, -4, -2)
PEAK = {
    ("atendimento", "noite"): (42, 65),
    ("triagem", "noite"): (10, 14),
    ("especializado", "dia"): (31, 51),
}
PEAK_ROWS = {
    ("atendimento", "dia"): (92, 84, ("pool-atendimento",)),
    ("atendimento", "noite"): (48, 40, ("pool-noturno",)),
    ("triagem", "dia"): (43, 38, ("pool-triagem", "pool-compartilhado")),
    ("triagem", "noite"): (31, 36, ("pool-noturno",)),
    ("especializado", "dia"): (55, 42, ("pool-especializado", "pool-compartilhado")),
    ("especializado", "noite"): (26, 26, ("pool-especializado",)),
}
PEAK_POOLS = {"pool-atendimento": 84, "pool-noturno": 65, "pool-triagem": 28,
              "pool-compartilhado": 26, "pool-especializado": 58}
BASE = {
    ("atendimento", "dia"): (105, 92, ("pool-atendimento",)),
    ("atendimento", "noite"): (70, 28, ("pool-noturno",)),
    ("triagem", "dia"): (48, 40, ("pool-triagem", "pool-compartilhado")),
    ("triagem", "noite"): (40, 29, ("pool-noturno",)),
    ("especializado", "dia"): (93, 30, ("pool-especializado", "pool-compartilhado")),
    ("especializado", "noite"): (33, 24, ("pool-especializado",)),
}
POOLS = {"pool-atendimento": 92, "pool-noturno": 42, "pool-triagem": 23,
         "pool-compartilhado": 22, "pool-especializado": 36}



@dataclass
class Flow:
    incoming: int
    reopened: int
    cancelled: int
    unmet: int
    opening: int
    closing: int

    @property
    def completed(self):
        return self.opening + self.incoming + self.reopened - self.cancelled - self.closing


def _peak_flow(rows, skill, demand, backlog, pool_hours, peak):
    # Historical service uses the same shared-pool ceilings as the snapshot.
    # In the synthetic operation, teams prioritize registered work in skill
    # order. Demand outside the register is counted separately.
    flows = {}
    for shift, cases in sorted(demand.items()):
        key = skill, shift
        unmet = (cases * 8 // 100) if peak and key in PEAK else 1
        incoming = cases - unmet
        reopened = max(1, incoming // (16 if peak and key in PEAK else 28))
        cancelled = 1
        opening = backlog[key]
        _, eligible, pools = rows[key]
        work = opening + incoming + reopened - cancelled
        completed = 0
        for pool in pools:
            hours = min(pool_hours[pool], eligible, (work - completed + 1) // 2)
            completed += min(work - completed, 2 * hours)
            eligible -= hours
            pool_hours[pool] -= hours
        closing = work - completed
        backlog[key] = closing
        flows[shift] = Flow(incoming, reopened, cancelled, unmet, opening, closing)
    return flows

def demo_csv(profile="gargalo", *, extra_weeks=0):
    if profile not in PROFILES or not 0 <= extra_weeks <= 8:
        raise ValueError("invalid demo profile or extension")
    rng = Random(4115)
    text = StringIO()
    writer = csv.DictWriter(text, fieldnames=[*REQUIRED, *OPTIONAL], lineterminator="\n")
    writer.writeheader()
    pulse = profile == "pico-e-retomada"
    rows = PEAK_ROWS if pulse else BASE
    pools_by_id = PEAK_POOLS if pulse else POOLS
    skills = sorted({skill for skill, _ in rows})
    backlog = dict.fromkeys(skills, 0)
    shift_backlog = dict.fromkeys(rows, 0)
    for index in range(88 + extra_weeks):
        start = date(2025, 3, 3) + timedelta(weeks=index)
        phase = index % len(SEASON)
        peak = pulse and phase in {11, 12}
        pool_hours = dict(pools_by_id)
        for skill in skills:
            by_shift = {}
            for (row_skill, shift), (base, _, _) in rows.items():
                if row_skill != skill:
                    continue
                boost = 0
                if profile == "pico" and index % 13 in {10, 11, 12, 0, 1, 2} and shift == "noite":
                    boost = 16
                if profile == "estrutural" and skill == "especializado":
                    boost = 22 + index // 12
                if profile == "turnos" and skill == "atendimento":
                    boost = 18 if shift == "noite" else -18
                if peak:
                    boost = PEAK.get((skill, shift), (0, 0))[phase - 11]
                # A small drift and a sustained change in historical operating mix.
                by_shift[shift] = base + SEASON[phase] + index // 12 + (index >= 35) * 3 + boost + rng.randint(-4, 4)
            total = sum(by_shift.values())
            if pulse:
                by_shift_flow = _peak_flow(rows, skill, by_shift, shift_backlog, pool_hours, peak)
                flow = Flow(*(sum(values) for values in zip(*(astuple(item) for item in by_shift_flow.values()))))
                backlog_by_shift = {shift: item.closing for shift, item in by_shift_flow.items()}
            else:
                unmet = 2 + index % 3
                incoming = total - unmet
                closing = min(8, max(0, 3 + (index + len(skill)) % 6 - 1))
                flow = Flow(incoming, max(1, incoming // 24), 2, unmet, backlog[skill], closing)
                backlog[skill] = closing
                backlog_by_shift = {"dia": closing // 2, "noite": closing - closing // 2}
            for shift, cases in sorted(by_shift.items()):
                _, eligible, pools = rows[(skill, shift)]
                for pool in pools:
                    writer.writerow({
                        "skill_id": skill, "shift_id": shift, "pool_id": pool, "eligible_hours": eligible,
                        "available_hours": pools_by_id[pool], "period_start": start.isoformat(),
                        "period_end_exclusive": (start + timedelta(weeks=1)).isoformat(),
                        "timezone": "America/Fortaleza", "demand_cases": total, "hours_unit": "hours_per_period",
                        "demand_unit": "cases_per_period", "cost_min": 32 if skill == "especializado" else 24,
                        "cost_max": 54 if skill == "especializado" else 37, "currency": "BRL",
                        "cases_per_hour": 2, "incoming_cases": flow.incoming, "completed_cases": flow.completed,
                        "cancelled_cases": flow.cancelled, "reopened_cases": flow.reopened, "unmet_cases": flow.unmet,
                        "backlog_start": flow.opening, "backlog_end": flow.closing, "shift_demand_cases": cases,
                        "shift_backlog_end": backlog_by_shift[shift],
                        "queue_sla_hours": 24, "service_cv": "0.65",
                    })
    return text.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="gargalo")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(demo_csv(args.profile), encoding="utf-8")


if __name__ == "__main__":
    main()
