import importlib
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import InvalidCredentialsError
from app.core.identity import AuthenticatedIdentity
from app.core.passwords import password_hasher
from app.core.roles import Role
from app.routers.error_handlers import register_error_handlers
from app.schemas.auth import TokenPairResponse


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-roles-auth-at-least-32-bytes")
    return importlib.import_module("app.services.auth_service")


@pytest.fixture
def client(auth):
    with TestClient(importlib.import_module("app.main").app) as client:
        yield client


@pytest.fixture(scope="module")
def password_hash():
    return password_hasher.hash("password123")


def account(password_hash, role="Staff", active=True):
    return {
        "employee_id": 42,
        "password_hash": password_hash,
        "role": role,
        "is_active": active,
    }


@pytest.mark.parametrize("role,expected", [("Admin", "admin"), ("Staff", "staff")])
def test_employee_login_uses_database_role(
    auth, client, monkeypatch, password_hash, role, expected
):
    monkeypatch.setattr(
        auth.employee_repository,
        "find_credentials_by_email",
        lambda email: account(password_hash, role),
    )
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    response = client.post(
        "/auth/employees/login",
        data={
            "username": "same@example.com",
            "password": "password123",
            "role": "member",
        },
    )
    assert response.status_code == 200
    result = auth.authenticate_employee("same@example.com", "password123")
    assert isinstance(result, TokenPairResponse)
    assert auth.decode_token(result.access_token)["role"] == expected
    access = auth.decode_token(response.json()["access_token"])
    refresh = auth.decode_token(response.json()["refresh_token"])
    assert access["role"] == expected
    assert access["sub"] == refresh["sub"] == "employee:42"
    assert "role" not in refresh
    assert add_pair.call_count == 2


@pytest.mark.parametrize("case", ["missing", "inactive", "password", "role", "hash"])
def test_employee_login_rejects_invalid_credentials(
    auth, client, monkeypatch, password_hash, case
):
    row = account(
        password_hash, "Owner" if case == "role" else "Staff", case != "inactive"
    )
    if case == "hash":
        row["password_hash"] = "invalid-hash"
    monkeypatch.setattr(
        auth.employee_repository,
        "find_credentials_by_email",
        lambda email: None if case == "missing" else row,
    )
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    response = client.post(
        "/auth/employees/login",
        data={
            "username": "a@example.com",
            "password": "wrong" if case == "password" else "password123",
        },
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}
    with pytest.raises(InvalidCredentialsError, match="Invalid username or password"):
        auth.authenticate_employee(
            "a@example.com", "wrong" if case == "password" else "password123"
        )
    add_pair.assert_not_called()


def test_same_email_has_separate_identities(auth, client, monkeypatch, password_hash):
    monkeypatch.setattr(
        auth.employee_repository,
        "find_credentials_by_email",
        lambda email: account(password_hash),
    )
    monkeypatch.setattr(
        auth.member_repository,
        "find_credentials_by_email",
        lambda email: {
            "member_id": 42,
            "password_hash": password_hash,
            "is_active": True,
        },
    )
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", lambda *args: None)
    subjects = []
    for path in ["/auth/login", "/auth/employees/login"]:
        response = client.post(
            path, data={"username": "same@example.com", "password": "password123"}
        )
        assert response.status_code == 200
        subjects.append(auth.decode_token(response.json()["access_token"])["sub"])
    assert subjects == ["member:42", "employee:42"]


