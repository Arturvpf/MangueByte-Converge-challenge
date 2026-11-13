"""Poll the scoped Jira integration through the authenticated Alinia API."""
import argparse
import os
from time import sleep
from urllib.parse import urlsplit

import httpx


def _authorization(client, base, token, email, password, tenant):
    if token:
        return {"Authorization": f"Bearer {token}"}
    response = client.post(f"{base}/api/auth/login", json={"email": email, "password": password, "tenant_id": tenant})
    response.raise_for_status()
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=int, default=0, help="0 runs one cycle; recurring intervals start at 300")
    args = parser.parse_args()
    if args.interval_seconds != 0 and args.interval_seconds < 300:
        parser.error("interval must be 0 or at least 300 seconds")
    token = os.environ.get("ALINIA_JIRA_WORKER_TOKEN")
    email = os.environ.get("ALINIA_JIRA_WORKER_EMAIL")
    password = os.environ.get("ALINIA_JIRA_WORKER_PASSWORD")
    tenant = os.environ.get("ALINIA_JIRA_TENANT_ID")
    if not token and not all((email, password, tenant)):
        parser.error("configure o token da API ou a conta de serviço Jira")
    base = os.environ.get("ALINIA_JIRA_API_BASE", "http://127.0.0.1:8000").rstrip("/")
    url = urlsplit(base)
    if (not url.hostname or url.username or url.password or url.query or url.fragment
            or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost", "::1"}))):
        parser.error("a API deve usar HTTPS ou HTTP em loopback")
    with httpx.Client(timeout=90) as client:
        while True:
            try:
                headers = _authorization(client, base, token, email, password, tenant)
                response = client.post(f"{base}/api/imports/jira/sync", headers=headers)
                response.raise_for_status()
                print(response.json()["status"], flush=True)
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if not args.interval_seconds or status in {401, 403}:
                    raise SystemExit(f"Coleta Jira falhou: HTTP {status}") from None
                print(f"Coleta Jira falhou: HTTP {status}", flush=True)
            except httpx.RequestError:
                if not args.interval_seconds:
                    raise SystemExit("API Alinia indisponível") from None
                print("API Alinia indisponível", flush=True)
            if not args.interval_seconds:
                return
            sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
