"""Read-only Jira client. There is no create, update, or transition call."""
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]


class IntegrationUnavailable(Exception):
    code = "INTEGRATION_UNAVAILABLE"


def load_fixture(name: str = "issues") -> dict:
    if name != "issues":
        raise IntegrationUnavailable("fixture desconhecida")
    return json.loads((ROOT / "backend/fixtures/jira/issues.json").read_text(encoding="utf-8"))


def fetch_issues(settings, transport=None) -> list[dict]:
    """GET pages only. Missing credentials stay visible and do not open a connection."""
    if not settings.jira_base_url or not settings.jira_api_token:
        raise IntegrationUnavailable("Integração Jira real pendente: credenciais não configuradas")
    transport = transport or _urllib_get
    start = 0
    collected = []
    while True:
        payload = transport(
            "GET", f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search",
            {"startAt": start, "maxResults": 50, "fields": "summary"},
            {"Authorization": f"Bearer {settings.jira_api_token}", "Accept": "application/json"},
        )
        page = payload.get("issues") or []
        collected.extend(page)
        start += len(page)
        if not page or start >= int(payload.get("total") or 0):
            return collected


def _urllib_get(method: str, url: str, params: dict, headers: dict):
    if method != "GET":
        raise IntegrationUnavailable("o conector Jira não escreve")
    request = Request(f"{url}?{urlencode(params)}", headers=headers, method="GET")
    with urlopen(request, timeout=10) as response:  # noqa: S310 — URL comes from server config, method is GET
        return json.loads(response.read().decode())
