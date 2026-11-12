from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from psycopg.errors import CheckViolation, ExclusionViolation, ForeignKeyViolation

from app.core.exceptions import (
    InvalidMembershipDatesError,
    MemberNotFoundError,
    MembershipOverlapError,
    PlanNotFoundError,
)
from app.infrastructure.memberships import repository


@pytest.fixture
def connection(monkeypatch):
    context = MagicMock()
    connection = context.return_value.__enter__.return_value
    monkeypatch.setattr(repository, "get_connection", context)
    return connection


def test_insert_is_parameterized(connection):
    row = {"membership_id": 1}
    connection.execute.return_value.fetchone.return_value = row
    assert (
        repository.membership_repository.create(
            42, 7, date(2026, 1, 1), date(2026, 1, 31)
        )
        == row
    )
    lock_query, lock_parameters = connection.execute.call_args_list[0].args
    assert "FOR NO KEY UPDATE" in lock_query
    assert lock_parameters == (42,)
    query, parameters = connection.execute.call_args.args
    assert parameters == (42, 7, date(2026, 1, 1), date(2026, 1, 31))
    assert "VALUES (%s, %s, %s, %s)" in query


@pytest.mark.parametrize(
    "error_type,constraint,expected",
    [
        (ForeignKeyViolation, "memberships_member_id_fkey", MemberNotFoundError),
        (ForeignKeyViolation, "memberships_plan_id_fkey", PlanNotFoundError),
        (ExclusionViolation, "no_overlap", MembershipOverlapError),
        (CheckViolation, "memberships_check", InvalidMembershipDatesError),
    ],
)
def test_constraint_errors_become_domain_errors(
    connection, error_type, constraint, expected
):
    class ConstraintError(error_type):
        @property
        def diag(self):
            return SimpleNamespace(constraint_name=constraint)

    connection.execute.side_effect = ConstraintError("Database internals")
    with pytest.raises(expected):
        repository.membership_repository.create(
            1, 1, date(2026, 1, 1), date(2026, 1, 31)
        )


def test_unrelated_constraint_is_not_misreported(connection):
    class UnknownForeignKey(ForeignKeyViolation):
        @property
        def diag(self):
            return SimpleNamespace(constraint_name="another_constraint")

    connection.execute.side_effect = UnknownForeignKey()
    with pytest.raises(UnknownForeignKey):
        repository.membership_repository.create(
            1, 1, date(2026, 1, 1), date(2026, 1, 31)
        )
