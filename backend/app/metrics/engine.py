"""Pure P1 metrics and shared-pool solver input preparation."""
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext, ROUND_HALF_EVEN
from fractions import Fraction

from ..contracts.v1 import DemandSnapshot, SkillCapacitySnapshot, ErrorCode


class MetricsError(ValueError):
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        super().__init__(message)


def number(value, name):
    if value is None or isinstance(value, bool):
        raise MetricsError(ErrorCode.INSUFFICIENT_DATA, f'{name} is required')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise MetricsError(ErrorCode.INSUFFICIENT_DATA, f'{name} must be numeric') from None
    if not result.is_finite() or result < 0:
        raise MetricsError(ErrorCode.INSUFFICIENT_DATA, f'{name} must be finite and nonnegative')
    return result


def exact_decimal(value: Fraction) -> Decimal:
    """Convert a finite decimal fraction without consulting Decimal context."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError('fraction does not have a finite decimal representation')
    scale = max(twos, fives)
    coefficient = abs(value.numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = tuple(int(digit) for digit in str(coefficient))
    return Decimal((int(value < 0), digits, -scale))


def ratio(numerator: Fraction, denominator: Fraction) -> Decimal:
    """Stable rounded ratio; all inputs and decision calculations remain exact."""
    value = numerator / denominator
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN, Emax=999999999, Emin=-999999999)):
        return Decimal(value.numerator) / Decimal(value.denominator)


@dataclass(frozen=True)
class HomogeneousMetrics:
    effective_hours: Decimal
    effective_availability: Decimal | None
    capacity_cases: Decimal
    ipd: Decimal | None
    fte: Decimal | None
    overtime_fte: Decimal | None
    required_headcount: int | None
    headcount_gap: int | None


_SAME_DEMAND = object()


def homogeneous_metrics(*, headcount, nominal_hours_per_person, availability, cases_per_hour,
                        demand_cases, projected_demand_cases=_SAME_DEMAND, overtime_effective_hours=0,
                        hours_unit='hours_per_period', demand_unit='cases_per_period',
                        productivity_unit='cases_per_hour'):
    """Calculate a homogeneous group; overtime hours are already effective.

    IPD = demand/capacity. FTE = total effective hours/nominal hours per person.
    The required headcount excludes overtime, which cannot be assumed for future staff.
    """
    if (hours_unit, demand_unit, productivity_unit) != ('hours_per_period', 'cases_per_period', 'cases_per_hour'):
        raise MetricsError(ErrorCode.UNIT_MISMATCH, 'incompatible units')
    h = number(headcount, 'headcount')
    if h != h.to_integral_value():
        raise MetricsError(ErrorCode.INSUFFICIENT_DATA, 'headcount must be an integer')
    nominal = number(nominal_hours_per_person, 'nominal_hours_per_person')
    availability = number(availability, 'availability')
    if availability > 1:
        raise MetricsError(ErrorCode.INSUFFICIENT_DATA, 'availability must be between 0 and 1')
    rate = number(cases_per_hour, 'cases_per_hour')
    demand = number(demand_cases, 'demand_cases')
    projected = demand if projected_demand_cases is _SAME_DEMAND else number(projected_demand_cases, 'projected_demand_cases')
    overtime = number(overtime_effective_hours, 'overtime_effective_hours')
    h, nominal, availability, rate, demand, projected, overtime = map(
        Fraction, (h, nominal, availability, rate, demand, projected, overtime))
    base = h * nominal
    effective = base * availability + overtime
    capacity = effective * rate
    per_person = nominal * availability * rate
    required = ((projected / per_person).__ceil__()
                if per_person else (0 if not projected else None))
    return HomogeneousMetrics(
        exact_decimal(effective), exact_decimal(availability) if base else None,
        exact_decimal(capacity), ratio(demand, capacity) if capacity else None,
        ratio(effective, nominal) if nominal else None,
        ratio(overtime, nominal) if nominal else None,
        required, max(required - int(h), 0) if required is not None else None,
    )


@dataclass(frozen=True)
class Pool:
    pool_id: str
    available_hours: Decimal | None


@dataclass(frozen=True)
class Row:
    skill_id: str
    shift_id: str
    pool_ids: tuple[str, ...]
    eligible_hours: Decimal | None
    availability_fraction: Decimal | None


@dataclass(frozen=True)
class Matrix:
    tenant_id: str
    team_id: str
    data_snapshot_id: str
    period: object
    hours_unit: str
    pools: tuple[Pool, ...]
    rows: tuple[Row, ...]
    demand: tuple[tuple[str, Decimal | None], ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class Allocation:
    pool_id: str
    skill_id: str
    shift_id: str
    hours: Decimal


def optional_number(value, name):
    return None if value is None else number(value, name)


def prepare_matrix(capacity: SkillCapacitySnapshot, demand: DemandSnapshot) -> Matrix:
    # Revalidate to catch mutated Pydantic models and invalid model_construct instances.
    capacity = SkillCapacitySnapshot.model_validate(capacity.model_dump())
    demand = DemandSnapshot.model_validate(demand.model_dump())
    if (capacity.tenant_id, capacity.team_id, capacity.data_snapshot_id) != (demand.tenant_id, demand.team_id, demand.data_snapshot_id):
        raise MetricsError(ErrorCode.FORBIDDEN_SCOPE, 'capacity and demand scope/snapshot differ')
    if capacity.hours_unit != 'hours_per_period' or any(r.unit != 'cases_per_period' for r in demand.records):
        raise MetricsError(ErrorCode.UNIT_MISMATCH, 'incompatible units')
    if any(r.period != capacity.period for r in demand.records):
        raise MetricsError(ErrorCode.UNIT_MISMATCH, 'demand and capacity periods differ')
    pools = tuple(Pool(p.pool_id, optional_number(p.available_hours, 'pool hours')) for p in capacity.pools)
    rows = tuple(Row(r.skill_id, r.shift_id, tuple(r.pool_ids), optional_number(r.eligible_hours, 'eligible hours'), optional_number(r.availability_fraction, 'availability')) for r in capacity.rows)
    return Matrix(capacity.tenant_id, capacity.team_id, capacity.data_snapshot_id, capacity.period.model_copy(deep=True), capacity.hours_unit, pools, rows,
                  tuple((r.skill_id, optional_number(r.quantity, 'demand')) for r in demand.records),
                  tuple(capacity.limitations + demand.limitations))


def validate_allocations(matrix: Matrix, allocations: list[Allocation]) -> None:
    """Validate an externally proposed allocation, not solver feasibility or coverage."""
    pools = {p.pool_id: p for p in matrix.pools}
    rows = {(r.skill_id, r.shift_id): r for r in matrix.rows}
    pool_totals = {key: Fraction(0) for key in pools}
    row_totals = {key: Fraction(0) for key in rows}
    seen = set()
    for a in allocations:
        key = (a.skill_id, a.shift_id)
        triple = (a.pool_id, *key)
        if triple in seen or key not in rows or a.pool_id not in rows[key].pool_ids:
            raise MetricsError(ErrorCode.INSUFFICIENT_DATA, 'duplicate or ineligible allocation')
        seen.add(triple)
        amount = Fraction(number(a.hours, 'allocation hours'))
        if pools[a.pool_id].available_hours is None or rows[key].eligible_hours is None:
            raise MetricsError(ErrorCode.INSUFFICIENT_DATA, 'allocation uses unknown limit')
        pool_totals[a.pool_id] += amount
        row_totals[key] += amount
    if any(pool_totals[k] > pools[k].available_hours for k in pool_totals if pools[k].available_hours is not None):
        raise MetricsError(ErrorCode.INSUFFICIENT_DATA, 'allocation exceeds pool budget')
    if any(row_totals[k] > rows[k].eligible_hours for k in row_totals if rows[k].eligible_hours is not None):
        raise MetricsError(ErrorCode.INSUFFICIENT_DATA, 'allocation exceeds row limit')

