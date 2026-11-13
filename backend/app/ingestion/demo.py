"""Reproducible weekly fixtures consumed through the aggregate CSV import path."""
import argparse
import csv
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from random import Random

from backend.app.ingestion.csvparse import REQUIRED, OPTIONAL

PROFILES = ("gargalo", "pico", "estrutural", "turnos")
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


def demo_csv(profile="gargalo", *, extra_weeks=0):
    if profile not in PROFILES or not 0 <= extra_weeks <= 8:
        raise ValueError("invalid demo profile or extension")
    rng = Random(4115)
    text = StringIO()
    writer = csv.DictWriter(text, fieldnames=[*REQUIRED, *OPTIONAL], lineterminator="\n")
    writer.writeheader()
    backlog = dict.fromkeys({skill for skill, _ in BASE}, 0)
    for index in range(88 + extra_weeks):
        start = date(2025, 3, 3) + timedelta(weeks=index)
        phase = (0, 2, 3, 5, 7, 9, 5, 3, 0, -2, -3, -4, -2)[index % 13]
        for skill in sorted(backlog):
            by_shift = {}
            for (row_skill, shift), (base, _, _) in BASE.items():
                if row_skill != skill:
                    continue
                boost = 0
                if profile == "pico" and index % 13 in {10, 11, 12, 0, 1, 2} and shift == "noite":
                    boost = 16
                if profile == "estrutural" and skill == "especializado":
                    boost = 22 + index // 12
                if profile == "turnos" and skill == "atendimento":
                    boost = 18 if shift == "noite" else -18
                # A small drift and a sustained change in historical operating mix.
                by_shift[shift] = base + phase + index // 12 + (index >= 35) * 3 + boost + rng.randint(-4, 4)
            total = sum(by_shift.values())
            unmet = 2 + index % 3
            incoming = total - unmet
            reopened = max(1, incoming // 24)
            cancelled = 2
            opening = backlog[skill]
            closing = min(8, max(0, 3 + (index + len(skill)) % 6 - 1))
            completed = opening + incoming + reopened - cancelled - closing
            backlog[skill] = closing
            for shift, cases in sorted(by_shift.items()):
                _, eligible, pools = BASE[(skill, shift)]
                for pool in pools:
                    writer.writerow({
                        "skill_id": skill, "shift_id": shift, "pool_id": pool, "eligible_hours": eligible,
                        "available_hours": POOLS[pool], "period_start": start.isoformat(),
                        "period_end_exclusive": (start + timedelta(weeks=1)).isoformat(),
                        "timezone": "America/Fortaleza", "demand_cases": total, "hours_unit": "hours_per_period",
                        "demand_unit": "cases_per_period", "cost_min": 32 if skill == "especializado" else 24,
                        "cost_max": 54 if skill == "especializado" else 37, "currency": "BRL",
                        "cases_per_hour": 2, "incoming_cases": incoming, "completed_cases": completed,
                        "cancelled_cases": cancelled, "reopened_cases": reopened, "unmet_cases": unmet,
                        "backlog_start": opening, "backlog_end": closing, "shift_demand_cases": cases,
                        "shift_backlog_end": closing // 2 if shift == "dia" else closing - closing // 2,
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
