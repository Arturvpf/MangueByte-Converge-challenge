"""Configuration read explicitly for each application instance."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./alinia.db"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(database_url=os.environ.get("DATABASE_URL", cls.database_url))
