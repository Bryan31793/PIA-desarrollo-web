import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from dotenv import dotenv_values
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app.infrastructure.database import db


def pytest_configure() -> None:
    """Carga solo la URL de pruebas local; el entorno exportado tiene prioridad."""
    if "TEST_DATABASE_URL" not in os.environ:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        database_url = dotenv_values(env_path).get("TEST_DATABASE_URL")
        if database_url:
            os.environ["TEST_DATABASE_URL"] = database_url


@pytest.fixture(autouse=True)
def isolate_database_pool(request, monkeypatch):
    """Las pruebas unitarias no abren pools reales ni reutilizan DSNs de otros tests."""
    db.close_pool()
    if "database" not in request.fixturenames:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    for name in ("DB_POOL_MIN_SIZE", "DB_POOL_MAX_SIZE", "DB_POOL_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    try:
        yield
    finally:
        db.close_pool()


@pytest.fixture
def database(monkeypatch):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    schema = "test_registration_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        # La extensión pertenece a la base; se usa la instalada por 001_init.sql.
        if not admin.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'citext'"
        ).fetchone():
            pytest.skip("Apply 001_init.sql to the test database first")
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            isolated_url = make_conninfo(
                database_url, options=f"-csearch_path={schema},public"
            )
            monkeypatch.setenv("DATABASE_URL", isolated_url)
            with psycopg.connect(isolated_url) as connection:
                migration = (
                    Path(__file__).resolve().parents[1] / "migrations/001_init.sql"
                )
                connection.execute(migration.read_text())
            db.open_pool()
            yield isolated_url
        finally:
            db.close_pool()
            admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
