"""Configuration read explicitly for each application instance."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./alinia.db"
    # HMAC key for access tokens. Never committed; without it, login and
    # authenticated routes fail closed.
    auth_secret: str | None = field(default=None, repr=False)
    access_token_ttl_seconds: int = 3600
    # Read-only Jira. Empty means the live connector reports INTEGRATION_UNAVAILABLE.
    jira_base_url: str | None = None
    jira_project_key: str | None = None
    jira_api_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", cls.database_url),
            auth_secret=os.environ.get("ALINIA_AUTH_SECRET") or None,
            access_token_ttl_seconds=int(os.environ.get("ALINIA_ACCESS_TOKEN_TTL_SECONDS", "3600")),
            jira_base_url=os.environ.get("JIRA_BASE_URL") or None,
            jira_project_key=os.environ.get("JIRA_PROJECT_KEY") or None,
            jira_api_token=os.environ.get("JIRA_API_TOKEN") or None,
        )
