import importlib
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    EmployeeEmailAlreadyExistsError,
    PlanNameAlreadyExistsError,
    StorageUnavailableError,
)
from app.core.passwords import password_hasher
from app.core.roles import Role
from app.infrastructure.employees.repository import employee_repository
from app.infrastructure.plans.repository import plan_repository


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-admin-at-least-32-bytes")
    auth = importlib.import_module("app.services.auth_service")
    monkeypatch.setattr(
        auth.refresh_token_repository, "is_access_token_active", lambda jti: True
    )
    return auth


@pytest.fixture
def client(auth):
    with TestClient(importlib.import_module("app.main").app) as client:
        yield client


@pytest.fixture
def admin_headers(auth):
    token = auth.create_token("employee:1", "access", 600, role=Role.ADMIN)[0]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def persistence(monkeypatch):
    create = MagicMock(
        side_effect=lambda name, price, duration: {
            "plan_id": 7,
            "name": name,
            "price": price,
            "duration_days": duration,
        }
    )
    patch = MagicMock(
        return_value={
            "plan_id": 7,
            "name": "Básico",
            "price": Decimal("450.25"),
            "duration_days": 30,
        }
    )
    employee = MagicMock(
        side_effect=lambda name, email, password_hash, role: {
            "employee_id": 8,
            "name": name,
            "email": email,
            "is_active": True,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )
    monkeypatch.setattr(plan_repository, "create", create)
    monkeypatch.setattr(plan_repository, "patch", patch)
    monkeypatch.setattr(employee_repository, "create", employee)
    return create, patch, employee


def test_admin_creates_plan(client, admin_headers, persistence):
    response = client.post(
        "/api/plans",
        headers=admin_headers,
        json={"name": " Básico ", "price": "350.25", "duration_days": 30},
    )
    assert response.status_code == 201
    assert response.json() == {
        "plan_id": 7,
        "name": "Básico",
        "price": "350.25",
        "duration_days": 30,
    }
    persistence[0].assert_called_once_with("Básico", Decimal("350.25"), 30)


def test_patch_only_sends_supplied_fields(client, admin_headers, persistence):
    response = client.patch(
        "/api/plans/7", headers=admin_headers, json={"price": "450.25"}
    )
    assert response.status_code == 200
    persistence[1].assert_called_once_with(7, {"price": Decimal("450.25")})


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/api/plans", {"name": "Test", "price": "350", "duration_days": 30}),
        ("PATCH", "/api/plans/7", {"price": "350"}),
        (
            "POST",
            "/api/employees",
            {
                "name": "Ana",
                "email": "ana@example.com",
                "password": "password123",
                "role": "staff",
            },
        ),
    ],
)
@pytest.mark.parametrize("role", [Role.MEMBER, Role.STAFF])
def test_non_admin_roles_cannot_manage_plans_or_employees(
    client, auth, persistence, method, path, body, role
):
    subject = "member:1" if role == Role.MEMBER else "employee:1"
    token = auth.create_token(subject, "access", 600, role=role)[0]
    assert (
        client.request(
            method, path, headers={"Authorization": f"Bearer {token}"}, json=body
        ).status_code
        == 403
    )
    for mock in persistence:
        mock.assert_not_called()


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/api/plans", "POST", {"name": "Test", "price": "350", "duration_days": 30}),
        ("/api/plans/7", "PATCH", {"price": "350"}),
        (
            "/api/employees",
            "POST",
            {
                "name": "Ana",
                "email": "ana@example.com",
                "password": "password123",
                "role": "staff",
            },
        ),
    ],
)
@pytest.mark.parametrize(
    "kind", ["missing", "invalid", "expired", "refresh", "revoked"]
)
def test_admin_endpoints_require_access_token(
    client, auth, monkeypatch, persistence, path, method, body, kind
):
    token = "invalid"
    if kind in {"expired", "revoked"}:
        token = auth.create_token(
            "employee:1", "access", -1 if kind == "expired" else 600, role=Role.ADMIN
        )[0]
    elif kind == "refresh":
        token = auth.create_token("employee:1", "refresh", 600)[0]
    if kind == "revoked":
        monkeypatch.setattr(
            auth.refresh_token_repository, "is_access_token_active", lambda jti: False
        )
    response = client.request(
        method,
        path,
        headers={} if kind == "missing" else {"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert response.status_code == 401
    for mock in persistence:
        mock.assert_not_called()


@pytest.mark.parametrize(
    "price",
    ["0", "-1", "NaN", "Infinity", "-Infinity", "350.001", "100000000", True, None],
)
@pytest.mark.parametrize(
    "method,path", [("POST", "/api/plans"), ("PATCH", "/api/plans/7")]
)
def test_price_validation_is_done_before_persistence(
    client, admin_headers, persistence, price, method, path
):
    body = {"price": price}
    if method == "POST":
        body |= {"name": "Test", "duration_days": 30}
    assert (
        client.request(method, path, headers=admin_headers, json=body).status_code
        == 422
    )
    persistence[0].assert_not_called()
    persistence[1].assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"duration_days": None},
        {"name": "   "},
        {"name": "x" * 51},
        {"duration_days": 0},
        {"duration_days": True},
        {"duration_days": 2**31},
        {"plan_id": 99},
    ],
)
def test_patch_rejects_empty_null_or_invalid_fields(
    client, admin_headers, persistence, body
):
    assert (
        client.patch("/api/plans/7", headers=admin_headers, json=body).status_code
        == 422
    )
    persistence[1].assert_not_called()


