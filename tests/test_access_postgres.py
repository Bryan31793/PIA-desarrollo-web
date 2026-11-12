from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import psycopg
import pytest

from app.core.exceptions import (
    AccessPassUnavailableError,
    ActiveMembershipRequiredError,
    DailyCheckInLimitError,
    InactiveMemberError,
    InvalidTokenError,
    MemberNotFoundError,
    StorageUnavailableError,
)
from app.core.identity import AuthenticatedIdentity
from app.core.roles import Role
from app.schemas.access import CheckInRequest
from app.services import access_service


@pytest.fixture
def accounts(database, monkeypatch):
    with psycopg.connect(database) as connection:
        connection.execute(
            (
                Path(__file__).resolve().parents[1] / "migrations/005_access_passes.sql"
            ).read_text()
        )
        member_id = connection.execute(
            "INSERT INTO members (name, email, password_hash) VALUES ('Ana', 'ana@example.com', 'unused') RETURNING member_id"
        ).fetchone()[0]
        other_id = connection.execute(
            "INSERT INTO members (name, email, password_hash) VALUES ('Luis', 'luis@example.com', 'unused') RETURNING member_id"
        ).fetchone()[0]
        employee_id = connection.execute(
            "INSERT INTO employees (name, email, password_hash, role_id) SELECT 'Staff', 'staff@example.com', 'unused', role_id FROM roles WHERE name = 'Staff' RETURNING employee_id"
        ).fetchone()[0]
        plan_id = connection.execute(
            "INSERT INTO plans (name, price, duration_days) VALUES ('Básico', 350, 30) RETURNING plan_id"
        ).fetchone()[0]
        membership_id = connection.execute(
            "INSERT INTO memberships (member_id, plan_id, start_date, end_date) VALUES (%s, %s, '2026-01-01', '2026-01-31') RETURNING membership_id",
            (member_id, plan_id),
        ).fetchone()[0]
    monkeypatch.setattr(
        access_service, "get_access_time", lambda: datetime(2026, 1, 15, 18, tzinfo=UTC)
    )
    return {
        "member": AuthenticatedIdentity(f"member:{member_id}", Role.MEMBER),
        "staff": AuthenticatedIdentity(f"employee:{employee_id}", Role.STAFF),
        "member_id": member_id,
        "other_id": other_id,
        "membership_id": membership_id,
    }


def generate(accounts):
    return access_service.generate_access_pass(accounts["member"])


def scan(accounts, token):
    return access_service.register_check_in(
        CheckInRequest(pass_token=token), accounts["staff"]
    )


def test_pass_hash_single_use_and_daily_limit_resets_next_day(
    database, accounts, monkeypatch
):
    first = generate(accounts)
    assert first.expires_in == 120
    assert first.expires_at == datetime(2026, 1, 15, 18, 2, tzinfo=UTC)
    assert len(first.pass_token) == 43
    with psycopg.connect(database) as connection:
        stored = connection.execute("SELECT token_hash FROM access_passes").fetchone()[
            0
        ]
        assert stored == sha256(first.pass_token.encode()).hexdigest()
        assert stored != first.pass_token
    entry = scan(accounts, first.pass_token)
    assert entry.member_name == "Ana"
    assert entry.member_id == accounts["member_id"]
    assert entry.membership_id == accounts["membership_id"]
    with pytest.raises(AccessPassUnavailableError):
        scan(accounts, first.pass_token)
    with pytest.raises(DailyCheckInLimitError):
        generate(accounts)
    monkeypatch.setattr(
        access_service, "get_access_time", lambda: datetime(2026, 1, 16, 18, tzinfo=UTC)
    )
    second = generate(accounts)
    assert second.pass_token != first.pass_token
    scan(accounts, second.pass_token)
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (2,)
        assert connection.execute(
            "SELECT count(*) FROM access_passes WHERE consumed_at IS NOT NULL"
        ).fetchone() == (2,)


def test_regeneration_invalidates_previous_pass(database, accounts):
    first = generate(accounts)
    second = generate(accounts)
    with pytest.raises(AccessPassUnavailableError):
        scan(accounts, first.pass_token)
    scan(accounts, second.pass_token)
    with psycopg.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM access_passes WHERE invalidated_at IS NOT NULL"
        ).fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (1,)


@pytest.mark.parametrize("seconds,valid", [(119, True), (120, False), (121, False)])
def test_pass_expiration_boundary(database, accounts, monkeypatch, seconds, valid):
    token = generate(accounts).pass_token
    monkeypatch.setattr(
        access_service,
        "get_access_time",
        lambda: datetime(2026, 1, 15, 18, tzinfo=UTC) + timedelta(seconds=seconds),
    )
    if valid:
        scan(accounts, token)
    else:
        with pytest.raises(AccessPassUnavailableError):
            scan(accounts, token)


