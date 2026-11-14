"""Fail-closed, disposable PostgreSQL helpers for the opt-in integration suite.

Local usage (credentials stay outside the repository)::

    set -a; . "$HOME/.config/conformdag/c26-postgres.env"; set +a
    mise run test:postgres

Tests use ``postgres_empty_database`` when they need a genuinely empty
``conformdag_c26_<uuid>`` database, or ``postgres_database`` when Alembic
initialization is part of setup. Both fixtures own a unique database through
``PostgresAdmin.disposable_database`` and dispose tracked engines before
dropping only the exact database name created by the fixture.
"""

from __future__ import annotations

import ipaddress
import os
import re
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import psycopg
from alembic.util.exc import CommandError
from psycopg import sql
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from conformdag.platform.persistence.migrations import (
    create_session_factory as production_create_session_factory,
)
from conformdag.platform.persistence.migrations import (
    initialize_session_factory as production_initialize_session_factory,
)

TEST_DSN_ENV = "CONFORMDAG_TEST_POSTGRES_DSN"
_LIBPQ_ROUTING_OVERRIDES = ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")
DATABASE_PREFIX = "conformdag_c26_"
_DATABASE_NAME_PATTERN = re.compile(r"conformdag_c26_[0-9a-f]{32}\Z")
_STATEMENT_TIMEOUT_MS = 5_000
_LOCK_TIMEOUT_MS = 2_000
_CONNECT_TIMEOUT_SECONDS = "3"
_PGOPTIONS = f"-c statement_timeout={_STATEMENT_TIMEOUT_MS} -c lock_timeout={_LOCK_TIMEOUT_MS}"


class PostgresHarnessError(RuntimeError):
    """A safe-to-display PostgreSQL harness configuration or lifecycle error."""


def admin_url_from_environment(environ: Mapping[str, str]) -> URL:
    """Return the dedicated test-maintenance URL; never fall back to app DSNs."""
    dsn = environ.get(TEST_DSN_ENV)
    if not dsn:
        raise PostgresHarnessError(
            f"{TEST_DSN_ENV} is required for the explicit PostgreSQL suite; "
            "set it to a dedicated loopback PostgreSQL 17 test-maintenance DSN."
        )
    return validate_admin_dsn(dsn)


def validate_libpq_routing_environment(environ: Mapping[str, str]) -> None:
    """Reject libpq settings that could redirect an otherwise-safe DSN."""
    for variable in _LIBPQ_ROUTING_OVERRIDES:
        if environ.get(variable):
            raise PostgresHarnessError(
                f"Unsafe libpq routing override {variable} is set; unset it before running the PostgreSQL suite."
            )


def validate_admin_dsn(dsn: str | None) -> URL:
    """Validate a local, test-only PostgreSQL 17 maintenance connection string."""
    if not dsn:
        raise PostgresHarnessError(f"{TEST_DSN_ENV} is required for the explicit PostgreSQL suite.")
    if any(character in dsn for character in "?#") or any(ord(character) < 32 for character in dsn):
        raise PostgresHarnessError(
            f"{TEST_DSN_ENV} must not contain URL query parameters, fragments, or control characters."
        )
    try:
        url = make_url(dsn)
    except (ArgumentError, ValueError):
        raise PostgresHarnessError(f"{TEST_DSN_ENV} is not a valid PostgreSQL test DSN.") from None

    if url.drivername != "postgresql+psycopg":
        raise PostgresHarnessError(f"{TEST_DSN_ENV} must use the existing psycopg 3 PostgreSQL driver.")
    host = url.host
    if not host or url.port is None or not 1 <= url.port <= 65_535 or not _is_loopback_host(host):
        raise PostgresHarnessError(
            f"{TEST_DSN_ENV} must specify an explicit loopback host and port; remote/shared servers are refused."
        )
    username = (url.username or "").lower()
    if "c26" not in username or "test" not in username:
        raise PostgresHarnessError(f"{TEST_DSN_ENV} must authenticate as a test-only role containing 'c26' and 'test'.")
    if not url.password:
        raise PostgresHarnessError(f"{TEST_DSN_ENV} must include the dedicated test role's password.")
    database = (url.database or "").lower()
    if database != "postgres" and not (
        "c26" in database and "test" in database and ("maint" in database or "maintenance" in database)
    ):
        raise PostgresHarnessError(
            f"{TEST_DSN_ENV} must connect only to the 'postgres' maintenance database or a clearly named C26 test maintenance database."
        )
    if url.query:
        raise PostgresHarnessError(f"{TEST_DSN_ENV} URL query options are not permitted by the test harness.")
    return url


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_owned_database(name: str, owned_names: set[str]) -> None:
    """Reject cleanup unless this run created the exact generated C26 name."""
    if not _DATABASE_NAME_PATTERN.fullmatch(name) or name not in owned_names:
        raise PostgresHarnessError("Refusing cleanup: database is not owned by this test run or is malformed.")


