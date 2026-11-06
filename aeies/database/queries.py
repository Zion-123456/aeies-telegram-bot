"""Transactional PostgreSQL adapter. Exceptions never include connection details."""

from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict
import certifi


class DatabaseUnavailable(RuntimeError):
    pass


class Duplicate(ValueError):
    pass


def connect(url, **kwargs):
    """Require authenticated TLS for remote databases; permit local test sockets."""
    info = conninfo_to_dict(url)
    host = info.get("hostaddr") or info.get("host", "")
    if host not in ("", "localhost", "127.0.0.1", "::1") and not host.startswith("/"):
        if info.get("sslmode", "verify-full") != "verify-full":
            raise ValueError(
                "Remote PostgreSQL requires sslmode=verify-full and a trusted CA certificate."
            )
        kwargs["sslmode"] = "verify-full"
        kwargs["sslrootcert"] = info.get("sslrootcert") or certifi.where()
    return psycopg.connect(url, **kwargs)


class Database:
    def __init__(self, url):
        self._url = url

    @contextmanager
    def transaction(self):
        try:
            with connect(
                self._url, row_factory=dict_row, connect_timeout=10
            ) as connection:
                connection.execute("SET search_path TO aeies, pg_catalog")
                connection.execute("SET statement_timeout TO '15s'")
                yield connection
        except psycopg.errors.UniqueViolation:
            raise Duplicate(
                "That record already exists; check for a duplicate."
            ) from None
        except psycopg.Error:
            raise DatabaseUnavailable(
                "Database operation failed. Please retry later."
            ) from None


def one(connection, sql, params=()):
    return connection.execute(sql, params).fetchone()


def rows(connection, sql, params=()):
    return connection.execute(sql, params).fetchall()
