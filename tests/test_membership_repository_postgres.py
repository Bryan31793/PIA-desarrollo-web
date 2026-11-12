from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import psycopg
import pytest

from app.core.exceptions import (
    InvalidMembershipDatesError,
    MemberNotFoundError,
    MembershipOverlapError,
    PlanNotFoundError,
)
from app.infrastructure.memberships.repository import membership_repository


@pytest.fixture
def membership_accounts(database):
    with psycopg.connect(database) as connection:
        member_id = connection.execute(
            """
            INSERT INTO members (name, email, password_hash, is_active)
            VALUES ('Ana', 'ana@example.com', 'unused', FALSE)
            RETURNING member_id
            """
        ).fetchone()[0]
        other_id = connection.execute(
            """
            INSERT INTO members (name, email, password_hash)
            VALUES ('Luis', 'luis@example.com', 'unused')
            RETURNING member_id
            """
        ).fetchone()[0]
        plan_id = connection.execute(
            """
            INSERT INTO plans (name, price, duration_days)
            VALUES ('Test', 350.00, 30) RETURNING plan_id
            """
        ).fetchone()[0]
    return member_id, other_id, plan_id


def test_membership_persists_without_adding_rules(database, membership_accounts):
    member_id, _, plan_id = membership_accounts
    # La base admite clientes inactivos, fechas pasadas y duraciones distintas al plan.
    row = membership_repository.create(
        member_id, plan_id, date(2020, 1, 1), date(2020, 1, 3)
    )
    assert row["member_id"] == member_id
    assert row["end_date"] == date(2020, 1, 3)
    with psycopg.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM memberships WHERE membership_id = %s",
            (row["membership_id"],),
        ).fetchone() == (1,)


@pytest.mark.parametrize("missing", ["member", "plan"])
def test_missing_reference(database, membership_accounts, missing):
    member_id, _, plan_id = membership_accounts
    expected = MemberNotFoundError if missing == "member" else PlanNotFoundError
    with pytest.raises(expected):
        membership_repository.create(
            -1 if missing == "member" else member_id,
            -1 if missing == "plan" else plan_id,
            date(2026, 1, 1),
            date(2026, 1, 31),
        )


@pytest.mark.parametrize("end", [date(2026, 1, 1), date(2025, 12, 31)])
def test_database_rejects_invalid_dates(database, membership_accounts, end):
    member_id, _, plan_id = membership_accounts
    with pytest.raises(InvalidMembershipDatesError):
        membership_repository.create(member_id, plan_id, date(2026, 1, 1), end)


def test_overlap_includes_endpoints_and_rollback_allows_next_insert(
    database, membership_accounts
):
    member_id, other_id, plan_id = membership_accounts
    membership_repository.create(
        member_id, plan_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    for start, end in [
        (date(2026, 1, 10), date(2026, 2, 10)),
        (date(2026, 1, 31), date(2026, 2, 28)),
        (date(2025, 12, 1), date(2026, 1, 1)),
    ]:
        with pytest.raises(MembershipOverlapError):
            membership_repository.create(member_id, plan_id, start, end)
    membership_repository.create(
        member_id, plan_id, date(2026, 2, 1), date(2026, 2, 28)
    )
    membership_repository.create(other_id, plan_id, date(2026, 1, 1), date(2026, 1, 31))
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM memberships").fetchone() == (3,)


@pytest.mark.parametrize("attempt", range(3))
def test_concurrent_overlapping_requests_cannot_both_succeed(
    database, membership_accounts, attempt
):
    member_id, _, plan_id = membership_accounts
    barrier = Barrier(2)

    def register():
        barrier.wait(timeout=10)
        try:
            membership_repository.create(
                member_id, plan_id, date(2026, 1, 1), date(2026, 1, 31)
            )
        except MembershipOverlapError:
            return "overlap"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: register(), range(2)))
    assert sorted(results) == ["created", "overlap"]


