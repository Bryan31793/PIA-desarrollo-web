import importlib
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AccessPassUnavailableError,
    ActiveMembershipRequiredError,
    DailyCheckInLimitError,
    InactiveMemberError,
    StorageUnavailableError,
)
from app.core.roles import Role
from app.schemas.access import AccessPassResponse, CheckInResponse
from app.services import access_service


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-qr-access-at-least-32-bytes")
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
def services(monkeypatch):
    generate = MagicMock(
        return_value=AccessPassResponse(
            pass_token="a" * 43,
            expires_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_in=120,
        )
    )
    check_in = MagicMock(
        return_value=CheckInResponse(
            check_in_id=1,
            member_id=42,
            member_name="Ana",
            membership_id=7,
            employee_id=8,
            checked_in_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    router = importlib.import_module("app.routers.access")
    monkeypatch.setattr(router, "generate_access_pass", generate)
    monkeypatch.setattr(router, "register_check_in", check_in)
    return generate, check_in


def headers(auth, role):
    subject = "member:42" if role == Role.MEMBER else "employee:8"
    token = auth.create_token(subject, "access", 600, role=role)[0]
    return {"Authorization": f"Bearer {token}"}


def test_member_generates_non_cached_qr_content(client, auth, services):
    response = client.post("/api/access-passes", headers=headers(auth, Role.MEMBER))
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["expires_in"] == 120
    assert response.json()["pass_token"] == "a" * 43
    assert services[0].call_args.args[0].subject == "member:42"


def test_staff_scan_immediately_registers_entry(client, auth, services):
    response = client.post(
        "/api/check-ins",
        headers=headers(auth, Role.STAFF),
        json={"pass_token": "a" * 43},
    )
    assert response.status_code == 201
    assert response.json()["member_name"] == "Ana"
    data, identity = services[1].call_args.args
    assert data.pass_token.get_secret_value() == "a" * 43
    assert identity.subject == "employee:8"


@pytest.mark.parametrize(
    "path,role",
    [
        ("/api/access-passes", Role.STAFF),
        ("/api/access-passes", Role.ADMIN),
        ("/api/check-ins", Role.MEMBER),
        ("/api/check-ins", Role.ADMIN),
    ],
)
def test_access_endpoints_are_role_restricted(client, auth, services, path, role):
    assert (
        client.post(
            path, headers=headers(auth, role), json={"pass_token": "a" * 43}
        ).status_code
        == 403
    )
    for service in services:
        service.assert_not_called()


@pytest.mark.parametrize("path", ["/api/access-passes", "/api/check-ins"])
@pytest.mark.parametrize(
    "kind", ["missing", "invalid", "expired", "refresh", "revoked"]
)
def test_access_endpoints_require_valid_access_tokens(
    client, auth, monkeypatch, services, path, kind
):
    role = Role.MEMBER if path.endswith("access-passes") else Role.STAFF
    subject = "member:42" if role == Role.MEMBER else "employee:8"
    token = "invalid"
    if kind in {"expired", "revoked"}:
        token = auth.create_token(
            subject, "access", -1 if kind == "expired" else 600, role=role
        )[0]
    elif kind == "refresh":
        token = auth.create_token(subject, "refresh", 600)[0]
    if kind == "revoked":
        monkeypatch.setattr(
            auth.refresh_token_repository, "is_access_token_active", lambda jti: False
        )
    response = client.post(
        path,
        headers={} if kind == "missing" else {"Authorization": f"Bearer {token}"},
        json={"pass_token": "a" * 43},
    )
    assert response.status_code == 401
    for service in services:
        service.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"pass_token": "short"},
        {"pass_token": "x" * 1000},
        {"pass_token": "a" * 43, "member_id": 1},
        {"pass_token": "a" * 43, "employee_id": 1},
    ],
)
def test_scanner_rejects_invalid_payload(client, auth, services, body):
    assert (
        client.post(
            "/api/check-ins", headers=headers(auth, Role.STAFF), json=body
        ).status_code
        == 422
    )
    services[1].assert_not_called()


@pytest.mark.parametrize(
    "error,status",
    [
        (AccessPassUnavailableError, 409),
        (DailyCheckInLimitError, 409),
        (InactiveMemberError, 403),
        (ActiveMembershipRequiredError, 403),
        (StorageUnavailableError, 503),
    ],
)
def test_scan_domain_errors_are_translated(client, auth, services, error, status):
    services[1].side_effect = error()
    response = client.post(
        "/api/check-ins",
        headers=headers(auth, Role.STAFF),
        json={"pass_token": "a" * 43},
    )
    assert response.status_code == status
    assert response.json() == {"detail": error.default_message}


def test_get_access_time_is_aware_utc():
    now = access_service.get_access_time()
    assert now.tzinfo == UTC


def test_generating_after_daily_entry_returns_conflict(client, auth, services):
    services[0].side_effect = DailyCheckInLimitError()
    response = client.post("/api/access-passes", headers=headers(auth, Role.MEMBER))
    assert response.status_code == 409
    assert response.json() == {"detail": "Member has already checked in today"}
