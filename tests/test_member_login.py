import importlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import InvalidCredentialsError, StorageUnavailableError
from app.core.passwords import password_hasher
from app.infrastructure.members import repository
from app.schemas.auth import TokenPairResponse


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-member-login-at-least-32-bytes")
    return importlib.import_module("app.services.auth_service")


@pytest.fixture
def client(auth):
    with TestClient(importlib.import_module("app.main").app) as client:
        yield client


@pytest.fixture(scope="module")
def stored_hash():
    return password_hasher.hash("una contraseña segura")


@pytest.mark.parametrize(
    "exists,active,password,expected",
    [
        (True, True, "una contraseña segura", True),
        (True, True, "incorrecta", False),
        (True, False, "una contraseña segura", False),
        (False, True, "una contraseña segura", False),
        (False, True, "demo-password", False),
    ],
)
def test_authenticate_checks_database_hash_and_active_status(
    auth, monkeypatch, stored_hash, exists, active, password, expected
):
    find = MagicMock(
        return_value={"member_id": 1, "password_hash": stored_hash, "is_active": active}
        if exists
        else None
    )
    monkeypatch.setattr(repository.member_repository, "find_credentials_by_email", find)
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    if expected:
        response = auth.authenticate("ana@example.com", password)
        assert isinstance(response, TokenPairResponse)
        claims = auth.decode_token(response.access_token)
        assert claims["sub"] == "member:1"
        assert claims["role"] == "member"
        add_pair.assert_called_once()
    else:
        with pytest.raises(
            InvalidCredentialsError, match="Invalid username or password"
        ):
            auth.authenticate("ana@example.com", password)
        add_pair.assert_not_called()
    find.assert_called_once_with("ana@example.com")


def test_authenticate_rejects_unknown_hash(auth, monkeypatch):
    monkeypatch.setattr(
        repository.member_repository,
        "find_credentials_by_email",
        lambda email: {
            "member_id": 1,
            "password_hash": "not-a-password-hash",
            "is_active": True,
        },
    )
    with pytest.raises(InvalidCredentialsError, match="Invalid username or password"):
        auth.authenticate("ana@example.com", "not-a-password-hash")


def test_login_issues_real_tokens_for_valid_member(
    client, auth, monkeypatch, stored_hash
):
    monkeypatch.setattr(
        repository.member_repository,
        "find_credentials_by_email",
        lambda email: {"member_id": 1, "password_hash": stored_hash, "is_active": True},
    )
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    response = client.post(
        "/auth/login",
        data={"username": "ana@example.com", "password": "una contraseña segura"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == auth.ACCESS_TOKEN_SECONDS
    for key, kind in [("access_token", "access"), ("refresh_token", "refresh")]:
        claims = auth.decode_token(body[key])
        assert claims["sub"] == "member:1"
        if kind == "access":
            assert claims["role"] == "member"
        assert claims["token_type"] == kind
    add_pair.assert_called_once()


@pytest.mark.parametrize("case", ["missing", "wrong-password", "inactive"])
def test_login_returns_same_401_without_issuing_tokens(
    client, auth, monkeypatch, stored_hash, case
):
    monkeypatch.setattr(
        repository.member_repository,
        "find_credentials_by_email",
        lambda email: (
            None
            if case == "missing"
            else {
                "member_id": 1,
                "password_hash": stored_hash,
                "is_active": case != "inactive",
            }
        ),
    )
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    response = client.post(
        "/auth/login",
        data={
            "username": "ana@example.com",
            "password": "wrong"
            if case == "wrong-password"
            else "una contraseña segura",
        },
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}
    assert response.headers["www-authenticate"] == "Bearer"
    add_pair.assert_not_called()


def test_login_reports_database_unavailability(client, auth, monkeypatch):
    def unavailable(email):
        raise StorageUnavailableError()

    monkeypatch.setattr(
        repository.member_repository, "find_credentials_by_email", unavailable
    )
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    response = client.post(
        "/auth/login", data={"username": "ana@example.com", "password": "password123"}
    )
    assert response.status_code == 503
    add_pair.assert_not_called()


def test_credentials_query_is_parameterized(monkeypatch):
    context = MagicMock()
    connection = context.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = None
    monkeypatch.setattr(repository, "get_connection", context)
    email = "' OR TRUE --"
    assert repository.member_repository.find_credentials_by_email(email) is None
    query, parameters = connection.execute.call_args.args
    assert parameters == (email,)
    assert email not in query
