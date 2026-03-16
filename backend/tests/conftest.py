import uuid
import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from app.core.security import get_current_user, hash_password
from app.core.config import settings
from app.db.session import get_db
from app.models.auth import PlatformRole, UserAccount
from app.main import app


def _url_to_psycopg_dsn(url: URL) -> str:
    return url.render_as_string(hide_password=False).replace("+psycopg", "")


def _create_temp_database(base_url: URL) -> tuple[str, URL]:
    db_name = f"project_tracker_test_{uuid.uuid4().hex[:8]}"
    admin_url = base_url.set(database="postgres")
    test_url = base_url.set(database=db_name)

    with psycopg.connect(_url_to_psycopg_dsn(admin_url), autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    return db_name, test_url


def _drop_temp_database(base_url: URL, db_name: str) -> None:
    admin_url = base_url.set(database="postgres")
    with psycopg.connect(_url_to_psycopg_dsn(admin_url), autocommit=True) as conn:
        conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (db_name,),
        )
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))


@pytest.fixture(scope="session")
def test_database_url() -> str:
    base_url_value = os.getenv("TEST_BASE_DATABASE_URL") or settings.database_url
    if not base_url_value:
        raise RuntimeError("Set TEST_BASE_DATABASE_URL or DATABASE_URL before running tests.")
    base_url = make_url(base_url_value)
    db_name, test_url = _create_temp_database(base_url)
    try:
        yield test_url.render_as_string(hide_password=False)
    finally:
        _drop_temp_database(base_url, db_name)


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_database_url)
    command.upgrade(alembic_cfg, "head")
    return test_database_url


@pytest.fixture
def db_engine(migrated_database: str):
    engine = create_engine(migrated_database, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(request, db_engine):
    if request.node.name == "test_migration_upgrade_downgrade_cycle":
        yield
        return
    tables = [
        "chat_action_proposals",
        "chat_messages",
        "chat_conversations",
        "project_chat_message_reactions",
        "project_chat_messages",
        "project_chat_room_members",
        "project_chat_rooms",
        "project_memberships",
        "user_accounts",
        "audit_events",
        "document_chunks",
        "project_documents",
        "deliverable_collaborators",
        "milestone_collaborators",
        "task_collaborators",
        "wp_collaborators",
        "milestone_wps",
        "deliverable_wps",
        "deliverables",
        "milestones",
        "tasks",
        "work_packages",
        "team_members",
        "partner_organizations",
        "projects",
    ]
    with db_engine.begin() as conn:
        conn.exec_driver_sql(f"TRUNCATE TABLE {', '.join(tables)} CASCADE")
    yield


@pytest.fixture
def client(db_engine):
    TestingSessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False, future=True)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_get_current_user():
        db = TestingSessionLocal()
        try:
            email = "test-admin@example.com"
            user = db.scalar(select(UserAccount).where(UserAccount.email == email))
            if not user:
                user = UserAccount(
                    email=email,
                    password_hash=hash_password("test-password-123"),
                    display_name="Test Admin",
                    platform_role=PlatformRole.super_admin.value,
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            return user
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
