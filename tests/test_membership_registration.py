import importlib
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import ANY, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    InvalidPlanPriceError,
    MemberNotFoundError,
    MembershipOverlapError,
    PlanNotFoundError,
    StorageUnavailableError,
)
from app.core.roles import Role
from app.infrastructure.memberships.repository import membership_repository
from app.infrastructure.plans.repository import plan_repository
from app.services import membership_service


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-memberships-at-least-32-bytes")
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
def headers(auth):
    token = auth.create_token("employee:42", "access", 600, role=Role.STAFF)[0]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def persistence(monkeypatch):
    monkeypatch.setattr(
        membership_service, "get_membership_start_date", lambda: date(2026, 1, 1)
    )
    context = MagicMock()
    monkeypatch.setattr(membership_service, "get_connection", context)
    find = MagicMock(
        return_value={"plan_id": 7, "duration_days": 30, "price": Decimal("350.00")}
    )
    create = MagicMock(
        side_effect=lambda member_id, plan_id, start, end, **kwargs: {
            "membership_id": 1,
            "member_id": member_id,
            "plan_id": plan_id,
            "start_date": start,
            "end_date": end,
        }
    )
    payment = MagicMock(
        side_effect=lambda membership_id, employee_id, amount, **kwargs: {
            "payment_id": 9,
            "membership_id": membership_id,
            "employee_id": employee_id,
            "amount": amount,
            "currency": "MXN",
            "paid_at": datetime(2026, 1, 1, 12, tzinfo=UTC),
            "notes": None,
        }
    )
    monkeypatch.setattr(membership_service.payment_repository, "create", payment)
    monkeypatch.setattr(plan_repository, "find_by_id", find)
    monkeypatch.setattr(membership_repository, "create", create)
    return find, create


def test_staff_registers_membership_and_duration_comes_from_plan(
    client, headers, persistence
):
    response = client.post(
        "/api/memberships",
        headers=headers,
        json={"member_id": 42, "plan_id": 7},
    )
    assert response.status_code == 201
    assert response.json() == {
        "membership_id": 1,
        "member_id": 42,
        "plan_id": 7,
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "payment": {
            "payment_id": 9,
            "membership_id": 1,
            "employee_id": 42,
            "amount": "350.00",
            "currency": "MXN",
            "paid_at": "2026-01-01T12:00:00Z",
            "notes": None,
        },
    }
    find, create = persistence
    find.assert_called_once_with(7, connection=ANY)
    create.assert_called_once_with(
        42, 7, date(2026, 1, 1), date(2026, 1, 31), connection=ANY
    )
    membership_service.payment_repository.create.assert_called_once_with(
        1, 42, Decimal("350.00"), connection=find.call_args.kwargs["connection"]
    )
    assert create.call_args.kwargs["connection"] is find.call_args.kwargs["connection"]


@pytest.mark.parametrize(
    "duration,start,end",
    [
        (1, "2026-01-01", "2026-01-02"),
        (30, "2024-02-01", "2024-03-02"),
        (365, "2026-01-01", "2027-01-01"),
    ],
)
def test_duration_uses_days_and_handles_leap_years(
    client, headers, persistence, monkeypatch, duration, start, end
):
    monkeypatch.setattr(
        membership_service,
        "get_membership_start_date",
        lambda: date.fromisoformat(start),
    )
    persistence[0].return_value["duration_days"] = duration
    response = client.post(
        "/api/memberships",
        headers=headers,
        json={"member_id": 42, "plan_id": 7},
    )
    assert response.status_code == 201
    assert response.json()["end_date"] == end


@pytest.mark.parametrize(
    "role,subject", [(Role.MEMBER, "member:42"), (Role.ADMIN, "employee:42")]
)
def test_other_roles_cannot_register(client, auth, persistence, role, subject):
    token = auth.create_token(subject, "access", 600, role=role)[0]
    response = client.post(
        "/api/memberships",
        headers={"Authorization": f"Bearer {token}"},
        json={"member_id": 42, "plan_id": 7},
    )
    assert response.status_code == 403
    for mock in persistence:
        mock.assert_not_called()


