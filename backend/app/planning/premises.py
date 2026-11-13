"""RH-reviewed, bounded inputs for exploratory re-planning."""
from typing import Literal

from pydantic import Field, model_validator

from backend.app.contracts.v1 import Contract


class MobilityPremise(Contract):
    kind: Literal["reallocate", "redesign"]
    pool_id: str = Field(min_length=1, max_length=128)
    target_skill: str = Field(min_length=1, max_length=128)
    target_shift: str = Field(min_length=1, max_length=128)
    transition_weeks: int = Field(ge=1, le=12)
    training_and_mentoring_hours_per_week: int = Field(ge=0, le=10_000)
    transferable_hours_per_week: int = Field(ge=1, le=10_000)
    cost_min_brl: float | None = Field(default=None, ge=0, le=1_000_000)
    cost_max_brl: float | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def ordered_cost(self):
        if ((self.cost_min_brl is None) != (self.cost_max_brl is None)
                or (self.cost_min_brl is not None and self.cost_min_brl > self.cost_max_brl)):
            raise ValueError("mobility cost needs two ordered bounds or no bounds")
        return self


class PlanningPremises(Contract):
    hiring_budget_brl: float | None = Field(default=None, ge=0, le=1_000_000_000)
    mobility: list[MobilityPremise] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def unique_pool_transitions(self):
        mobility = self.mobility or []
        keys = {(item.kind, item.pool_id) for item in mobility}
        if len(keys) != len(mobility):
            raise ValueError("duplicate mobility premise for a pool and scenario")
        return self

    def applies_to(self, snapshot):
        pools = {pool.pool_id: pool.available_hours for pool in snapshot.capacity.pools}
        matrix = {(row.skill_id, row.shift_id): row for row in snapshot.capacity.rows}
        for item in self.mobility or []:
            target = (item.target_skill, item.target_shift)
            hours = pools.get(item.pool_id)
            if hours is None or target not in matrix or max(item.transferable_hours_per_week,
                                                             item.training_and_mentoring_hours_per_week) > hours:
                return False
            sources = [key for key, row in matrix.items() if item.pool_id in row.pool_ids]
            if target in sources:
                return False
            if item.kind == "reallocate" and not any(shift == item.target_shift for _, shift in sources):
                return False
            if item.kind == "redesign" and not any(skill == item.target_skill for skill, _ in sources):
                return False
        return True
