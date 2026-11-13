"""Run one authorized polling cycle (schedule this command with your job runner)."""
import os

import httpx


def main():
    token = os.environ.get("ALINIA_JIRA_WORKER_TOKEN")
    if not token:
        raise SystemExit("ALINIA_JIRA_WORKER_TOKEN ausente")
    base = os.environ.get("ALINIA_JIRA_API_BASE", "http://127.0.0.1:8000").rstrip("/")
    with httpx.Client(timeout=90) as client:
        response = client.post(f"{base}/api/imports/jira/sync", headers={"Authorization": f"Bearer {token}"})
        if not response.is_success:
            raise SystemExit(f"Coleta Jira falhou: HTTP {response.status_code}")
        print(response.json()["status"])


if __name__ == "__main__":
    main()
