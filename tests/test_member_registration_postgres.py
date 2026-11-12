import importlib
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.services.member_service import password_hasher


def test_registration_persists_hash_and_handles_database_duplicate(
    database, monkeypatch
):
    monkeypatch.setenv(
        "JWT_SECRET", "test-secret-for-member-registration-at-least-32-bytes"
    )
    app = importlib.import_module("app.main").app
    auth = importlib.import_module("app.services.auth_service")
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", lambda *args: None)
    with TestClient(app) as client:
        data = {"name": "Ana", "email": "ana@example.com", "password": "password123"}
        response = client.post("/auth/register", json=data)
        assert response.status_code == 201
        member_id = response.json()["member_id"]
        login = client.post(
            "/auth/login",
            data={"username": "ANA@EXAMPLE.COM", "password": data["password"]},
        )
        assert login.status_code == 200
        assert login.json()["access_token"]
        assert (
            client.post(
                "/auth/login",
                data={"username": data["email"], "password": "wrong-password"},
            ).status_code
            == 401
        )
        # Nueva conexión: comprueba que el alta se confirmó, no solo se ejecutó.
        with psycopg.connect(database) as connection:
            row = connection.execute(
                "SELECT password_hash, is_active FROM members WHERE member_id = %s",
                (member_id,),
            ).fetchone()
            assert row is not None
            assert password_hasher.verify(data["password"], row[0])
            assert row[1] is True
            # Simula un correo con mayúsculas ya almacenado por otro proceso.
            connection.execute(
                "UPDATE members SET email = 'ANA@EXAMPLE.COM' WHERE member_id = %s",
                (member_id,),
            )
        duplicate = client.post("/auth/register", json=data)
        assert duplicate.status_code == 409
        with psycopg.connect(database) as connection:
            assert connection.execute("SELECT count(*) FROM members").fetchone() == (1,)
        # El error anterior no deja la conexión en una transacción fallida.
        data["email"] = "another@example.com"
        assert client.post("/auth/register", json=data).status_code == 201
        with psycopg.connect(database) as connection:
            connection.execute(
                "UPDATE members SET is_active = FALSE WHERE member_id = %s",
                (member_id,),
            )
        assert (
            client.post(
                "/auth/login",
                data={"username": "ana@example.com", "password": data["password"]},
            ).status_code
            == 401
        )


def test_employee_roles_are_immutable(database):
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations/003_immutable_employee_roles.sql"
    )
    with psycopg.connect(database) as connection:
        connection.execute(migration.read_text())
        employee_id = connection.execute(
            """
            INSERT INTO employees (name, email, password_hash, role_id)
            SELECT 'Staff', 'staff@example.com', 'unused', role_id
            FROM roles WHERE name = 'Staff'
            RETURNING employee_id
            """
        ).fetchone()[0]
        # Asignar el mismo rol o modificar otros campos sigue permitido.
        connection.execute(
            "UPDATE employees SET role_id = role_id, name = 'Updated' WHERE employee_id = %s",
            (employee_id,),
        )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                """
                UPDATE employees SET role_id = (
                    SELECT role_id FROM roles WHERE name = 'Admin'
                ) WHERE employee_id = %s
                """,
                (employee_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute("UPDATE roles SET name = 'Admin2' WHERE name = 'Staff'")
