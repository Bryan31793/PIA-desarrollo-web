import importlib
from datetime import date
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import StorageUnavailableError
from app.core.roles import Role
from app.infrastructure.memberships.repository import membership_repository
from app.services import membership_service


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET", "test-secret-for-membership-status-at-least-32-bytes"
    )
    auth = importlib.import_module("app.services.auth_service")
    monkeypatch.setattr(
        auth.refresh_token_repository, "is_access_token_active", lambda jti: True
    )
    monkeypatch.setattr(
        membership_service, "get_membership_start_date", lambda: date(2026, 1, 15)
    )
    return auth


@pytest.fixture
def client(auth):
    with TestClient(importlib.import_module("app.main").app) as client:
        yield client


@pytest.fixture
def headers(auth):
    token = auth.create_token("member:42", "access", 600, role=Role.MEMBER)[0]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def find(monkeypatch):
    find = MagicMock(
        return_value={
            "member_id": 42,
            "membership_id": 1,
            "plan_id": 7,
            "plan_name": "Plan Básico",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 31),
        }
    )
    monkeypatch.setattr(membership_repository, "find_current_by_member_id", find)
    return find


def test_member_sees_own_current_plan(client, headers, find):
    response = client.get("/api/memberships/me?member_id=99", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "has_active_plan": True,
        "membership": {
            "membership_id": 1,
            "plan_id": 7,
            "plan_name": "Plan Básico",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
    }
    find.assert_called_once_with(42, date(2026, 1, 15))


def test_member_without_current_plan_has_normal_response(client, headers, find):
    find.return_value = {"member_id": 42, "membership_id": None}
    response = client.get("/api/memberships/me", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"has_active_plan": False, "membership": None}


def test_deleted_member_returns_not_found(client, headers, find):
    find.return_value = None
    response = client.get("/api/memberships/me", headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Member not found"}


@pytest.mark.parametrize("role", [Role.ADMIN, Role.STAFF])
def test_employees_cannot_use_member_status(client, auth, find, role):
    token = auth.create_token("employee:42", "access", 600, role=role)[0]
    assert (
        client.get(
            "/api/memberships/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 403
    )
    find.assert_not_called()


@pytest.mark.parametrize(
    "kind", ["missing", "invalid", "expired", "refresh", "revoked"]
)
def test_status_requires_valid_access_token(client, auth, monkeypatch, find, kind):
    token = "invalid"
    if kind in {"expired", "revoked"}:
        token = auth.create_token(
            "member:42", "access", -1 if kind == "expired" else 600, role=Role.MEMBER
        )[0]
    elif kind == "refresh":
        token = auth.create_token("member:42", "refresh", 600)[0]
    if kind == "revoked":
        monkeypatch.setattr(
            auth.refresh_token_repository, "is_access_token_active", lambda jti: False
        )
    headers = {} if kind == "missing" else {"Authorization": f"Bearer {token}"}
    assert client.get("/api/memberships/me", headers=headers).status_code == 401
    find.assert_not_called()


def test_status_reports_storage_unavailable(client, headers, find):
    find.side_effect = StorageUnavailableError()
    response = client.get("/api/memberships/me", headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "Storage is temporarily unavailable"}


@pytest.mark.parametrize(
    "today,active",
    [
        (date(2025, 12, 31), False),
        (date(2026, 1, 1), True),
        (date(2026, 1, 15), True),
        (date(2026, 1, 31), True),
        (date(2026, 2, 1), False),
    ],
)
def test_status_postgres_inclusive_dates_and_account_isolation(
    database, client, auth, monkeypatch, today, active
):
    with psycopg.connect(database) as connection:
        own_id = connection.execute(
            "INSERT INTO members (name, email, password_hash) VALUES ('Ana', 'ana@example.com', 'unused') RETURNING member_id"
        ).fetchone()[0]
        other_id = connection.execute(
            "INSERT INTO members (name, email, password_hash) VALUES ('Luis', 'luis@example.com', 'unused') RETURNING member_id"
        ).fetchone()[0]
        empty_id = connection.execute(
            "INSERT INTO members (name, email, password_hash) VALUES ('Eva', 'eva@example.com', 'unused') RETURNING member_id"
        ).fetchone()[0]
        plan_id = connection.execute(
            "INSERT INTO plans (name, price, duration_days) VALUES ('Básico', 350, 30) RETURNING plan_id"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO memberships (member_id, plan_id, start_date, end_date) VALUES (%s, %s, '2026-01-01', '2026-01-31')",
            (own_id, plan_id),
        )
        connection.execute(
            "INSERT INTO memberships (member_id, plan_id, start_date, end_date) VALUES (%s, %s, '2025-01-01', '2027-01-01')",
            (other_id, plan_id),
        )
    monkeypatch.setattr(membership_service, "get_membership_start_date", lambda: today)
    token = auth.create_token(f"member:{own_id}", "access", 600, role=Role.MEMBER)[0]
    response = client.get(
        f"/api/memberships/me?member_id={other_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_active_plan"] is active
    if active:
        assert body["membership"]["plan_name"] == "Básico"
        assert body["membership"]["start_date"] == "2026-01-01"
        assert body["membership"]["end_date"] == "2026-01-31"
    else:
        assert body["membership"] is None
    empty_token = auth.create_token(
        f"member:{empty_id}", "access", 600, role=Role.MEMBER
    )[0]
    assert client.get(
        "/api/memberships/me", headers={"Authorization": f"Bearer {empty_token}"}
    ).json() == {"has_active_plan": False, "membership": None}
