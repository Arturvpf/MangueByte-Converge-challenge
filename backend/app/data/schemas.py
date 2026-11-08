"""Validated aggregate snapshot; no person-level attributes are accepted."""
from typing import Literal
import re
from pydantic import Field, field_validator, model_validator
from backend.app.contracts.v1 import Contract, SkillCapacitySnapshot, DemandSnapshot, nonempty

class NamedItem(Contract):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    _valid = field_validator('id', 'name')(nonempty)

class Source(Contract):
    kind: Literal['manual', 'csv', 'jira', 'synthetic']
    reference: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=128)
    _valid = field_validator('reference', 'version')(nonempty)

class SnapshotData(Contract):
    team: NamedItem
    skills: list[NamedItem]
    roles: list[NamedItem]
    shifts: list[NamedItem]
    source: Source
    capacity: SkillCapacitySnapshot
    demand: DemandSnapshot

    @model_validator(mode='after')
    def consistent(self):
        c, d = self.capacity, self.demand
        for identifier in (c.tenant_id, c.team_id, c.data_snapshot_id):
            if len(identifier) > 128 or not re.fullmatch(r'[A-Za-z0-9._~-]+', identifier):
                raise ValueError('scope and snapshot IDs must be URL-safe and at most 128 characters')
        if (c.tenant_id, c.team_id, c.data_snapshot_id) != (d.tenant_id, d.team_id, d.data_snapshot_id) or self.team.id != c.team_id:
            raise ValueError('snapshot scope must match')
        for items in (self.skills, self.roles, self.shifts):
            if len({item.id for item in items}) != len(items):
                raise ValueError('duplicate catalog ID')
        skills, shifts = {x.id for x in self.skills}, {x.id for x in self.shifts}
        if any(r.skill_id not in skills or r.shift_id not in shifts for r in c.rows) or any(r.skill_id not in skills for r in d.records):
            raise ValueError('unknown skill or shift')
        return self
