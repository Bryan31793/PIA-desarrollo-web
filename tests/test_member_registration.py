import importlib
from datetime import UTC, datetime
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import MemberEmailAlreadyExistsError, StorageUnavailableError
from app.infrastructure.database import db
from app.infrastructure.members import repository
from app.services.member_service import password_hasher


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET", "test-secret-for-member-registration-at-least-32-bytes"
    )
    app = importlib.import_module("app.main").app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def saved_members(monkeypatch):
    saved = []

    def create(name, email, password_hash):
        if any(member["email"] == email for member in saved):
            raise MemberEmailAlreadyExistsError()
        member = {
            "member_id": len(saved) + 1,
            "name": name,
            "email": email,
            "password_hash": password_hash,
            "is_active": True,
            "created_at": datetime.now(UTC),
        }
        saved.append(member)
        return member

    monkeypatch.setattr(repository.member_repository, "create", create)
    return saved


def test_public_registration_hashes_password_and_returns_public_fields(
    client, saved_members
):
    response = client.post(
        "/auth/register",
        json={
            "name": " Ana Pérez ",
            "email": "ANA@example.com",
            "password": "a secure password",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ana Pérez"
    assert body["email"] == "ana@example.com"
    assert body["is_active"] is True
    assert body["member_id"] == 1
    assert body["created_at"]
    assert set(body) == {"member_id", "name", "email", "is_active", "created_at"}
    stored_hash = saved_members[0]["password_hash"]
    assert stored_hash.startswith("$argon2id$")
    assert password_hasher.verify("a secure password", stored_hash)
    assert not password_hasher.verify("wrong password", stored_hash)


def test_registration_rejects_duplicate_email_case_insensitively(client, saved_members):
    data = {"name": "Ana", "email": "ana@example.com", "password": "password123"}
    assert client.post("/auth/register", json=data).status_code == 201
    data["email"] = "ANA@EXAMPLE.COM"
    response = client.post("/auth/register", json=data)
    assert response.status_code == 409
    assert response.json() == {"detail": "Email is already registered"}
    assert len(saved_members) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "   "},
        {"name": "x" * 101},
        {"email": "invalid"},
        {"password": "short"},
        {"password": "x" * 129},
        {"password": None},
        {"role_id": 1},
        {"is_active": False},
    ],
)
def test_registration_rejects_invalid_input_before_persistence(
    client, saved_members, changes
):
    data = {"name": "Ana", "email": "ana@example.com", "password": "password123"}
    response = client.post("/auth/register", json=data | changes)
    assert response.status_code == 422
    assert saved_members == []


def test_registration_requires_fields(client, saved_members):
    assert client.post("/auth/register", json={}).status_code == 422
    assert saved_members == []


def test_registration_reports_storage_unavailability(client, monkeypatch):
    def unavailable(*args):
        raise StorageUnavailableError()

    monkeypatch.setattr(repository.member_repository, "create", unavailable)
    response = client.post(
        "/auth/register",
        json={"name": "Ana", "email": "ana@example.com", "password": "password123"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Storage is temporarily unavailable"}


def test_repository_uses_parameters_and_returns_only_public_columns(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    connection = MagicMock()
    row = {"member_id": 1}
    connection.execute.return_value.fetchone.return_value = row
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = connection
    monkeypatch.setattr(db, "_pool", pool)
    name = "O'Brien"
    assert repository.member_repository.create(name, "ana@example.com", "hash") == row
    query, params = connection.execute.call_args.args
    assert params == (name, "ana@example.com", "hash")
    assert name not in query
    assert "password_hash" not in query.split("RETURNING")[1]
    pool.connection.return_value.__exit__.assert_called_once_with(None, None, None)


def test_repository_requires_database_configuration(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(StorageUnavailableError):
        repository.member_repository.create("Ana", "ana@example.com", "hash")


def test_repository_translates_connection_failure(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    pool = MagicMock()
    pool.connection.side_effect = psycopg.OperationalError("private connection details")
    monkeypatch.setattr(db, "_pool", pool)
    with pytest.raises(
        StorageUnavailableError, match="Storage is temporarily unavailable"
    ):
        repository.member_repository.create("Ana", "ana@example.com", "hash")