def test_unknown_pass_is_rejected(database, accounts):
    with pytest.raises(AccessPassUnavailableError):
        scan(accounts, "x" * 43)


@pytest.mark.parametrize("phase", ["generate", "scan"])
@pytest.mark.parametrize(
    "condition,error",
    [
        ("inactive", InactiveMemberError),
        ("no_membership", ActiveMembershipRequiredError),
    ],
)
def test_checks_current_account_and_membership(
    database, accounts, phase, condition, error
):
    token = generate(accounts).pass_token if phase == "scan" else None
    with psycopg.connect(database) as connection:
        if condition == "inactive":
            connection.execute(
                "UPDATE members SET is_active = FALSE WHERE member_id = %s",
                (accounts["member_id"],),
            )
        else:
            connection.execute(
                "UPDATE memberships SET start_date = '2027-01-01', end_date = '2027-01-31' WHERE membership_id = %s",
                (accounts["membership_id"],),
            )
    with pytest.raises(error):
        generate(accounts) if phase == "generate" else scan(accounts, token)
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM access_passes WHERE consumed_at IS NOT NULL"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "instant,valid",
    [
        (datetime(2026, 1, 1, 5, 59, tzinfo=UTC), False),
        (datetime(2026, 1, 1, 6, tzinfo=UTC), True),
        (datetime(2026, 2, 1, 5, 59, tzinfo=UTC), True),
        (datetime(2026, 2, 1, 6, tzinfo=UTC), False),
    ],
)
def test_membership_inclusive_dates_use_monterrey(
    database, accounts, monkeypatch, instant, valid
):
    monkeypatch.setattr(access_service, "get_access_time", lambda: instant)
    if valid:
        scan(accounts, generate(accounts).pass_token)
    else:
        with pytest.raises(ActiveMembershipRequiredError):
            generate(accounts)


def test_midnight_can_invalidate_membership_before_pass_expires(
    database, accounts, monkeypatch
):
    monkeypatch.setattr(
        access_service,
        "get_access_time",
        lambda: datetime(2026, 2, 1, 5, 59, tzinfo=UTC),
    )
    token = generate(accounts).pass_token
    monkeypatch.setattr(
        access_service, "get_access_time", lambda: datetime(2026, 2, 1, 6, tzinfo=UTC)
    )
    with pytest.raises(ActiveMembershipRequiredError):
        scan(accounts, token)


def test_scan_failure_rolls_back_consumption_and_entry(database, accounts, monkeypatch):
    token = generate(accounts).pass_token

    def fail(*args, **kwargs):
        raise StorageUnavailableError()

    with monkeypatch.context() as failure:
        failure.setattr(access_service.access_repository, "create_check_in", fail)
        with pytest.raises(StorageUnavailableError):
            scan(accounts, token)
    with psycopg.connect(database) as connection:
        assert connection.execute(
            "SELECT consumed_at FROM access_passes"
        ).fetchone() == (None,)
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (0,)
    scan(accounts, token)


def test_missing_employee_rolls_back_consumption(database, accounts):
    token = generate(accounts).pass_token
    missing_staff = AuthenticatedIdentity("employee:9223372036854775807", Role.STAFF)
    with pytest.raises(InvalidTokenError):
        access_service.register_check_in(
            CheckInRequest(pass_token=token), missing_staff
        )
    scan(accounts, token)


def test_generation_failure_does_not_invalidate_previous_pass(
    database, accounts, monkeypatch
):
    token = generate(accounts).pass_token

    def fail(*args, **kwargs):
        raise StorageUnavailableError()

    with monkeypatch.context() as failure:
        failure.setattr(access_service.access_repository, "create_pass", fail)
        with pytest.raises(StorageUnavailableError):
            generate(accounts)
    scan(accounts, token)


def test_missing_member_cannot_generate(database, accounts):
    with pytest.raises(MemberNotFoundError):
        access_service.generate_access_pass(
            AuthenticatedIdentity("member:9223372036854775807", Role.MEMBER)
        )


def test_member_without_membership_cannot_generate_for_someone_else(database, accounts):
    with pytest.raises(ActiveMembershipRequiredError):
        access_service.generate_access_pass(
            AuthenticatedIdentity(f"member:{accounts['other_id']}", Role.MEMBER)
        )


@pytest.mark.parametrize("attempt", range(3))
def test_simultaneous_scans_register_one_entry(database, accounts, attempt):
    token = generate(accounts).pass_token
    barrier = Barrier(2)

    def register(_):
        barrier.wait(timeout=10)
        try:
            scan(accounts, token)
            return "created"
        except AccessPassUnavailableError:
            return "unavailable"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(register, range(2))) == ["created", "unavailable"]
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (1,)


