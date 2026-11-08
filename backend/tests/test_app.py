import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.app.core.config import Settings
from backend.app.core.modules import DomainModule, JobDefinition
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_empty_database_migrates(tmp_path):
    db = tmp_path / "empty.db"
    url = f"sqlite:///{db.as_posix()}"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
                   cwd=ROOT, env=env, check=True)
    engine = create_engine(url)
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar_one() == ScriptDirectory.from_config(Config(str(ROOT / "backend/alembic.ini"))).get_current_head()
    engine.dispose()


def test_health_openapi_and_isolated_registration(tmp_path):
    calls = []
    router = APIRouter()

    @router.get("/example")
    def example():
        return {"example": True}

    module = DomainModule((router,), (JobDefinition("example", lambda: calls.append(True)),))
    a = create_app(Settings(f"sqlite:///{(tmp_path / 'a.db').as_posix()}"), (module,))
    b = create_app(Settings(f"sqlite:///{(tmp_path / 'b.db').as_posix()}"), ())
    with TestClient(a) as first, TestClient(b) as second:
        assert first.get("/health").json() == {"status": "ok"}
        assert "/health" in first.get("/openapi.json").json()["paths"]
        assert first.get("/example").json() == {"example": True}
        assert second.get("/example").status_code == 404
        assert a.state.engine is not b.state.engine
        assert "example" in a.state.jobs and not b.state.jobs
        assert not calls
