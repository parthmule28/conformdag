"""Offline safety checks for the opt-in PostgreSQL integration harness."""

from __future__ import annotations

import os

import postgres_harness
import pytest
from postgres_harness import (
    PostgresHarnessError,
    admin_url_from_environment,
    postgres_admin_from_environment,
    validate_admin_dsn,
    validate_libpq_routing_environment,
    validate_owned_database,
    validate_server_requirements,
)
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

_SAFE_DSN = "postgresql+psycopg://c26_test:local-only-secret@127.0.0.1:55432/postgres"


def test_missing_dsn_fails_with_actionable_message() -> None:
    with pytest.raises(PostgresHarnessError, match="CONFORMDAG_TEST_POSTGRES_DSN is required"):
        admin_url_from_environment({})


def test_platform_dsn_is_never_used_as_test_dsn() -> None:
    with pytest.raises(PostgresHarnessError, match="CONFORMDAG_TEST_POSTGRES_DSN is required"):
        admin_url_from_environment({"CONFORMDAG_PLATFORM_DSN": _SAFE_DSN})


def test_valid_local_test_dsn_is_parsed_without_exposing_password() -> None:
    url = validate_admin_dsn(_SAFE_DSN)

    assert isinstance(url, URL)
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.database == "postgres"
    assert "local-only-secret" not in repr(url)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+psycopg://c26_test:secret@db.example.invalid:55432/postgres",
        "postgresql+psycopg://c26_test:secret@127.0.0.1/postgres",
        "postgresql+psycopg://admin:secret@127.0.0.1:55432/postgres",
        "postgresql+psycopg://c26_only:secret@127.0.0.1:55432/postgres",
        "postgresql+psycopg://test_only:secret@127.0.0.1:55432/postgres",
        "postgresql+psycopg://c26_test@127.0.0.1:55432/postgres",
        "postgresql+psycopg://c26_test:secret@127.0.0.1:55432/production",
        "postgresql+psycopg://c26_test:secret@127.0.0.1:55432/postgres?sslmode=disable",
    ],
)
def test_unsafe_dsn_is_rejected_without_echoing_it(dsn: str) -> None:
    with pytest.raises(PostgresHarnessError) as raised:
        validate_admin_dsn(dsn)

    assert "secret" not in str(raised.value)
    assert dsn not in str(raised.value)


def test_missing_dsn_error_does_not_echo_other_environment_values() -> None:
    with pytest.raises(PostgresHarnessError) as raised:
        admin_url_from_environment({"CONFORMDAG_PLATFORM_DSN": _SAFE_DSN})

    assert "local-only-secret" not in str(raised.value)


def test_cleanup_rejects_names_not_created_by_this_run() -> None:
    with pytest.raises(PostgresHarnessError, match="not owned by this test run"):
        validate_owned_database("conformdag_c26_someone_elses_db", set())


@pytest.mark.parametrize("name", ["postgres", "conformdag_c26_evil;DROP DATABASE postgres"])
def test_cleanup_rejects_maintenance_and_malformed_names(name: str) -> None:
    with pytest.raises(PostgresHarnessError):
        validate_owned_database(name, {name})


def test_cleanup_accepts_an_exact_uuid_name_owned_by_this_run() -> None:
    owned_name = f"conformdag_c26_{'a' * 32}"

    validate_owned_database(owned_name, {owned_name})


def test_server_guard_accepts_postgresql_17_with_createdb() -> None:
    validate_server_requirements(170_005, True)


@pytest.mark.parametrize(
    ("version_num", "createdb", "message"),
    [
        (160_000, True, "major version 17"),
        (170_000, False, "CREATEDB privilege"),
    ],
)
def test_server_guard_rejects_wrong_version_or_missing_createdb(version_num: int, createdb: bool, message: str) -> None:
    with pytest.raises(PostgresHarnessError, match=message):
        validate_server_requirements(version_num, createdb)


@pytest.mark.parametrize("routing_override", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
def test_libpq_routing_override_is_rejected_before_engine_or_connection(
    monkeypatch: pytest.MonkeyPatch, routing_override: str
) -> None:
    engine_calls = 0
    connection_calls = 0

    def unexpected_engine(_url: URL) -> Engine:
        nonlocal engine_calls
        engine_calls += 1
        raise AssertionError("routing guard must reject before engine creation")

    def unexpected_connection(*_args: object, **_kwargs: object) -> None:
        nonlocal connection_calls
        connection_calls += 1
        raise AssertionError("routing guard must reject before connection")

    monkeypatch.setattr(postgres_harness, "build_admin_engine", unexpected_engine)
    monkeypatch.setattr(postgres_harness.psycopg, "connect", unexpected_connection)
    override_value = "routing-value-must-not-be-logged"
    environ = {"CONFORMDAG_TEST_POSTGRES_DSN": _SAFE_DSN, routing_override: override_value}

    with (
        pytest.raises(PostgresHarnessError, match="libpq routing override") as raised,
        postgres_admin_from_environment(environ),
    ):
        pytest.fail("unsafe libpq routing override unexpectedly reached the fixture")

    assert engine_calls == 0
    assert connection_calls == 0
    assert override_value not in str(raised.value)
    assert environ[routing_override] == override_value


def test_empty_libpq_routing_environment_is_allowed() -> None:
    validate_libpq_routing_environment({"PGHOSTADDR": "", "PGSERVICE": "", "PGSERVICEFILE": ""})


class _ExpectedEnvironmentContextExit(RuntimeError):
    pass


@pytest.mark.parametrize(
    ("raise_inside_context", "previous_options", "previous_connect_timeout"),
    [
        (False, None, None),
        (True, "caller-provided pg options", "19"),
    ],
    ids=["normal-restores-unset-values", "exception-restores-existing-values"],
)
def test_postgres_connection_environment_is_restored(
    monkeypatch: pytest.MonkeyPatch,
    raise_inside_context: bool,
    previous_options: str | None,
    previous_connect_timeout: str | None,
) -> None:
    previous_values = {
        "PGOPTIONS": previous_options,
        "PGCONNECT_TIMEOUT": previous_connect_timeout,
    }
    for variable, value in previous_values.items():
        if value is None:
            monkeypatch.delenv(variable, raising=False)
        else:
            monkeypatch.setenv(variable, value)

    engine = create_engine("sqlite://")

    def build_fake_engine(_url: URL) -> Engine:
        options = os.environ.get("PGOPTIONS")
        assert options is not None and "statement_timeout" in options
        assert os.environ.get("PGCONNECT_TIMEOUT") == "3"
        return engine

    def skip_live_connection(_engine: Engine) -> None:
        return None

    monkeypatch.setattr(postgres_harness, "build_admin_engine", build_fake_engine)
    monkeypatch.setattr(postgres_harness, "verify_admin_connection", skip_live_connection)
    environment = {"CONFORMDAG_TEST_POSTGRES_DSN": _SAFE_DSN}

    if raise_inside_context:
        with pytest.raises(_ExpectedEnvironmentContextExit), postgres_admin_from_environment(environment):
            assert os.environ.get("PGCONNECT_TIMEOUT") == "3"
            raise _ExpectedEnvironmentContextExit
    else:
        with postgres_admin_from_environment(environment):
            assert os.environ.get("PGCONNECT_TIMEOUT") == "3"

    for variable, value in previous_values.items():
        assert os.environ.get(variable) == value