def validate_server_requirements(version_num: int, createdb: bool) -> None:
    """Require PostgreSQL 17 and the test role's CREATEDB attribute."""
    if version_num // 10_000 != 17:
        raise PostgresHarnessError("The configured PostgreSQL test service must be major version 17.")
    if not createdb:
        raise PostgresHarnessError("The configured test-only maintenance role must have CREATEDB privilege.")


def _empty_engines() -> list[Engine]:
    return []


def _empty_session_factories() -> list[sessionmaker[Session]]:
    return []


@dataclass
class PostgresTestDatabase:
    """One uniquely owned live test database and its tracked SQLAlchemy engines."""

    name: str
    url: URL = field(repr=False)
    _admin: PostgresAdmin = field(repr=False)
    _engines: list[Engine] = field(default_factory=_empty_engines, repr=False)
    _session_factories: list[sessionmaker[Session]] = field(default_factory=_empty_session_factories, repr=False)

    @property
    def factory(self) -> sessionmaker[Session]:
        """The factory initialized through the production Alembic entry point."""
        if not self._session_factories:
            raise PostgresHarnessError("The test database has not been initialized through Alembic.")
        return self._session_factories[0]

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Alias for ``factory`` for explicit session-factory call sites."""
        return self.factory

    def initialize(self) -> sessionmaker[Session]:
        """Initialize migrations using the production function and track its engine."""
        factory = self._initialize_with_production_owner()
        self._track_factory(factory)
        return factory

    def new_session_factory(self, *, initialize: bool = True) -> sessionmaker[Session]:
        """Create another independent production-bound session factory and track it."""
        if initialize:
            factory = self._initialize_with_production_owner()
        else:
            factory = production_create_session_factory(self._connection_string())
        self._track_factory(factory)
        return factory

    def dispose_engines(self) -> None:
        """Dispose every SQLAlchemy engine created through this helper."""
        failed = False
        for engine in self._engines:
            try:
                engine.dispose(close=True)
            except (SQLAlchemyError, psycopg.Error, OSError):
                failed = True
        if failed:
            raise PostgresHarnessError(
                "Could not dispose every tracked PostgreSQL test engine before cleanup."
            ) from None
        self._admin.mark_engines_disposed(self.name)

    def _initialize_with_production_owner(self) -> sessionmaker[Session]:
        try:
            factory = production_initialize_session_factory(self._connection_string())
        except (CommandError, SQLAlchemyError, OSError, RuntimeError, ValueError):
            raise PostgresHarnessError(
                "Production PostgreSQL migration/session-factory initialization failed; "
                "the database name and connection details are intentionally redacted."
            ) from None
        return factory

    def _connection_string(self) -> str:
        return self.url.render_as_string(hide_password=False)

    def _track_factory(self, factory: sessionmaker[Session]) -> None:
        bind = factory.kw.get("bind")
        if not isinstance(bind, Engine):
            raise PostgresHarnessError("Production session factory is not bound to a SQLAlchemy Engine.")
        event.listen(bind, "connect", _apply_test_timeouts)
        self._session_factories.append(factory)
        if bind not in self._engines:
            self._engines.append(bind)
        self._admin.mark_engine_tracked(self.name)


class PostgresAdmin:
    """Session-scoped guarded maintenance connection and fixture-owned DB ledger."""

    def __init__(self, url: URL, engine: Engine) -> None:
        self.url = url
        self.engine = engine
        self.owned_database_names: set[str] = set()
        self._ready_to_drop: set[str] = set()

    def create_database(self) -> PostgresTestDatabase:
        name = f"{DATABASE_PREFIX}{uuid.uuid4().hex}"
        created = False
        try:
            with psycopg.connect(
                self._connection_string(), autocommit=True, options=_PGOPTIONS, connect_timeout=3
            ) as connection:
                connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                self.owned_database_names.add(name)
                self._ready_to_drop.add(name)
                created = True
        except psycopg.Error:
            if created:
                try:
                    self.drop_database(name)
                except PostgresHarnessError:
                    raise PostgresHarnessError(
                        "Database creation cleanup failed visibly; only the newly created owned test database was targeted."
                    ) from None
            raise PostgresHarnessError(
                "Could not create a fresh disposable PostgreSQL test database; check the test role's CREATEDB privilege."
            ) from None
        database_url = self.url.set(database=name)
        return PostgresTestDatabase(name=name, url=database_url, _admin=self)

    @contextmanager
    def disposable_database(self) -> Iterator[PostgresTestDatabase]:
        """Own one fresh database without implicitly running its migrations."""
        database = self.create_database()
        try:
            yield database
        finally:
            database.dispose_engines()
            self.drop_database(database.name)

    def drop_database(self, name: str) -> None:
        validate_owned_database(name, self.owned_database_names)
        if name not in self._ready_to_drop:
            raise PostgresHarnessError("Refusing cleanup until all tracked database engines have been disposed.")
        try:
            with psycopg.connect(
                self._connection_string(), autocommit=True, options=_PGOPTIONS, connect_timeout=3
            ) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        except psycopg.Error:
            raise PostgresHarnessError(
                "Could not drop the owned PostgreSQL test database; cleanup failed visibly and no other database was targeted."
            ) from None
        self.owned_database_names.remove(name)
        self._ready_to_drop.remove(name)

    def mark_engine_tracked(self, name: str) -> None:
        validate_owned_database(name, self.owned_database_names)
        self._ready_to_drop.discard(name)

    def mark_engines_disposed(self, name: str) -> None:
        validate_owned_database(name, self.owned_database_names)
        self._ready_to_drop.add(name)

    def can_drop_database(self, name: str) -> bool:
        """Return whether this run owns the name and all associated engines were disposed."""
        validate_owned_database(name, self.owned_database_names)
        return name in self._ready_to_drop

    def dispose(self) -> None:
        self.engine.dispose(close=True)

    def _connection_string(self) -> str:
        return self.url.set(drivername="postgresql").render_as_string(hide_password=False)


def _apply_test_timeouts(dbapi_connection: Any, _connection_record: Any) -> None:
    """Apply bounded deadlock-safety timeouts to each checked-out test connection."""
    with dbapi_connection.cursor() as cursor:
        cursor.execute(f"SET statement_timeout = '{_STATEMENT_TIMEOUT_MS}ms'")
        cursor.execute(f"SET lock_timeout = '{_LOCK_TIMEOUT_MS}ms'")


def build_admin_engine(url: URL) -> Engine:
    """Create an engine for the guarded maintenance database with bounded IO."""
    return create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": _PGOPTIONS},
    )


def verify_admin_connection(engine: Engine) -> None:
    """Prove loopback service reachability, server major version and CREATEDB."""
    try:
        with engine.connect() as connection:
            version_num, createdb = connection.execute(
                text(
                    "SELECT current_setting('server_version_num')::integer, "
                    "(SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user)"
                )
            ).one()
    except (SQLAlchemyError, psycopg.Error, OSError):
        raise PostgresHarnessError(
            "Cannot authenticate to the configured loopback PostgreSQL test service; "
            "verify it is running, reachable, and the dedicated test credentials are valid."
        ) from None
    validate_server_requirements(int(version_num), bool(createdb))


@contextmanager
def postgres_admin_from_environment(environ: Mapping[str, str]) -> Iterator[PostgresAdmin]:
    """Validate and connect only when a marked test requests PostgreSQL fixtures."""
    validate_libpq_routing_environment(environ)
    previous_options = os.environ.get("PGOPTIONS")
    previous_connect_timeout = os.environ.get("PGCONNECT_TIMEOUT")
    admin: PostgresAdmin | None = None
    try:
        os.environ["PGOPTIONS"] = _PGOPTIONS
        os.environ["PGCONNECT_TIMEOUT"] = _CONNECT_TIMEOUT_SECONDS
        url = admin_url_from_environment(environ)
        try:
            engine = build_admin_engine(url)
        except SQLAlchemyError:
            raise PostgresHarnessError("Could not create the PostgreSQL test-maintenance connection.") from None
        admin = PostgresAdmin(url, engine)
        verify_admin_connection(engine)
        yield admin
    finally:
        cleanup_failure: PostgresHarnessError | None = None
        if admin is not None:
            for database_name in tuple(admin.owned_database_names):
                if not admin.can_drop_database(database_name):
                    cleanup_failure = PostgresHarnessError(
                        "Refusing cleanup because a tracked test database engine was not disposed."
                    )
                    continue
                try:
                    admin.drop_database(database_name)
                except PostgresHarnessError as error:
                    cleanup_failure = error
            try:
                admin.dispose()
            except (SQLAlchemyError, psycopg.Error, OSError):
                cleanup_failure = PostgresHarnessError(
                    "Could not dispose the PostgreSQL maintenance connection cleanly."
                )
        if previous_options is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = previous_options
        if previous_connect_timeout is None:
            os.environ.pop("PGCONNECT_TIMEOUT", None)
        else:
            os.environ["PGCONNECT_TIMEOUT"] = previous_connect_timeout
        if cleanup_failure is not None:
            raise PostgresHarnessError(str(cleanup_failure)) from None
