"""Load synthetic policies through the lifecycle service. Nothing is inserted raw."""
import json
from pathlib import Path

from backend.app.policies.schemas import PolicyCreate
from backend.app.policies.service import approve_version, create_policy, submit_version

ROOT = Path(__file__).resolve().parents[3]
SOURCE = "SINTÉTICO — não é regra jurídica validada"


def load_synthetic(session, author, approver, tenant_id: str):
    """Create, submit and approve the synthetic catalog for one company.

    author and approver must be different RH principals of that company.
    Repeating the load reuses the idempotency key and does not add a second rule.
    """
    if author.tenant_id != tenant_id or approver.tenant_id != tenant_id or author.user_id == approver.user_id:
        raise ValueError("fixtures require two principals of the same company")
    document = json.loads((ROOT / "backend/fixtures/policies/synthetic.json").read_text(encoding="utf-8"))
    if document["source_reference"] != SOURCE:
        raise ValueError("synthetic fixture lost its marker")
    loaded = []
    for item in document["tenants"][tenant_id]:
        if item["source_kind"] != "sintetico" or item["source_reference"] != SOURCE:
            raise ValueError("synthetic fixture must stay marked as synthetic")
        policy, version = create_policy(
            session, author, PolicyCreate.model_validate(item), f"fixture-{tenant_id}-{item['rule_key']}",
        )
        if version.status == "draft":
            _, version = submit_version(session, author, version.version_id, version.revision)
            policy, version = approve_version(
                session, approver, version.version_id, version.revision, "parecer-sintetico-fixture",
            )
        loaded.append((policy, version))
    return loaded
