"""Conditional SimPy queue model using common random streams for A–E."""
from random import Random
from statistics import mean
from collections import defaultdict
from decimal import Decimal

import simpy

SEEDS = (115, 209, 337, 401, 503, 601, 709, 811, 919, 1009, 1103, 1201)
WEEK_HOURS = 168


def _draw_work(rng, service, cv):
    if cv == 0:
        return service
    return rng.gammavariate(1 / cv ** 2, service * cv ** 2)


def _simulate(rows, rate, cv, opening, seed):
    env = simpy.Environment()
    rng = Random(seed)
    pending = simpy.Store(env)
    completed = []
    arrivals = []

    def register():
        for _ in range(round(opening)):
            yield pending.put((None, _draw_work(rng, 1 / rate, cv)))
        for index, row in enumerate(rows):
            end = (index + 1) * WEEK_HOURS
            intensity = row["arrival_cases"] / WEEK_HOURS
            while intensity:
                delay = rng.expovariate(intensity)
                if env.now + delay >= end:
                    break
                yield env.timeout(delay)
                arrivals.append(env.now)
                yield pending.put((env.now, _draw_work(rng, 1 / rate, cv)))
            yield env.timeout(end - env.now)

    def serve():
        while True:
            arrival, work = yield pending.get()
            while work > 1e-9:
                index = int(env.now // WEEK_HOURS)
                if index == len(rows):
                    return
                remaining = (index + 1) * WEEK_HOURS - env.now
                speed = rows[index]["covered_hours"] / WEEK_HOURS
                elapsed = min(remaining, work / speed) if speed else remaining
                yield env.timeout(elapsed)
                work -= elapsed * speed
            completed.append((arrival, env.now))

    env.process(register())
    env.process(serve())
    env.run(until=len(rows) * WEEK_HOURS)
    return arrivals, completed


def simulate_queues(weeks, rate, rework, initial, aggregates):
    sla = float(aggregates["queue_sla_hours"]) if aggregates.get("queue_sla_hours") else None
    cv = float(aggregates["service_cv"]) if aggregates.get("service_cv") else None
    total = sum(week["arrival_cases"] for week in weeks)
    if (not weeks or not sla or not 0 <= (cv if cv is not None else -1) <= 3 or total > 10_000
            or any(value is None for value in initial.values())
            or sum(initial.values()) > 10_000):
        return {"status": "unavailable", "reason": "SLA, variabilidade, backlog inicial ou volume fora do suporte do modelo."}
    grids = defaultdict(list)
    for week in weeks:
        for row in week["skills_shifts"]:
            grids[(row["skill"], row["shift"])].append(row)
    counts = [[[] for _ in range(3)] for _ in weeks]
    sla_results = []
    service_rate = float(rate / (1 + (rework or Decimal(0))))
    horizon = len(weeks) * WEEK_HOURS
    for seed in SEEDS:
        weekly = [[0, 0, 0, 0] for _ in weeks]
        for index, (key, rows) in enumerate(sorted(grids.items())):
            arrivals, done = _simulate(rows, service_rate, cv, initial[key], seed + 10007 * index)
            cutoff = horizon - sla
            for week_index, result in enumerate(weekly):
                start = week_index * WEEK_HOURS
                end = start + WEEK_HOURS
                arrived = sum(at < end for at in arrivals)
                finished = sum(stop < end for _, stop in done)
                result[0] += arrived + round(initial[key]) - finished
                result[1] += sum(start <= stop < end for _, stop in done)
                result[2] += sum(start <= at < end and at <= cutoff for at in arrivals)
                result[3] += sum(at is not None and start <= at < end and at <= cutoff
                                 and stop - at <= sla for at, stop in done)
        eligible = sum(row[2] for row in weekly)
        if eligible:
            sla_results.append(sum(row[3] for row in weekly) / eligible)
        for bucket, (backlog, throughput, eligible, on_time) in zip(counts, weekly):
            bucket[0].append(backlog)
            bucket[1].append(throughput)
            if eligible:
                bucket[2].append(on_time / eligible)

    def summary(values):
        return {"mean": mean(values), "min": min(values), "max": max(values)} if values else None

    weekly_results = [
        {"starts": week["starts"], "backlog_end": summary(bucket[0]),
         "completed": summary(bucket[1]), "sla_fraction": summary(bucket[2])}
        for week, bucket in zip(weeks, counts)
    ]
    return {
        "status": "simulated", "runs": len(SEEDS), "seeds": list(SEEDS), "sla_hours": sla,
        "backlog_end": weekly_results[-1]["backlog_end"], "sla_fraction": summary(sla_results),
        "weeks": weekly_results,
        "assumptions": ["Chegadas Poisson por semana; serviço Gamma; capacidade comprometida distribuída no tempo.",
                        "Backlog inicial entra na fila com idade desconhecida e fica fora da medição de SLA.",
                        "Pools já compartilhados pelo CP-SAT; nenhuma capacidade extra é adicionada na fila."],
    }
