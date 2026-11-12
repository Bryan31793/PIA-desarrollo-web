import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.passwords import password_hasher
from app.core.roles import Role
from app.infrastructure.plans.repository import plan_repository
from app.schemas.plans import PlanPatch
from app.services.plan_service import patch_plan


@pytest.fixture
def admin_database(database):
    with psycopg.connect(database) as connection:
        connection.execute(
            (
                Path(__file__).resolve().parents[1]
                / "migrations/006_plan_price_validation_backend.sql"
            ).read_text()
        )
    return database


@pytest.fixture
def client(admin_database, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-admin-postgres-at-least-32-bytes")
    auth = importlib.import_module("app.services.auth_service")
    monkeypatch.setattr(
        auth.refresh_token_repository, "is_access_token_active", lambda jti: True
    )
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", lambda *args: None)
    with TestClient(importlib.import_module("app.main").app) as client:
        yield client


@pytest.fixture
def headers(client):
    auth = importlib.import_module("app.services.auth_service")
    token = auth.create_token("employee:1", "access", 600, role=Role.ADMIN)[0]
    return {"Authorization": f"Bearer {token}"}


def test_plan_create_patch_and_unique_conflicts(admin_database, client, headers):
    data = {"name": "Básico", "price": "350.25", "duration_days": 30}
    created = client.post("/api/plans", headers=headers, json=data)
    assert created.status_code == 201
    plan_id = created.json()["plan_id"]
    assert client.post("/api/plans", headers=headers, json=data).status_code == 409
    updated = client.patch(
        f"/api/plans/{plan_id}", headers=headers, json={"price": "450.50"}
    )
    assert updated.status_code == 200
    assert updated.json() == {**created.json(), "price": "450.50"}
    other = client.post(
        "/api/plans", headers=headers, json=data | {"name": "Anual"}
    ).json()
    assert (
        client.patch(
            f"/api/plans/{other['plan_id']}", headers=headers, json={"name": "Básico"}
        ).status_code
        == 409
    )
    with psycopg.connect(admin_database) as connection:
        row = connection.execute(
            "SELECT name, price, duration_days FROM plans WHERE plan_id = %s",
            (plan_id,),
        ).fetchone()
        assert row == ("Básico", Decimal("450.50"), 30)


def test_price_rule_is_in_backend_not_sql_check(admin_database, client, headers):
    with psycopg.connect(admin_database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM pg_constraint WHERE conrelid = 'plans'::regclass AND conname = 'plans_price_check'"
        ).fetchone() == (0,)
        # SQL directo no aplica reglas de negocio de precio; el endpoint sí.
        plan_id = connection.execute(
            "INSERT INTO plans (name, price, duration_days) VALUES ('SQL only', 0, 30) RETURNING plan_id"
        ).fetchone()[0]
    assert (
        client.post(
            "/api/plans",
            headers=headers,
            json={"name": "Invalid", "price": "0", "duration_days": 30},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/plans/{plan_id}", headers=headers, json={"price": "-1"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/plans/{plan_id}", headers=headers, json={"price": "100"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("role", ["admin", "staff"])
def test_employee_registration_persists_hash_and_can_log_in(
    admin_database, client, headers, role
):
    data = {
        "name": "Ana",
        "email": "ANA@EXAMPLE.COM",
        "password": "password123",
        "role": role,
    }
    response = client.post("/api/employees", headers=headers, json=data)
    assert response.status_code == 201
    employee_id = response.json()["employee_id"]
    assert response.json()["role"] == role
    with psycopg.connect(admin_database) as connection:
        row = connection.execute(
            "SELECT e.password_hash, e.email, r.name FROM employees e JOIN roles r USING (role_id) WHERE employee_id = %s",
            (employee_id,),
        ).fetchone()
        assert password_hasher.verify(data["password"], row[0])
        assert row[1] == "ana@example.com"
        assert row[2] == role.capitalize()
    duplicate = client.post(
        "/api/employees", headers=headers, json=data | {"email": "ana@example.com"}
    )
    assert duplicate.status_code == 409
    login = client.post(
        "/auth/employees/login",
        data={"username": "ANA@EXAMPLE.COM", "password": data["password"]},
    )
    assert login.status_code == 200
    auth = importlib.import_module("app.services.auth_service")
    claims = auth.decode_token(login.json()["access_token"])
    assert claims["sub"] == f"employee:{employee_id}"
    assert claims["role"] == role


def test_plan_patch_preserves_existing_membership_and_payment(
    admin_database, client, headers
):
    with psycopg.connect(admin_database) as connection:
        connection.execute(
            (
                Path(__file__).resolve().parents[1] / "migrations/002_cash_payments.sql"
            ).read_text()
        )
        member_id = connection.execute(
            "INSERT INTO members (name, email, password_hash) VALUES ('Ana', 'member@example.com', 'unused') RETURNING member_id"
        ).fetchone()[0]
        employee_id = connection.execute(
            "INSERT INTO employees (name, email, password_hash, role_id) SELECT 'Staff', 'staff@example.com', 'unused', role_id FROM roles WHERE name = 'Staff' RETURNING employee_id"
        ).fetchone()[0]
    plan_id = client.post(
        "/api/plans",
        headers=headers,
        json={"name": "Básico", "price": "350", "duration_days": 30},
    ).json()["plan_id"]
    auth = importlib.import_module("app.services.auth_service")
    staff_token = auth.create_token(
        f"employee:{employee_id}", "access", 600, role=Role.STAFF
    )[0]
    membership = client.post(
        "/api/memberships",
        headers={"Authorization": f"Bearer {staff_token}"},
        json={"member_id": member_id, "plan_id": plan_id},
    )
    assert membership.status_code == 201
    assert (
        client.patch(
            f"/api/plans/{plan_id}",
            headers=headers,
            json={"price": "900", "duration_days": 90},
        ).status_code
        == 200
    )
    with psycopg.connect(admin_database) as connection:
        row = connection.execute(
            "SELECT ms.start_date, ms.end_date, p.amount FROM memberships ms JOIN payments p USING (membership_id)"
        ).fetchone()
        assert row[0] == date.fromisoformat(membership.json()["start_date"])
        assert row[1] == date.fromisoformat(membership.json()["end_date"])
        assert row[2] == Decimal(350)


def test_concurrent_patches_preserve_independent_fields(admin_database):
    plan = plan_repository.create("Básico", Decimal(350), 30)
    barrier = Barrier(2)

    def update(data):
        barrier.wait(timeout=10)
        return patch_plan(plan["plan_id"], PlanPatch(**data))

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(update, [{"price": "450.25"}, {"duration_days": 90}]))
    with psycopg.connect(admin_database) as connection:
        assert connection.execute(
            "SELECT price, duration_days FROM plans WHERE plan_id = %s",
            (plan["plan_id"],),
        ).fetchone() == (Decimal("450.25"), 90)
