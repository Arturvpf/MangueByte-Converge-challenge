"""Read-only Jira client. There is no create, update, or transition call."""
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[3]


class IntegrationUnavailable(Exception):
    code = "INTEGRATION_UNAVAILABLE"


def load_fixture(name: str = "issues") -> dict:
    if name != "issues":
        raise IntegrationUnavailable("fixture desconhecida")
    return json.loads((ROOT / "backend/fixtures/jira/issues.json").read_text(encoding="utf-8"))


def fetch_issues(settings, transport=None, *, created_from=None, created_to=None) -> list[dict]:
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
    if parsed_url.query or parsed_url.fragment:
        raise IntegrationUnavailable("JIRA_BASE_URL inválida")
    jql = f'project = "{project}"'
    if created_from is not None and created_to is not None:
        jql += f' AND created >= "{created_from}" AND created < "{created_to}"'
    token = None
    seen = set()
    collected = []
    for _page_number in range(200):
        params = {"maxResults": 50, "fields": "created,issuetype,project",
                  "jql": jql + " ORDER BY created ASC, key ASC"}
        if token:
            params["nextPageToken"] = token
        payload = transport(
            "GET", f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql", params,
            {"Authorization": f"Bearer {settings.jira_api_token}", "Accept": "application/json"},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("issues"), list):
            raise IntegrationUnavailable("Resposta Jira inválida; nenhum evento persistido")
        page = payload["issues"]
        if len(page) > 50:
            raise IntegrationUnavailable("Página Jira acima do limite declarado")
        collected.extend(page)
        if payload.get("isLast") is True:
            return collected
        token = payload.get("nextPageToken")
        if not isinstance(token, str) or not token or token in seen:
            raise IntegrationUnavailable("Paginação Jira incompleta; nenhum evento persistido")
        seen.add(token)
    raise IntegrationUnavailable("Limite de páginas Jira atingido; nenhuma importação parcial permitida")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_get(method: str, url: str, params: dict, headers: dict):
    if method != "GET":
        raise IntegrationUnavailable("o conector Jira não escreve")
    request = Request(f"{url}?{urlencode(params)}", headers=headers, method="GET")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=10) as response:  # noqa: S310 — URL from deployment config
            return json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise IntegrationUnavailable("Falha na leitura da API Jira; nenhuma importação confirmada") from exc
