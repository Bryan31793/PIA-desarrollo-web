import importlib
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg_pool import PoolClosed, PoolTimeout, TooManyRequests

from app.core.exceptions import StorageUnavailableError
from app.infrastructure.database import db


@pytest.fixture
def pool_factory(monkeypatch):
    factory = MagicMock()
    factory.__getitem__.return_value = factory
    factory.return_value.closed = False
    monkeypatch.setattr(db, "ConnectionPool", factory)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    return factory


def test_pool_is_explicit_non_blocking_and_reused(pool_factory):
    db.open_pool()
    db.open_pool()
    pool_factory.assert_called_once_with(
        conninfo="postgresql://test",
        kwargs={"row_factory": dict_row, "connect_timeout": 5},
        min_size=1,
        max_size=10,
        timeout=5.0,
        open=False,
        check=pool_factory.check_connection,
    )
    pool_factory.return_value.open.assert_called_once_with(wait=False)
    first = db._pool
    with db.get_connection() as connection:
        assert connection is first.connection.return_value.__enter__.return_value
    with db.get_connection():
        pass
    assert first.connection.call_count == 2
    assert db._pool is first


def test_pool_settings_are_configurable(pool_factory, monkeypatch):
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "2")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "4")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "0.25")
    db.open_pool()
    assert pool_factory.call_args.kwargs["min_size"] == 2
    assert pool_factory.call_args.kwargs["max_size"] == 4
    assert pool_factory.call_args.kwargs["timeout"] == 0.25


@pytest.mark.parametrize(
    "settings",
    [
        {"DB_POOL_MIN_SIZE": "0"},
        {"DB_POOL_MIN_SIZE": "11"},
        {"DB_POOL_MAX_SIZE": "0"},
        {"DB_POOL_MAX_SIZE": "1.5"},
        {"DB_POOL_TIMEOUT_SECONDS": "0"},
        {"DB_POOL_TIMEOUT_SECONDS": "nan"},
        {"DB_POOL_TIMEOUT_SECONDS": "inf"},
        {"DB_POOL_TIMEOUT_SECONDS": "bad"},
    ],
)
def test_invalid_settings_fail_before_creating_pool(
    pool_factory, monkeypatch, settings
):
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        db.open_pool()
    pool_factory.assert_not_called()


def test_missing_url_starts_without_database_pool(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(db, "ConnectionPool", factory)
    db.open_pool()
    factory.assert_not_called()
    with pytest.raises(StorageUnavailableError), db.get_connection():
        pass


def test_close_is_idempotent_and_allows_fresh_start(pool_factory):
    db.open_pool()
    pool = db._pool
    db.close_pool()
    db.close_pool()
    pool.close.assert_called_once_with(timeout=5)
    assert db._pool is None
    with pytest.raises(StorageUnavailableError), db.get_connection():
        pass
    db.open_pool()
    assert pool_factory.call_count == 2


@pytest.mark.parametrize(
    "error",
    [
        PoolTimeout,
        PoolClosed,
        TooManyRequests,
        psycopg.OperationalError,
        psycopg.InterfaceError,
    ],
)
def test_pool_errors_are_domain_errors_without_sensitive_details(pool_factory, error):
    db.open_pool()
    pool_factory.return_value.connection.side_effect = error(
        "private connection details"
    )
    with (
        pytest.raises(
            StorageUnavailableError, match="Storage is temporarily unavailable"
        ) as caught,
        db.get_connection(),
    ):
        pass
    assert "private" not in str(caught.value)


def test_business_exception_reaches_context_for_rollback(pool_factory):
    db.open_pool()
    context = pool_factory.return_value.connection.return_value
    context.__exit__.return_value = False
    error = ValueError("business validation failed")
    with pytest.raises(ValueError, match="business validation"), db.get_connection():
        raise error
    assert context.__exit__.call_args.args[:2] == (ValueError, error)


def test_failed_pool_open_closes_resources(pool_factory):
    pool_factory.return_value.open.side_effect = RuntimeError("Cannot start worker")
    with pytest.raises(RuntimeError, match="Cannot start worker"):
        db.open_pool()
    pool_factory.return_value.close.assert_called_once()
    assert db._pool is None


def test_fastapi_lifespan_manages_pool(pool_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-pool-lifespan-at-least-32-bytes")
    app = importlib.import_module("app.main").app
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        pool_factory.return_value.open.assert_called_once_with(wait=False)
        pool_factory.return_value.close.assert_not_called()
    pool_factory.return_value.close.assert_called_once_with(timeout=5)


def test_fastapi_starts_without_url_and_database_operation_returns_503(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-pool-lifespan-at-least-32-bytes")
    app = importlib.import_module("app.main").app
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        response = client.post(
            "/auth/login",
            data={"username": "ana@example.com", "password": "password123"},
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "Storage is temporarily unavailable"}


def test_fastapi_starts_when_database_connection_is_unavailable(
    pool_factory, monkeypatch
):
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-pool-lifespan-at-least-32-bytes")
    pool_factory.return_value.connection.side_effect = PoolTimeout(
        "database unavailable"
    )
    app = importlib.import_module("app.main").app
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert (
            client.post(
                "/auth/login",
                data={"username": "a@example.com", "password": "password123"},
            ).status_code
            == 503
        )
