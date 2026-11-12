"""Pool de conexiones y transacciones compartido por proceso."""

import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.exceptions import StorageUnavailableError

_pool: ConnectionPool[Connection[dict[str, Any]]] | None = None
_pool_lock = Lock()


def _pool_settings() -> tuple[int, int, float]:
    try:
        minimum = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
        maximum = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
        timeout = float(os.getenv("DB_POOL_TIMEOUT_SECONDS", "5"))
    except ValueError as error:
        raise RuntimeError("Database pool settings must be valid numbers") from error
    if minimum < 1 or maximum < minimum:
        raise RuntimeError("Database pool sizes must satisfy 1 <= min_size <= max_size")
    if not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeError(
            "DB_POOL_TIMEOUT_SECONDS must be finite and greater than zero"
        )
    return minimum, maximum, timeout


def open_pool() -> None:
    """Inicia el pool sin esperar conectividad; nunca se abre al importar módulos."""
    global _pool
    with _pool_lock:
        if _pool is not None and not _pool.closed:
            return
        minimum, maximum, timeout = _pool_settings()
        database_url = os.getenv("DATABASE_URL", "")
        if not database_url:
            return
        pool = ConnectionPool[Connection[dict[str, Any]]](
            conninfo=database_url,
            kwargs={"row_factory": dict_row, "connect_timeout": 5},
            min_size=minimum,
            max_size=maximum,
            timeout=timeout,
            open=False,
            check=ConnectionPool[Connection[dict[str, Any]]].check_connection,
        )
        try:
            pool.open(wait=False)
        except Exception:
            pool.close()
            raise
        _pool = pool


def close_pool() -> None:
    """Libera el pool y sus hilos; se puede llamar más de una vez."""
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.close(timeout=5)


@contextmanager
def get_connection() -> Iterator[Connection[dict[str, Any]]]:
    """Presta una conexión; confirma o revierte antes de devolverla al pool."""
    pool = _pool
    if pool is None:
        raise StorageUnavailableError()
    try:
        with pool.connection() as connection:
            yield connection
    except (psycopg.OperationalError, psycopg.InterfaceError) as error:
        # Incluye PoolTimeout, PoolClosed y TooManyRequests, sin exponer el DSN.
        raise StorageUnavailableError() from error
