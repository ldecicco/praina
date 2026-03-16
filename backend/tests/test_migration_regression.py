import os
import uuid
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings


def _dsn_for_psycopg(url_text: str) -> str:
    return url_text.replace("+psycopg", "")


def test_migration_upgrade_downgrade_cycle():
    base_url = os.getenv("TEST_BASE_DATABASE_URL") or settings.database_url
    assert base_url, "Set TEST_BASE_DATABASE_URL or DATABASE_URL before running tests."

    parsed = make_url(base_url)
    db_name = f"project_tracker_mig_{uuid.uuid4().hex[:8]}"
    admin_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    test_db_url = parsed.set(database=db_name).render_as_string(hide_password=False)

    backend_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    with psycopg.connect(_dsn_for_psycopg(admin_url), autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    try:
        command.upgrade(alembic_cfg, "head")
        engine = create_engine(test_db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT to_regclass('public.projects')")).scalar()
            assert result == "projects"
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")
    finally:
        with psycopg.connect(_dsn_for_psycopg(admin_url), autocommit=True) as conn:
            conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (db_name,),
            )
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))

