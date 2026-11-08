"""Max-flow assignment of pool hours to skill/shift rows.

A finished search maximizes covered hours under the caps, so the residual is the
minimum leftover for this model. Stopping early does not prove the problem is
infeasible. The same pool hour cannot leave the pool twice.
"""
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    skill_id: str
    shift_id: str
    pool_ids: tuple[str, ...]
    eligible: int
    minimum: int = 0
    cost: int = 0


@dataclass(frozen=True)
class Allocation:
    pool_id: str
    skill_id: str
    shift_id: str
    hours: int


@dataclass(frozen=True)
class SolveResult:
    status: str
    allocations: tuple[Allocation, ...]
    residual_hours: dict[str, int]
    limitations: tuple[str, ...]
    expansions: int
    cost: int | None


def _nonneg_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _augment(residual, parent, source, sink) -> int:
    bottleneck = 10**9
    node = sink
    while node != source:
        previous = parent[node]
        bottleneck = min(bottleneck, residual[previous][node])
        node = previous
    node = sink
    while node != source:
        previous = parent[node]
        residual[previous][node] -= bottleneck
        residual[node][previous] = residual[node].get(previous, 0) + bottleneck
        node = previous
    return bottleneck


def _bfs(residual, source, sink):
    parent = {source: None}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for nxt, cap in residual.get(node, {}).items():
            if cap > 0 and nxt not in parent:
                parent[nxt] = node
                if nxt == sink:
                    return parent
                queue.append(nxt)
    return None


def _run(edges, source, sink, budget: int):
    residual: dict[str, dict[str, int]] = {}
    original: dict[tuple[str, str], int] = {}
    for left, right, cap in edges:
        residual.setdefault(left, {})
        residual.setdefault(right, {})
        residual[left][right] = residual[left].get(right, 0) + cap
        residual[right].setdefault(left, 0)
        original[(left, right)] = original.get((left, right), 0) + cap
    if source not in residual or sink not in residual:
        return {}, 0, True
    expansions = 0
    complete = True
    while True:
        if expansions >= budget:
            complete = False
            break
        parent = _bfs(residual, source, sink)
        expansions += 1
        if parent is None:
            break
        _augment(residual, parent, source, sink)
    flows = {}
    for (left, right), cap in original.items():
        sent = cap - residual[left][right]
        if sent > 0:
            flows[(left, right)] = sent
    return flows, expansions, complete


def _connections(pools, rows, max_total):
    edges = []
    origin = "gate" if max_total is not None else "source"
    if max_total is not None:
        edges.append(("source", "gate", max_total))
    for pool_id, hours in pools.items():
        edges.append((origin, f"pool:{pool_id}", hours))
        for index, row in enumerate(rows):
            if pool_id in row.pool_ids:
                edges.append((f"pool:{pool_id}", f"row:{index}", hours))
    return edges


