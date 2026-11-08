"""Bootstrap tenants and users. Passwords come from ALINIA_BOOTSTRAP_PASSWORD or a prompt, never argv.

python -m backend.app.auth.cli create-tenant --tenant-id X --name Y
python -m backend.app.auth.cli create-user --tenant-id X --email E --role admin [--team-id T]
"""
import argparse
from getpass import getpass
import os
import sys

from sqlalchemy.exc import IntegrityError

from backend.app.audit.log import record_event
from backend.app.audit.tracing import current_trace_id
from backend.app.auth.api import valid_email
from backend.app.auth.models import MembershipRow, Tenant, User
from backend.app.auth.passwords import hash_password
from backend.app.auth.permissions import Membership, Role, check_memberships
from backend.app.core.config import Settings
from backend.app.core.database import make_database


def read_password() -> str:
    password = os.environ.get("ALINIA_BOOTSTRAP_PASSWORD")
    if password:
        return password
    password = getpass("Password: ")
    if password != getpass("Repeat password: "):
        raise ValueError("passwords do not match")
    return password


def create_tenant(sessions, tenant_id: str, name: str) -> str:
    if not tenant_id or tenant_id != tenant_id.strip() or len(tenant_id) > 128 or not name.strip():
        raise ValueError("invalid tenant")
    with sessions() as session:
        session.add(Tenant(tenant_id=tenant_id, name=name.strip(), active=True))
        try:
            session.commit()
        except IntegrityError:
            raise ValueError("tenant already exists") from None
    return tenant_id


def create_user(sessions, tenant_id: str, email: str, role: Role, team_id: str | None, password: str) -> str:
    email = valid_email(email)
    check_memberships([Membership(role, team_id)])
    password_hash = hash_password(password)
    with sessions() as session:
        if session.get(Tenant, tenant_id) is None:
            raise ValueError("unknown tenant")
        user = User(tenant_id=tenant_id, email=email, password_hash=password_hash)
        session.add(user)
        try:
            session.flush()
        except IntegrityError:
            raise ValueError("user already exists") from None
        session.add(MembershipRow(tenant_id=tenant_id, user_id=user.user_id, role=role.value, team_id=team_id))
        record_event(session, action="admin.user.create", outcome="success", tenant_id=tenant_id, actor_type="system",
                     resource_type="user", resource_id=user.user_id,
                     details={"grants": [f"{role.value}:{team_id or '*'}"]}, trace_id=current_trace_id())
        session.commit()
        return user.user_id


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.app.auth.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    tenant = commands.add_parser("create-tenant")
    tenant.add_argument("--tenant-id", required=True)
    tenant.add_argument("--name", required=True)
    user = commands.add_parser("create-user")
    user.add_argument("--tenant-id", required=True)
    user.add_argument("--email", required=True)
    user.add_argument("--role", required=True, choices=[r.value for r in Role])
    user.add_argument("--team-id")
    args = parser.parse_args(argv)
    engine, sessions = make_database(Settings.from_env().database_url)
    try:
        if args.command == "create-tenant":
            print(create_tenant(sessions, args.tenant_id, args.name))
        else:
            print(create_user(sessions, args.tenant_id, args.email, Role(args.role), args.team_id, read_password()))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