def test_staff_endpoint_persists_and_reports_database_conflicts(
    database, membership_accounts, monkeypatch
):
    import importlib
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.core.exceptions import StorageUnavailableError
    from app.core.roles import Role
    from app.services import membership_service

    monkeypatch.setenv(
        "JWT_SECRET", "test-secret-for-membership-postgres-at-least-32-bytes"
    )
    auth = importlib.import_module("app.services.auth_service")
    monkeypatch.setattr(
        auth.refresh_token_repository, "is_access_token_active", lambda jti: True
    )
    with psycopg.connect(database) as connection:
        employee_id = connection.execute(
            "INSERT INTO employees (name, email, password_hash, role_id) SELECT 'Staff', 'staff@example.com', 'unused', role_id FROM roles WHERE name = 'Staff' RETURNING employee_id"
        ).fetchone()[0]
    token = auth.create_token(
        f"employee:{employee_id}", "access", 600, role=Role.STAFF
    )[0]
    headers = {"Authorization": f"Bearer {token}"}
    member_id, other_id, plan_id = membership_accounts
    with psycopg.connect(database) as connection:
        migration = (
            Path(__file__).resolve().parents[1] / "migrations/002_cash_payments.sql"
        )
        connection.execute(migration.read_text())
    monkeypatch.setattr(
        membership_service, "get_membership_start_date", lambda: date(2026, 1, 1)
    )
    app = importlib.import_module("app.main").app
    with TestClient(app) as client:
        data = {"member_id": member_id, "plan_id": plan_id}

        # El fallo de pago ocurre después del INSERT de membresía y debe revertirlo.
        def unavailable(*args, **kwargs):
            raise StorageUnavailableError()

        with monkeypatch.context() as payment_failure:
            payment_failure.setattr(
                membership_service.payment_repository, "create", unavailable
            )
            failed = client.post("/api/memberships", headers=headers, json=data)
            assert failed.status_code == 503
        with psycopg.connect(database) as connection:
            assert connection.execute(
                "SELECT count(*) FROM memberships"
            ).fetchone() == (0,)
            assert connection.execute("SELECT count(*) FROM payments").fetchone() == (
                0,
            )
        created = client.post("/api/memberships", headers=headers, json=data)
        assert created.status_code == 201
        assert created.json()["end_date"] == "2026-01-31"
        payment = created.json()["payment"]
        assert payment["amount"] == "350.00"
        assert payment["employee_id"] == employee_id
        assert payment["membership_id"] == created.json()["membership_id"]
        assert payment["currency"] == "MXN"
        assert payment["paid_at"]
        for start in [date(2026, 1, 15), date(2026, 1, 31)]:
            monkeypatch.setattr(
                membership_service,
                "get_membership_start_date",
                lambda start=start: start,
            )
            response = client.post("/api/memberships", headers=headers, json=data)
            assert response.status_code == 409
            assert response.json() == {
                "detail": "Membership dates overlap an existing membership"
            }
        monkeypatch.setattr(
            membership_service, "get_membership_start_date", lambda: date(2026, 2, 1)
        )
        assert (
            client.post(
                "/api/memberships",
                headers=headers,
                json=data,
            ).status_code
            == 201
        )
        for changes, message in [
            ({"member_id": -1}, "Member not found"),
            ({"plan_id": -1}, "Plan not found"),
        ]:
            response = client.post(
                "/api/memberships", headers=headers, json=data | changes
            )
            assert response.status_code == 404
            assert response.json() == {"detail": message}
        missing_employee_token = auth.create_token(
            "employee:9223372036854775807", "access", 600, role=Role.STAFF
        )[0]
        response = client.post(
            "/api/memberships",
            headers={"Authorization": f"Bearer {missing_employee_token}"},
            json={"member_id": other_id, "plan_id": plan_id},
        )
        assert response.status_code == 401
        # Un plan gratuito tampoco debe dejar registros parciales.
        with psycopg.connect(database) as connection:
            connection.execute(
                "UPDATE plans SET price = 0 WHERE plan_id = %s", (plan_id,)
            )
        response = client.post(
            "/api/memberships",
            headers=headers,
            json={"member_id": other_id, "plan_id": plan_id},
        )
        assert response.status_code == 422
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM memberships").fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM payments").fetchone() == (2,)
        # Cambiar la tarifa no altera los pagos registrados.
        assert (
            connection.execute("SELECT DISTINCT amount FROM payments").fetchone()[0]
            == 350
        )