def test_patch_missing_plan_returns_not_found(client, admin_headers, persistence):
    persistence[1].return_value = None
    response = client.patch(
        "/api/plans/7", headers=admin_headers, json={"price": "450"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Plan not found"}


@pytest.mark.parametrize("role,db_role", [("admin", "Admin"), ("staff", "Staff")])
def test_admin_registers_employee_and_hashes_password(
    client, admin_headers, persistence, role, db_role
):
    response = client.post(
        "/api/employees",
        headers=admin_headers,
        json={
            "name": " Ana ",
            "email": "ANA@EXAMPLE.COM",
            "password": "password123",
            "role": role,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == role
    assert body["email"] == "ana@example.com"
    assert body["is_active"] is True
    assert "password" not in body and "password_hash" not in body
    name, email, stored_hash, role_name = persistence[2].call_args.args
    assert (name, email, role_name) == ("Ana", "ana@example.com", db_role)
    assert stored_hash.startswith("$argon2id$")
    assert password_hasher.verify("password123", stored_hash)


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "member"},
        {"role": "owner"},
        {"role": None},
        {"role_id": 1},
        {"is_active": False},
        {"email": "invalid"},
        {"password": "short"},
        {"name": " "},
    ],
)
def test_employee_registration_rejects_invalid_fields(
    client, admin_headers, persistence, changes
):
    body = {
        "name": "Ana",
        "email": "ana@example.com",
        "password": "password123",
        "role": "staff",
    } | changes
    assert (
        client.post("/api/employees", headers=admin_headers, json=body).status_code
        == 422
    )
    persistence[2].assert_not_called()


@pytest.mark.parametrize(
    "index,path,method,body,error,status",
    [
        (
            0,
            "/api/plans",
            "POST",
            {"name": "Test", "price": "350", "duration_days": 30},
            PlanNameAlreadyExistsError,
            409,
        ),
        (
            1,
            "/api/plans/7",
            "PATCH",
            {"name": "Other"},
            PlanNameAlreadyExistsError,
            409,
        ),
        (
            2,
            "/api/employees",
            "POST",
            {
                "name": "Ana",
                "email": "ana@example.com",
                "password": "password123",
                "role": "staff",
            },
            EmployeeEmailAlreadyExistsError,
            409,
        ),
        (
            0,
            "/api/plans",
            "POST",
            {"name": "Test", "price": "350", "duration_days": 30},
            StorageUnavailableError,
            503,
        ),
    ],
)
def test_admin_domain_errors_are_translated(
    client, admin_headers, persistence, index, path, method, body, error, status
):
    persistence[index].side_effect = error()
    response = client.request(method, path, headers=admin_headers, json=body)
    assert response.status_code == status
    assert response.json() == {"detail": error.default_message}
