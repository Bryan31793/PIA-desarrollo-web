"""Backend temporal para E2E del cliente; solo usa TEST_DATABASE_URL y esquema aislado."""

import os
import sys
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

import psycopg
import uvicorn
from dotenv import dotenv_values
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    config = dotenv_values(ROOT / ".env")
    database_url = os.getenv("TEST_DATABASE_URL") or config.get("TEST_DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Configure TEST_DATABASE_URL to start the isolated E2E backend"
        )
    schema = "client_e2e_" + uuid4().hex
    redis_url = os.getenv("E2E_REDIS_URL", "redis://127.0.0.1:6379/15")
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        repository = None
        try:
            isolated_url = make_conninfo(
                database_url, options=f"-csearch_path={schema},public"
            )
            os.environ["DATABASE_URL"] = isolated_url
            os.environ["REDIS_URL"] = redis_url
            os.environ["JWT_SECRET"] = token_urlsafe(48)
            with psycopg.connect(isolated_url, autocommit=True) as connection:
                for migration in sorted((ROOT / "migrations").glob("[0-9]*.sql")):
                    connection.execute(migration.read_text())
                from app.core.passwords import password_hasher

                password_hash = password_hasher.hash("Client-Test-1234")
                for role, email in [
                    ("Admin", "e2e-admin@example.com"),
                    ("Staff", "e2e-staff@example.com"),
                ]:
                    connection.execute(
                        """
                        INSERT INTO employees (name, email, password_hash, role_id)
                        SELECT %s, %s, %s, role_id FROM roles WHERE name = %s
                        """,
                        (role + " E2E", email, password_hash, role),
                    )
            from app.infrastructure.auth.repository import refresh_token_repository

            repository = refresh_token_repository
            # Aísla únicamente las claves de esta ejecución, sin limpiar bases Redis completas.
            repository._access_key = lambda token_id: f"{schema}:access:{token_id}"
            repository._refresh_key = lambda token_id: f"{schema}:refresh:{token_id}"
            uvicorn.run(
                "app.main:app", host="127.0.0.1", port=8001, log_level="warning"
            )
        finally:
            from app.infrastructure.database.db import close_pool

            close_pool()
            try:
                if repository is not None:
                    keys = list(repository._client.scan_iter(match=f"{schema}:*"))
                    if keys:
                        repository._client.delete(*keys)
                    repository._client.close()
            finally:
                admin.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
                )


if __name__ == "__main__":
    main()