@pytest.mark.parametrize(
    "role,subject,status",
    [
        (Role.MEMBER, "member:1", 403),
        (Role.STAFF, "employee:1", 200),
        (Role.ADMIN, "employee:1", 200),
    ],
)
def test_employee_endpoint_permissions(
    auth, client, monkeypatch, role, subject, status
):
    active = MagicMock(return_value=True)
    monkeypatch.setattr(auth.refresh_token_repository, "is_access_token_active", active)
    token = auth.create_token(subject, "access", 600, role=role)[0]
    response = client.get(
        "/api/employees/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status
    active.assert_called_once()  # La dependencia valida una sola vez, sin middleware.


@pytest.mark.parametrize(
    "subject,role",
    [
        ("member:1", None),
        ("member:1", "owner"),
        ("member:1", "admin"),
        ("employee:1", "member"),
        ("old@example.com", "member"),
        ("member:0", "member"),
    ],
)
def test_invalid_access_claims(auth, client, monkeypatch, subject, role):
    token = auth.create_token("member:1", "access", 600, role=Role.MEMBER)[0]
    claims = auth.decode_token(token)
    claims["sub"] = subject
    if role is None:
        claims.pop("role")
    else:
        claims["role"] = role
    from app.core.auth_config import JWT_ALGORITHM, JWT_SECRET

    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    active = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "is_access_token_active", active)
    assert (
        client.get(
            "/api/protected", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )
    active.assert_not_called()


@pytest.mark.parametrize("kind", ["member", "employee"])
def test_refresh_rotates_once_and_resolves_identity(auth, client, monkeypatch, kind):
    repository = (
        auth.member_repository if kind == "member" else auth.employee_repository
    )
    monkeypatch.setattr(
        repository,
        "find_identity_by_id",
        lambda identifier: {"is_active": True, "role": "Staff"},
    )
    consumed = set()

    def consume(jti):
        if jti in consumed:
            return False
        consumed.add(jti)
        return True

    monkeypatch.setattr(auth.refresh_token_repository, "consume_refresh", consume)
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    token = auth.create_token(f"{kind}:42", "refresh", 600)[0]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/auth/refresh", headers=headers)
    assert response.status_code == 200
    claims = auth.decode_token(response.json()["access_token"])
    assert claims["sub"] == f"{kind}:42"
    assert claims["role"] == ("member" if kind == "member" else "staff")
    assert client.post("/auth/refresh", headers=headers).status_code == 401
    add_pair.assert_called_once()


@pytest.mark.parametrize("kind", ["member", "employee"])
@pytest.mark.parametrize("row", [None, {"is_active": False, "role": "Staff"}])
def test_refresh_rejects_deleted_or_inactive_account(
    auth, client, monkeypatch, kind, row
):
    repository = (
        auth.member_repository if kind == "member" else auth.employee_repository
    )
    monkeypatch.setattr(repository, "find_identity_by_id", lambda identifier: row)
    add_pair = MagicMock()
    monkeypatch.setattr(auth.refresh_token_repository, "add_pair", add_pair)
    token = auth.create_token(f"{kind}:42", "refresh", 600)[0]
    assert (
        client.post(
            "/auth/refresh", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )
    add_pair.assert_not_called()


def test_access_revocation_and_token_types(auth, client, monkeypatch):
    monkeypatch.setattr(
        auth.refresh_token_repository, "is_access_token_active", lambda jti: False
    )
    access = auth.create_token("member:1", "access", 600, role=Role.MEMBER)[0]
    refresh = auth.create_token("member:1", "refresh", 600)[0]
    for path, method, token in [
        ("/api/protected", "GET", access),
        ("/api/protected", "GET", refresh),
        ("/auth/refresh", "POST", access),
    ]:
        assert (
            client.request(
                method, path, headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 401
        )


def test_admin_only_dependency(auth):
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/admin", dependencies=[Depends(auth.require_roles(Role.ADMIN))])
    def admin_only():
        return {"ok": True}

    with TestClient(app) as client:
        for role, expected in [(Role.STAFF, 403), (Role.ADMIN, 200)]:
            app.dependency_overrides[auth.verify_access_token] = lambda role=role: (
                AuthenticatedIdentity("employee:1", role)
            )
            assert client.get("/admin").status_code == expected


def test_employee_queries_are_parameterized(monkeypatch):
    from app.infrastructure.employees import repository

    context = MagicMock()
    execute = context.return_value.__enter__.return_value.execute
    execute.return_value.fetchone.return_value = None
    monkeypatch.setattr(repository, "get_connection", context)
    repository.employee_repository.find_credentials_by_email("' OR TRUE --")
    query, parameters = execute.call_args.args
    assert parameters == ("' OR TRUE --",)
    assert parameters[0] not in query
    repository.employee_repository.find_identity_by_id(42)
    assert execute.call_args.args[1] == (42,)
