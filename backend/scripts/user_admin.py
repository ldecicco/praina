#!/usr/bin/env python3

import argparse
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.auth import PlatformRole, UserAccount


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage platform admin users.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new super admin user.")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--password", required=True)
    create_parser.add_argument("--name", required=True)

    promote_parser = subparsers.add_parser("promote", help="Promote an existing user to super_admin.")
    promote_parser.add_argument("--email", required=True)

    demote_parser = subparsers.add_parser("demote", help="Demote a super admin to regular user.")
    demote_parser.add_argument("--email", required=True)

    return parser


def create_admin(email: str, password: str, name: str) -> int:
    normalized_email = email.strip().lower()
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        existing = db.scalar(select(UserAccount).where(UserAccount.email == normalized_email))
        if existing:
            print(f"User {normalized_email} already exists.", file=sys.stderr)
            return 1

        user = UserAccount(
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=name.strip(),
            platform_role=PlatformRole.super_admin.value,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    print(f"Created super_admin: {normalized_email}")
    return 0


def set_role(email: str, role: str) -> int:
    normalized_email = email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == normalized_email))
        if not user:
            print(f"User {normalized_email} not found.", file=sys.stderr)
            return 1

        user.platform_role = role
        db.commit()

    print(f"Updated {normalized_email} role to {role}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "create":
        return create_admin(args.email, args.password, args.name)
    if args.command == "promote":
        return set_role(args.email, PlatformRole.super_admin.value)
    if args.command == "demote":
        return set_role(args.email, PlatformRole.user.value)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