def test_simultaneous_generation_leaves_one_usable_pass(database, accounts):
    barrier = Barrier(2)

    def create(_):
        barrier.wait(timeout=10)
        return generate(accounts).pass_token

    with ThreadPoolExecutor(max_workers=2) as executor:
        tokens = list(executor.map(create, range(2)))
    succeeded = 0
    for token in tokens:
        try:
            scan(accounts, token)
            succeeded += 1
        except AccessPassUnavailableError:
            pass
    assert succeeded == 1


def test_http_qr_generation_and_staff_scan(database, accounts, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    monkeypatch.setenv("JWT_SECRET", "test-secret-for-qr-http-at-least-32-bytes")
    auth = importlib.import_module("app.services.auth_service")
    monkeypatch.setattr(
        auth.refresh_token_repository, "is_access_token_active", lambda jti: True
    )
    member_token = auth.create_token(
        accounts["member"].subject, "access", 600, role=Role.MEMBER
    )[0]
    staff_token = auth.create_token(
        accounts["staff"].subject, "access", 600, role=Role.STAFF
    )[0]
    with TestClient(importlib.import_module("app.main").app) as client:
        response = client.post(
            "/api/access-passes", headers={"Authorization": f"Bearer {member_token}"}
        )
        assert response.status_code == 201
        token = response.json()["pass_token"]
        response = client.post(
            "/api/check-ins",
            headers={"Authorization": f"Bearer {staff_token}"},
            json={"pass_token": token},
        )
        assert response.status_code == 201
        assert response.json()["member_id"] == accounts["member_id"]
        assert (
            client.post(
                "/api/check-ins",
                headers={"Authorization": f"Bearer {staff_token}"},
                json={"pass_token": token},
            ).status_code
            == 409
        )


def test_regeneration_and_scan_are_serialized(database, accounts):
    old_token = generate(accounts).pass_token
    barrier = Barrier(2)

    def regenerate():
        barrier.wait(timeout=10)
        try:
            return generate(accounts).pass_token
        except DailyCheckInLimitError:
            return None

    def scan_old():
        barrier.wait(timeout=10)
        try:
            scan(accounts, old_token)
            return True
        except AccessPassUnavailableError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        new_pass = executor.submit(regenerate)
        old_scan = executor.submit(scan_old)
        new_token = new_pass.result(timeout=15)
        old_succeeded = old_scan.result(timeout=15)
    with pytest.raises(AccessPassUnavailableError):
        scan(accounts, old_token)
    if new_token is not None:
        assert not old_succeeded
        scan(accounts, new_token)
    else:
        assert old_succeeded
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (1,)


def test_new_pending_pass_cannot_bypass_daily_entry_limit(database, accounts):
    scan(accounts, generate(accounts).pass_token)
    # Simula un pase pendiente heredado; el escaneo también aplica el límite.
    token = "z" * 43
    now = access_service.get_access_time()
    with psycopg.connect(database) as connection:
        connection.execute(
            "INSERT INTO access_passes (token_hash, member_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
            (
                sha256(token.encode()).hexdigest(),
                accounts["member_id"],
                now,
                now + timedelta(seconds=120),
            ),
        )
    with pytest.raises(DailyCheckInLimitError):
        scan(accounts, token)
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (1,)
        assert connection.execute(
            "SELECT consumed_at FROM access_passes WHERE token_hash = %s",
            (sha256(token.encode()).hexdigest(),),
        ).fetchone() == (None,)


def test_daily_entry_resets_at_monterrey_midnight(database, accounts, monkeypatch):
    monkeypatch.setattr(
        access_service,
        "get_access_time",
        lambda: datetime(2026, 1, 15, 5, 59, tzinfo=UTC),
    )
    scan(accounts, generate(accounts).pass_token)
    monkeypatch.setattr(
        access_service,
        "get_access_time",
        lambda: datetime(2026, 1, 15, 5, 59, 59, tzinfo=UTC),
    )
    with pytest.raises(DailyCheckInLimitError):
        generate(accounts)
    monkeypatch.setattr(
        access_service, "get_access_time", lambda: datetime(2026, 1, 15, 6, tzinfo=UTC)
    )
    scan(accounts, generate(accounts).pass_token)
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (2,)


def test_daily_entry_limit_is_per_member(database, accounts):
    scan(accounts, generate(accounts).pass_token)
    with psycopg.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO memberships (member_id, plan_id, start_date, end_date)
            SELECT %s, plan_id, start_date, end_date FROM memberships
            WHERE membership_id = %s
            """,
            (accounts["other_id"], accounts["membership_id"]),
        )
    other = {
        **accounts,
        "member": AuthenticatedIdentity(f"member:{accounts['other_id']}", Role.MEMBER),
    }
    scan(other, generate(other).pass_token)
    with pytest.raises(DailyCheckInLimitError):
        generate(other)
    with psycopg.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM check_ins").fetchone() == (2,)