def solve(pools: dict[str, int], rows: list[Row], demand: dict[str, int], *,
          max_total_hours: int | None = None, max_expansions: int = 100000) -> SolveResult:
    skills = sorted(set(demand) | {row.skill_id for row in rows})
    blank = {skill: demand.get(skill, 0) for skill in skills}
    if (not _nonneg_int(max_expansions) or
            any(not _nonneg_int(hours) for hours in pools.values()) or
            any(not _nonneg_int(hours) for hours in demand.values()) or
            (max_total_hours is not None and not _nonneg_int(max_total_hours)) or
            any(not _nonneg_int(row.eligible) or not _nonneg_int(row.minimum) or not _nonneg_int(row.cost) for row in rows)):
        return SolveResult("unknown", (), blank, ("entrada do solver não é um inteiro não negativo",), 0, None)
    if any(row.minimum > row.eligible for row in rows):
        return SolveResult("infeasible", (), blank, ("mínimo da linha supera o teto da linha",), 0, None)

    minimum_total = sum(row.minimum for row in rows)
    spent = 0
    minimum_flow = {}
    if minimum_total:
        edges = _connections(pools, rows, max_total_hours)
        for index, row in enumerate(rows):
            if row.minimum:
                edges.append((f"row:{index}", "sink", row.minimum))
        minimum_flow, used, done = _run(edges, "source", "sink", max_expansions)
        spent += used
        placed = sum(hours for (left, right), hours in minimum_flow.items() if right == "sink")
        if not done:
            return SolveResult("unknown", (), blank,
                               ("busca interrompida antes de provar se os mínimos cabem; timeout não é inviabilidade",), spent, None)
        if placed < minimum_total:
            return SolveResult("infeasible", (), blank, ("os mínimos obrigatórios não cabem nos pools",), spent, None)

    remaining_pools = dict(pools)
    remaining_eligible = [row.eligible for row in rows]
    covered = {skill: 0 for skill in skills}
    for (left, right), hours in minimum_flow.items():
        if left.startswith("pool:") and right.startswith("row:"):
            index = int(right.split(":", 1)[1])
            pool_id = left.split(":", 1)[1]
            remaining_pools[pool_id] -= hours
            remaining_eligible[index] -= hours
            covered[rows[index].skill_id] += hours
    if any(hours < 0 for hours in remaining_pools.values()) or any(hours < 0 for hours in remaining_eligible):
        return SolveResult("infeasible", (), blank, ("mínimo inconsistente com o teto",), spent, None)

    remaining_demand = {skill: max(demand.get(skill, 0) - covered.get(skill, 0), 0) for skill in skills}
    extra_flow = {}
    done = True
    if max_total_hours is not None:
        max_total_hours -= sum(covered.values())
    if sum(remaining_demand.values()) and any(remaining_pools.values()):
        edges = _connections(remaining_pools, rows, max_total_hours)
        for index, row in enumerate(rows):
            if remaining_eligible[index] > 0:
                edges.append((f"row:{index}", f"skill:{row.skill_id}", remaining_eligible[index]))
        for skill, hours in remaining_demand.items():
            if hours:
                edges.append((f"skill:{skill}", "sink", hours))
        extra_flow, used, done = _run(edges, "source", "sink", max(max_expansions - spent, 0))
        spent += used

    assigned = {}
    for (left, right), hours in list(minimum_flow.items()) + list(extra_flow.items()):
        if left.startswith("pool:") and right.startswith("row:"):
            assigned[(left, right)] = assigned.get((left, right), 0) + hours

    allocations = []
    cost = 0
    for (left, right), hours in sorted(assigned.items()):
        index = int(right.split(":", 1)[1])
        row = rows[index]
        pool_id = left.split(":", 1)[1]
        allocations.append(Allocation(pool_id, row.skill_id, row.shift_id, hours))
        cost += hours * row.cost
    residual = {skill: max(demand.get(skill, 0) - covered.get(skill, 0), 0) for skill in skills}
    # Recompute covered from allocations so minimums are not dropped.
    covered = {skill: 0 for skill in skills}
    for item in allocations:
        covered[item.skill_id] += item.hours
    residual = {skill: max(demand.get(skill, 0) - covered.get(skill, 0), 0) for skill in skills}
    pool_used = {pool_id: 0 for pool_id in pools}
    for item in allocations:
        pool_used[item.pool_id] += item.hours
    if any(pool_used[pool_id] > hours for pool_id, hours in pools.items()):
        return SolveResult("unknown", (), blank, ("fluxo excedeu um pool; resultado descartado",), spent, None)
    if not done:
        if not allocations:
            return SolveResult("unknown", (), residual,
                               ("busca interrompida sem solução; timeout não prova inviabilidade",), spent, None)
        return SolveResult("feasible", tuple(allocations), residual,
                           ("busca interrompida com alocação parcial; otimalidade não comprovada; timeout não prova inviabilidade",),
                           spent, cost)
    note = ()
    if any(covered[skill] > demand.get(skill, 0) for skill in skills):
        note = ("parte da alocação cobre mínimo obrigatório acima da demanda",)
    return SolveResult("optimal", tuple(allocations), residual, note, spent, cost)
