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

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", cls.database_url),
            auth_secret=os.environ.get("ALINIA_AUTH_SECRET") or None,
            access_token_ttl_seconds=int(os.environ.get("ALINIA_ACCESS_TOKEN_TTL_SECONDS", "3600")),
        )
