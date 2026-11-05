import asyncio
import importlib
import json

import pytest
from fastapi import FastAPI

from app.core.exceptions import (
    AuthError,
    DomainError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
)
from app.routers.error_handlers import register_error_handlers


def request(app, method, path, body=None, token=None):
    """Exercise the complete ASGI stack without a running server or Redis."""

    async def run():
        messages = []
        payload = json.dumps(body).encode() if body is not None else b""
        headers = [(b"content-type", b"application/json")]
        if token is not None:
            headers.append((b"authorization", f"Bearer {token}".encode()))
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": payload, "more_body": False}
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": headers,
                "server": ("test", 80),
                "client": ("test", 1234),
                "root_path": "",
            },
            receive,
            send,
        )
        start = next(m for m in messages if m["type"] == "http.response.start")
        data = b"".join(
            m.get("body", b"") for m in messages if m["type"] == "http.response.body"
        )
        return start["status"], dict(start["headers"]), json.loads(data)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "error",
    [
        DomainError,
        AuthError,
        InvalidCredentialsError,
        InvalidTokenError,
        TokenExpiredError,
    ],
)
def test_domain_errors_are_translated(error):
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/error")
    def fail():
        raise error("Test error")

    status, headers, body = request(app, "GET", "/error")
    assert status == (401 if issubclass(error, AuthError) else 400)
    assert body == {"detail": "Test error"}
    assert headers.get(b"www-authenticate") == (
        b"Bearer" if issubclass(error, AuthError) else None
    )


@pytest.fixture
def auth_app(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-error-handlers-at-least-32-bytes")
    return importlib.import_module("app.main").app


def test_invalid_login(auth_app):
    status, headers, body = request(
        auth_app,
        "POST",
        "/auth/login",
        {
            "username": "demo",
            "password": "wrong",
        },
    )
    assert status == 401
    assert headers[b"www-authenticate"] == b"Bearer"
    assert body == {"detail": "Invalid username or password"}


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/protected", "GET"),
        ("/auth/refresh", "POST"),
    ],
)
@pytest.mark.parametrize("expired", [False, True])
def test_invalid_and_expired_tokens(auth_app, path, method, expired):
    from app.infrastructure.auth.authentication import create_token

    kind = "access" if method == "GET" else "refresh"
    token = create_token("demo", kind, -60)[0] if expired else "invalid-token"
    status, headers, body = request(
        auth_app,
        method,
        path,
        body={"refresh_token": token} if method == "POST" else None,
        token=token if method == "GET" else None,
    )
    assert status == 401
    assert headers[b"www-authenticate"] == b"Bearer"
    assert body == {
        "detail": f"{kind.capitalize()} token expired"
        if expired
        else f"Invalid {kind} token"
    }


def test_missing_access_token(auth_app):
    status, headers, body = request(auth_app, "GET", "/api/protected")
    assert status == 401
    assert headers[b"www-authenticate"] == b"Bearer"
    assert body == {"detail": "Bearer access token required"}


def test_validation_still_returns_422(auth_app):
    status, _, _ = request(auth_app, "POST", "/auth/login", {})
    assert status == 422


def test_valid_access_token(auth_app, monkeypatch):
    from app.infrastructure.auth.authentication import create_token
    from app.services.auth_service import refresh_token_repository

    monkeypatch.setattr(
        refresh_token_repository, "is_access_token_active", lambda token_id: True
    )
    token = create_token("demo", "access", 600)[0]
    status, _, body = request(auth_app, "GET", "/api/protected", token=token)
    assert status == 200
    assert body == {"message": "Access granted", "username": "demo"}
