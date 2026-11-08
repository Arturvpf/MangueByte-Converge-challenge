"""Smoke contract for the redesigned UI served by FastAPI.

This verifies same-origin assets, API authorization and the DOM hooks consumed
by app.js. It is NOT a headless-browser test and does not prove visual behavior.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


class AttributeCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attributes = set()

    def handle_starttag(self, tag, attrs):
        self.attributes.update(name for name, value in attrs)


def test_redesigned_frontend_same_origin_and_dom_contract():
    app = create_app(Settings("sqlite://", auth_secret="s" * 40))
    with TestClient(app) as client:
        page = client.get("/prototype/app/")
        script = client.get("/prototype/app/app.js")
        styles = client.get("/prototype/app/app.css")
        assert page.status_code == script.status_code == styles.status_code == 200
        assert "Plataforma" in page.text
        assert 'src="app.js"' in page.text
        assert "data-connect-dialog" in page.text
        assert "data-decision-form" in page.text
        assert client.get("/health").json()["status"] == "ok"
        # Protected API resources must not become public when UI assets are served.
        assert client.get("/api/teams").status_code == 401
        assert client.get("/api/investigations").status_code == 401

    collector = AttributeCollector()
    collector.feed(page.text)
    hooks = set(re.findall(r"\\[data-([a-z][a-z-]+)", script.text))
    missing = sorted("data-" + hook for hook in hooks if "data-" + hook not in collector.attributes)
    assert not missing, "JS selectors missing from redesigned HTML: " + ", ".join(missing)
    assert "api('/api/auth/login'" in script.text
    assert "api('/api/investigations')" in script.text
    assert "api('/api/teams')" in script.text
    assert "scenario.conclusive === true && validation(scenario).ok" in script.text
    assert "function resetLoadedInvestigation()" in script.text
    assert "localStorage" not in script.text and "sessionStorage" not in script.text
