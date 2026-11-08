"""Rule catalog: key, category, and parameter shape. No legal limits live here."""
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, field_validator

from backend.app.contracts.v1 import Contract


class UnknownRuleKey(ValueError):
    def __init__(self, rule_key: str):
        self.rule_key = rule_key
        super().__init__(f"unknown rule_key: {rule_key}")


def _hours(value: object) -> Decimal:
    """Integer or decimal string only. Floats are rejected so a binary fraction cannot become a stored limit."""
    if isinstance(value, bool) or type(value) is float:
        raise ValueError("hours must be an integer or a decimal string")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str):
        if not value or value != value.strip():
            raise ValueError("hours must be an integer or a decimal string")
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            raise ValueError("hours must be an integer or a decimal string") from None
    else:
        raise ValueError("hours must be an integer or a decimal string")
    if not parsed.is_finite():
        raise ValueError("hours must be finite")
    return parsed


Hours = Annotated[Decimal, BeforeValidator(_hours, json_schema_input_type=str | int), Field(gt=0)]
ModalityName = Literal["indeterminado", "temporario", "determinado", "intermitente", "estagio", "aprendiz"]


class WorkweekMaxHours(Contract):
    max_hours: Hours


class WorkdayMaxHours(Contract):
    max_hours: Hours
    requires_collective_agreement: bool


class WeeklyRest(Contract):
    min_days: int = Field(ge=1, le=7)


class ContractModality(Contract):
    modality: ModalityName
    allowed: bool
    max_duration_days: int | None
    requires_legal_review: bool

    @field_validator("max_duration_days")
    @classmethod
    def positive_duration(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("max_duration_days must be a positive integer or null")
        return value


class InternshipCapacity(Contract):
    allowed: bool


RuleParameters = WorkweekMaxHours | WorkdayMaxHours | WeeklyRest | ContractModality | InternshipCapacity

# category, parameter schema. Adding a key extends the catalog; it does not supply a limit.
CATALOG: dict[str, tuple[str, type[Contract]]] = {
    "workweek.max_hours": ("jornada", WorkweekMaxHours),
    "workday.max_hours": ("jornada", WorkdayMaxHours),
    "rest.weekly_min_days": ("repouso", WeeklyRest),
    "contract.modality": ("modalidade_contratual", ContractModality),
    "internship.counts_as_capacity": ("estagio_aprendizagem", InternshipCapacity),
}


def _entry(rule_key: str) -> tuple[str, type[Contract]]:
    try:
        return CATALOG[rule_key]
    except KeyError:
        raise UnknownRuleKey(rule_key) from None


def category_for(rule_key: str) -> str:
    return _entry(rule_key)[0]


def parameter_model(rule_key: str) -> type[Contract]:
    return _entry(rule_key)[1]


def validate_parameters(rule_key: str, parameters: object) -> Contract:
    return parameter_model(rule_key).model_validate(parameters)
