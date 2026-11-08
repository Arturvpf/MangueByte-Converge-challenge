"""Read-only Jira client. There is no create, update, or transition call."""
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
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
    project = getattr(settings, "jira_project_key", None)
    if not project or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{1,50}", project):
        raise IntegrationUnavailable("JIRA_PROJECT_KEY ausente ou inválido; consulta ampla bloqueada")
    parsed_url = urlsplit(settings.jira_base_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname or parsed_url.username or parsed_url.password:
        raise IntegrationUnavailable("JIRA_BASE_URL exige host HTTPS sem credenciais embutidas")
    transport = transport or _urllib_get
    start = 0
    collected = []
    for _page_number in range(200):
        payload = transport(
            "GET", f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search",
            {"startAt": start, "maxResults": 50,
             "fields": "created,resolutiondate,status,issuetype,project",
             "jql": f'project = "{project}" ORDER BY created ASC'},
            {"Authorization": f"Bearer {settings.jira_api_token}", "Accept": "application/json"},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("issues"), list):
            raise IntegrationUnavailable("Resposta Jira inválida; nenhum evento persistido")
        page = payload["issues"]
        if len(page) > 50:
            raise IntegrationUnavailable("Pagina Jira acima do limite declarado")
        collected.extend(page)
        start += len(page)
        try:
            total = int(payload["total"])
        except (KeyError, TypeError, ValueError):
            raise IntegrationUnavailable("Total de resultados Jira inválido") from None
        if total < 0 or (not page and start < total):
            raise IntegrationUnavailable("Paginação Jira incompleta; nenhum evento persistido")
        if start >= total:
            return collected
    raise IntegrationUnavailable("Limite de páginas Jira atingido; nenhuma importação parcial permitida")


def _urllib_get(method: str, url: str, params: dict, headers: dict):
    if method != "GET":
        raise IntegrationUnavailable("o conector Jira não escreve")
    request = Request(f"{url}?{urlencode(params)}", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 — URL from deployment config
            return json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise IntegrationUnavailable("Falha na leitura da API Jira; nenhuma importação confirmada") from exc