@pytest.mark.parametrize("token", [None, "invalid", "expired", "refresh", "revoked"])
def test_authentication_required(client, auth, monkeypatch, persistence, token):
    if token in {"expired", "revoked"}:
        if token == "revoked":
            monkeypatch.setattr(
                auth.refresh_token_repository,
                "is_access_token_active",
                lambda jti: False,
            )
        token = auth.create_token(
            "employee:42", "access", -1 if token == "expired" else 600, role=Role.STAFF
        )[0]
    elif token == "refresh":
        token = auth.create_token("employee:42", "refresh", 600)[0]
    response = client.post(
        "/api/memberships",
        headers={"Authorization": f"Bearer {token}"} if token else {},
        json={"member_id": 42, "plan_id": 7},
    )
    assert response.status_code == 401
    for mock in persistence:
        mock.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"end_date": "2026-02-01"},
        {"start_date": "2026-01-01"},
        {"member_id": None},
        {"plan_id": True},
        {"plan_id": 2**63},
        {"amount": 350},
        {"price": 1},
        {"employee_id": 1},
        {"duration_days": 30},
    ],
)
def test_invalid_input_does_not_reach_database(client, headers, persistence, changes):
    response = client.post(
        "/api/memberships",
        headers=headers,
        json={"member_id": 42, "plan_id": 7} | changes,
    )
    assert response.status_code == 422
    for mock in persistence:
        mock.assert_not_called()


def test_missing_plan_is_domain_error(client, headers, persistence):
    persistence[0].return_value = None
    response = client.post(
        "/api/memberships",
        headers=headers,
        json={"member_id": 42, "plan_id": 7},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Plan not found"}
    persistence[1].assert_not_called()


@pytest.mark.parametrize(
    "error,status",
    [
        (MemberNotFoundError, 404),
        (PlanNotFoundError, 404),
        (MembershipOverlapError, 409),
        (StorageUnavailableError, 503),
    ],
)
def test_domain_errors_are_translated(client, headers, persistence, error, status):
    persistence[1].side_effect = error()
    response = client.post(
        "/api/memberships",
        headers=headers,
        json={"member_id": 42, "plan_id": 7},
    )
    assert response.status_code == status
    assert response.json() == {"detail": error.default_message}


def test_date_overflow_is_validation_error(client, headers, persistence):
    persistence[0].return_value["duration_days"] = 2**31 - 1
    response = client.post(
        "/api/memberships",
        headers=headers,
        json={"member_id": 42, "plan_id": 7},
    )
    assert response.status_code == 422
    persistence[1].assert_not_called()


@pytest.mark.parametrize(
    "instant,expected",
    [
        (datetime(2026, 1, 1, 3, tzinfo=UTC), date(2025, 12, 31)),
        (datetime(2026, 1, 1, 6, tzinfo=UTC), date(2026, 1, 1)),
    ],
)
def test_start_date_uses_monterrey_day_at_midnight(monkeypatch, instant, expected):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    monkeypatch.setattr(membership_service, "datetime", FrozenDatetime)
    assert membership_service.get_membership_start_date() == expected


@pytest.mark.parametrize("price", [Decimal("0.00"), Decimal("NaN")])
def test_invalid_plan_price_cannot_create_membership_or_payment(
    client, headers, persistence, price
):
    persistence[0].return_value["price"] = price
    response = client.post(
        "/api/memberships", headers=headers, json={"member_id": 42, "plan_id": 7}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": InvalidPlanPriceError.default_message}
    persistence[1].assert_not_called()
    membership_service.payment_repository.create.assert_not_called()


def test_payment_uses_exact_plan_price_with_cents(client, headers, persistence):
    persistence[0].return_value["price"] = Decimal("450.25")
    response = client.post(
        "/api/memberships", headers=headers, json={"member_id": 42, "plan_id": 7}
    )
    assert response.status_code == 201
    assert response.json()["payment"]["amount"] == "450.25"
