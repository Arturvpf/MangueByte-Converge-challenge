"""Shared errors for the pilot flow. Permission denials still go through deny()."""


class FlowError(Exception):
    def __init__(self, status: int, code: str, team_id: str | None = None):
        self.status = status
        self.code = code
        self.team_id = team_id
        super().__init__(code)
