import psycopg
import pytest

from app.core.exceptions import StorageUnavailableError
from app.infrastructure.database import db


@pytest.fixture
def single_pool(database, monkeypatch):
    db.close_pool()
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "1")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "0.1")
    db.open_pool()
    # La espera de conectividad solo corresponde al fixture, nunca al arranque HTTP.
    db._pool.wait(timeout=5)
    return db._pool


def test_reuses_backend_and_preserves_commit_and_rollback(single_pool):
    with db.get_connection() as connection:
        first_pid = connection.execute("SELECT pg_backend_pid() AS pid").fetchone()[
            "pid"
        ]
        connection.execute("CREATE TABLE pool_test (value INTEGER NOT NULL)")
        connection.execute("INSERT INTO pool_test VALUES (1)")
    with db.get_connection() as connection:
        assert (
            connection.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            == first_pid
        )
        assert connection.execute("SELECT value FROM pool_test").fetchone() == {
            "value": 1
        }
    with pytest.raises(ValueError, match="rollback"), db.get_connection() as connection:
        connection.execute("INSERT INTO pool_test VALUES (2)")
        raise ValueError("rollback")
    with db.get_connection() as connection:
        assert connection.execute(
            "SELECT count(*) AS total FROM pool_test"
        ).fetchone() == {"total": 1}
        assert (
            connection.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            == first_pid
        )


def test_sql_error_does_not_poison_reused_connection(single_pool):
    with db.get_connection() as connection:
        first_pid = connection.info.backend_pid
    with (
        pytest.raises(psycopg.errors.DivisionByZero),
        db.get_connection() as connection,
    ):
        connection.execute("SELECT 1 / 0")
    with db.get_connection() as connection:
        assert connection.info.backend_pid == first_pid
        assert connection.execute("SELECT 42 AS value").fetchone() == {"value": 42}


def test_exhaustion_is_bounded_and_pool_recovers(single_pool):
    with (
        db.get_connection(),
        pytest.raises(StorageUnavailableError),
        db.get_connection(),
    ):
        pass
    with db.get_connection() as connection:
        assert connection.execute("SELECT 1 AS value").fetchone() == {"value": 1}
    assert single_pool.get_stats()["pool_size"] == 1


def test_broken_connection_is_replaced(single_pool):
    with db.get_connection() as connection:
        first_pid = connection.info.backend_pid
        connection.close()
    single_pool.wait(timeout=5)
    with db.get_connection() as connection:
        assert connection.info.backend_pid != first_pid
        assert connection.execute("SELECT 1 AS value").fetchone() == {"value": 1}


def test_stale_connection_detected_on_checkout(single_pool, database):
    with db.get_connection() as connection:
        first_pid = connection.info.backend_pid
    with psycopg.connect(database, autocommit=True) as admin:
        assert admin.execute(
            "SELECT pg_terminate_backend(%s)", (first_pid,)
        ).fetchone() == (True,)
    # Se permite más tiempo aquí para crear la conexión que sustituye a la rota.
    single_pool.timeout = 5
    with db.get_connection() as connection:
        assert connection.info.backend_pid != first_pid
        assert connection.execute("SELECT 1 AS value").fetchone() == {"value": 1}
