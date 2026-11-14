"""Real PostgreSQL integration suite.

Run explicitly with ``mise run test:postgres`` after setting
``CONFORMDAG_TEST_POSTGRES_DSN`` to the dedicated disposable local PostgreSQL 17
maintenance connection. The harness provisions and removes one fresh database
for each marked test; credentials are never included in test diagnostics.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import NamedTuple, cast

import pytest
from alembic import command
from alembic.config import Config
from postgres_harness import (
    TEST_DSN_ENV,
    PostgresAdmin,
    PostgresHarnessError,
    PostgresTestDatabase,
    postgres_admin_from_environment,
)
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from conformdag.baselines import Baseline
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    RemediationAction,
    RemediationPayload,
    RemediationTarget,
    RunIssue,
    RunMetadata,
    ScanReport,
    Severity,
)
from conformdag.platform import runner as runner_module
from conformdag.platform.domain import ScanStatus
from conformdag.platform.persistence import migrations as persistence_migrations
from conformdag.platform.persistence.baselines import eligible_baseline
from conformdag.platform.persistence.migrations import migration_lock
from conformdag.platform.persistence.models import FindingRow, RepositoryRow, ScanRow, SuppressionRow
from conformdag.platform.persistence.retention import prune_scan_artifact, retention_target_scan_ids
from conformdag.platform.persistence.scans import (
    claim_queued_scan,
    heartbeat_running_scan,
    transition_running_scan,
    transition_scan_to_cancelled,
)
from conformdag.platform.services import ConflictError
from conformdag.platform.services.baselines import set_baseline
from conformdag.platform.services.suppressions import create_suppression
from conformdag.platform.worker import WorkerSettings, run_worker_once

_INITIALIZER_CHILD = """
import sys
from sqlalchemy import Engine
from conformdag.platform.persistence.migrations import initialize_session_factory

database_url = sys.stdin.readline().rstrip("\\n")
factory = initialize_session_factory(database_url)
engine = factory.kw.get("bind")
if not isinstance(engine, Engine):
    raise SystemExit(2)
engine.dispose(close=True)
"""
_CHILD_LOCK_TIMEOUT_MS = 45_000
_CHILDREN_WAIT_TIMEOUT_SECONDS = 30.0
_BACKEND_OBSERVATION_TIMEOUT_SECONDS = 20.0
_CLAIM_WORKER_TIMEOUT_SECONDS = 8.0
_RUNNER_RACE_WORKER_TIMEOUT_SECONDS = 20.0
_ROW_LOCK_OBSERVATION_TIMEOUT_SECONDS = 15.0
_RACE_LOCK_TIMEOUT_MS = 30_000
_RACE_STATEMENT_TIMEOUT_MS = 30_000
_RUNNER_INGEST = cast("Callable[[Session, ScanRow, ScanReport], None]", runner_module.__dict__["_ingest"])
_RUNNER_BASELINE = cast("Callable[[Session, str, str | None], Baseline | None]", runner_module.__dict__["_baseline"])


@pytest.fixture(scope="session")
def postgres_admin() -> Iterator[PostgresAdmin]:
    """Connect only when a marked integration test requests this fixture."""
    failure: str | None = None
    manager = postgres_admin_from_environment(os.environ)
    admin: PostgresAdmin | None = None
    try:
        admin = manager.__enter__()
    except PostgresHarnessError as error:
        failure = str(error)
    if failure is not None:
        pytest.fail(failure, pytrace=False)
        return
    if admin is None:
        pytest.fail("Could not initialize the guarded PostgreSQL maintenance fixture.", pytrace=False)
        return

    try:
        yield admin
    finally:
        failure = None
        try:
            manager.__exit__(None, None, None)
        except PostgresHarnessError as error:
            failure = str(error)
        if failure is not None:
            pytest.fail(failure, pytrace=False)


@pytest.fixture
def postgres_empty_database(postgres_admin: PostgresAdmin) -> Iterator[PostgresTestDatabase]:
    """Create and safely drop one unique disposable database without initializing it."""
    try:
        with postgres_admin.disposable_database() as database:
            yield database
    except PostgresHarnessError as error:
        pytest.fail(str(error), pytrace=False)


@pytest.fixture
def postgres_database(postgres_empty_database: PostgresTestDatabase) -> Iterator[PostgresTestDatabase]:
    """Create, migrate, and safely drop one unique disposable database per test."""
    try:
        postgres_empty_database.initialize()
    except PostgresHarnessError as error:
        pytest.fail(str(error), pytrace=False)
        return
    yield postgres_empty_database


@pytest.mark.postgres
def test_fixture_creates_and_migrates_a_fresh_postgres_database(postgres_database: PostgresTestDatabase) -> None:
    with postgres_database.session_factory() as session:
        database_name, server_version, revision = session.execute(
            text(
                "SELECT current_database(), current_setting('server_version_num')::integer, "
                "(SELECT version_num FROM alembic_version)"
            )
        ).one()

    assert database_name == postgres_database.name
    assert postgres_database.name.startswith("conformdag_c26_")
    assert server_version // 10000 == 17
    assert revision == "0004"


@pytest.mark.postgres
def test_create_session_factory_is_bind_only_and_initialize_is_idempotent(
    postgres_empty_database: PostgresTestDatabase,
) -> None:
    bound_factory = postgres_empty_database.new_session_factory(initialize=False)
    engine = _factory_engine(bound_factory)
    with engine.connect() as connection:
        public_tables = (
            connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars().all()
        )

    assert public_tables == []

    first_factory = postgres_empty_database.initialize()
    _assert_head_and_schema(first_factory)
    second_factory = postgres_empty_database.initialize()
    _assert_head_and_schema(second_factory)


@pytest.mark.postgres
def test_upgrade_from_0003_preserves_rows_and_deduplicates_suppressions(
    postgres_empty_database: PostgresTestDatabase,
) -> None:
    first_factory = postgres_empty_database.initialize()
    _assert_head_and_schema(first_factory)
    config = _production_alembic_config(postgres_empty_database.url.render_as_string(hide_password=False))
    command.downgrade(config, "0003")

    repository_id = "c26-pg01-preserved-repo"
    scan_id = "c26-pg01-preserved-scan"
    duplicate_created_at = datetime(2025, 1, 1, tzinfo=UTC)
    preserved_created_at = datetime(2024, 1, 1, tzinfo=UTC)
    pre_upgrade_factory = postgres_empty_database.new_session_factory(initialize=False)
    with pre_upgrade_factory() as session:
        session.add(RepositoryRow(id=repository_id, name="C26 PG01 preserved", path="dags/c26_pg01"))
        session.flush()
        session.add(
            ScanRow(
                id=scan_id,
                repository_id=repository_id,
                status="succeeded",
                result_fingerprint="f" * 64,
                complete=True,
                report_json={"summary": {"ok": True, "text": "preserved λ"}},
            )
        )
        session.flush()
        session.add_all(
            [
                FindingRow(
                    scan_id=scan_id,
                    repository_id=repository_id,
                    policy_id="C26-PG01",
                    policy_version="1",
                    status="violation",
                    severity="high",
                    file_path="dags/preserved.py",
                    start_line=4,
                    end_line=9,
                    fingerprint="e" * 64,
                    explanation="preserved finding",
                    remediation="preserved remediation",
                    fix_json={"patches": [{"path": "dags/preserved.py", "applied": False}]},
                ),
                SuppressionRow(
                    id="c26-pg01-suppression-old",
                    policy_id="C26-PG01",
                    fingerprint="d" * 64,
                    reason="old duplicate retained",
                    owner="c26-test",
                    created_at=preserved_created_at,
                    expires_at=datetime(2035, 1, 1, tzinfo=UTC),
                ),
                SuppressionRow(
                    id="c26-pg01-suppression-new",
                    policy_id="C26-PG01",
                    fingerprint="d" * 64,
                    reason="new duplicate removed",
                    owner="c26-test",
                    created_at=duplicate_created_at,
                    expires_at=datetime(2035, 1, 1, tzinfo=UTC),
                ),
            ]
        )
        session.commit()

    upgraded_factory = postgres_empty_database.initialize()
    _assert_head_and_schema(upgraded_factory)
    with upgraded_factory() as session:
        repository = session.get(RepositoryRow, repository_id)
        scan = session.get(ScanRow, scan_id)
        finding = session.execute(select(FindingRow).where(FindingRow.scan_id == scan_id)).scalar_one()
        suppressions = (
            session.execute(
                select(SuppressionRow).where(
                    SuppressionRow.policy_id == "C26-PG01",
                    SuppressionRow.fingerprint == "d" * 64,
                )
            )
            .scalars()
            .all()
        )

    assert repository is not None and repository.name == "C26 PG01 preserved"
    assert scan is not None
    assert scan.result_fingerprint == "f" * 64
    assert scan.report_json == {"summary": {"ok": True, "text": "preserved λ"}}
    assert finding.start_line == 4 and finding.end_line == 9
    assert finding.fix_json == {"patches": [{"path": "dags/preserved.py", "applied": False}]}
    assert [(row.id, row.reason, row.created_at) for row in suppressions] == [
        ("c26-pg01-suppression-old", "old duplicate retained", preserved_created_at)
    ]


@pytest.mark.postgres
@pytest.mark.parametrize("raise_inside_lock", [False, True], ids=["normal-exit", "exceptional-exit"])
def test_migration_advisory_lock_is_session_scoped_and_released(
    postgres_empty_database: PostgresTestDatabase, raise_inside_lock: bool
) -> None:
    database_url = postgres_empty_database.url.render_as_string(hide_password=False)
    verifier_engine = _factory_engine(postgres_empty_database.new_session_factory(initialize=False))

    if raise_inside_lock:
        with pytest.raises(_ExpectedLockContextError), migration_lock(database_url):
            _assert_migration_lock_blocks_distinct_backend(verifier_engine, database_url)
            raise _ExpectedLockContextError
    else:
        with migration_lock(database_url):
            _assert_migration_lock_blocks_distinct_backend(verifier_engine, database_url)

    with verifier_engine.connect() as connection:
        backend_id = connection.scalar(text("SELECT pg_backend_pid()"))
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"), {"lock_key": database_url}
        )
        assert isinstance(backend_id, int)
        assert acquired is True
        assert (
            connection.scalar(text("SELECT pg_advisory_unlock(hashtext(:lock_key))"), {"lock_key": database_url})
            is True
        )


@pytest.mark.postgres
def test_two_process_first_boots_wait_on_the_real_advisory_lock(
    postgres_empty_database: PostgresTestDatabase,
) -> None:
    database_url = postgres_empty_database.url.render_as_string(hide_password=False)
    monitor_engine = _factory_engine(postgres_empty_database.new_session_factory(initialize=False))
    children: list[subprocess.Popen[str]] = []
    observed_waiters = False
    try:
        with migration_lock(database_url):
            try:
                children.append(_start_initializer_child(database_url))
                children.append(_start_initializer_child(database_url))
                waiting_backends = _wait_for_initializer_backends(monitor_engine, children)
                observed_waiters = True
                child_backend_ids = {backend_id for backend_id, _ in waiting_backends}
                shared_blockers = set(waiting_backends[0][1])
                for _, blockers in waiting_backends[1:]:
                    shared_blockers.intersection_update(blockers)
                assert len(waiting_backends) == 2
                assert len(child_backend_ids) == 2
                assert len(shared_blockers) == 1
                assert not child_backend_ids.intersection(shared_blockers)
            finally:
                if not observed_waiters:
                    _terminate_owned_children(children)

        deadline = time.monotonic() + _CHILDREN_WAIT_TIMEOUT_SECONDS
        for child in children:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "Concurrent first-boot child processes exceeded the bounded completion deadline."
            try:
                return_code = child.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pytest.fail(
                    "Concurrent first-boot child process did not finish after advisory-lock release.", pytrace=False
                )
            assert return_code == 0, (
                "Concurrent first-boot child process failed; child output is intentionally suppressed."
            )

        with monitor_engine.connect() as connection:
            revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        assert revisions == ["0004"]
    finally:
        _terminate_owned_children(children)


class _ExpectedLockContextError(RuntimeError):
    pass


def _assert_migration_lock_blocks_distinct_backend(engine: Engine, database_url: str) -> None:
    with engine.connect() as connection:
        backend_id = connection.scalar(text("SELECT pg_backend_pid()"))
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"), {"lock_key": database_url}
        )
        lock_holders = (
            connection.execute(
                text(
                    "SELECT pid FROM pg_locks "
                    "WHERE locktype = 'advisory' AND granted "
                    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
                    "AND pid <> pg_backend_pid()"
                )
            )
            .scalars()
            .all()
        )

    assert isinstance(backend_id, int)
    assert acquired is False
    assert len(lock_holders) == 1
    assert lock_holders[0] != backend_id


def _assert_head_and_schema(factory: sessionmaker[Session]) -> None:
    engine = _factory_engine(factory)
    inspector = inspect(engine)
    assert set(inspector.get_table_names(schema="public")) == {
        "alembic_version",
        "findings",
        "repos",
        "scans",
        "suppressions",
    }
    with engine.connect() as connection:
        revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    assert revisions == ["0004"]

    findings_indexes = {index["name"]: index for index in inspector.get_indexes("findings", schema="public")}
    scan_indexes = {index["name"]: index for index in inspector.get_indexes("scans", schema="public")}
    suppression_indexes = {index["name"]: index for index in inspector.get_indexes("suppressions", schema="public")}
    assert findings_indexes["ix_findings_repo_policy"]["column_names"] == ["repository_id", "policy_id"]
    assert scan_indexes["ix_scans_repo_created"]["column_names"] == ["repository_id", "created_at"]
    assert scan_indexes["ix_scans_status_created"]["column_names"] == ["status", "created_at"]
    assert scan_indexes["ix_scans_status_claimed"]["column_names"] == ["status", "claimed_at"]
    assert suppression_indexes["uq_suppressions_policy_fingerprint"]["unique"] is True
    assert suppression_indexes["uq_suppressions_policy_fingerprint"]["column_names"] == [
        "policy_id",
        "fingerprint",
    ]

    repository_unique_constraints = inspector.get_unique_constraints("repos", schema="public")
    assert any(constraint["column_names"] == ["name"] for constraint in repository_unique_constraints)

    foreign_keys: set[tuple[str, tuple[str, ...], str, tuple[str, ...], str | None]] = set()
    for table in ("scans", "findings"):
        for foreign_key in inspector.get_foreign_keys(table, schema="public"):
            options = foreign_key.get("options")
            on_delete = options.get("ondelete") if options is not None else None
            foreign_keys.add(
                (
                    table,
                    tuple(foreign_key["constrained_columns"]),
                    foreign_key["referred_table"],
                    tuple(foreign_key["referred_columns"]),
                    on_delete,
                )
            )
    assert {
        ("scans", ("repository_id",), "repos", ("id",), "CASCADE"),
        ("findings", ("scan_id",), "scans", ("id",), "CASCADE"),
        ("findings", ("repository_id",), "repos", ("id",), "CASCADE"),
    } <= foreign_keys


def _factory_engine(factory: sessionmaker[Session]) -> Engine:
    engine = factory.kw.get("bind")
    assert isinstance(engine, Engine)
    return engine


def _production_alembic_config(database_url: str) -> Config:
    ini_path = Path(persistence_migrations.__file__).resolve().parent.parent / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(ini_path.parent / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _start_initializer_child(database_url: str) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    for variable in (
        TEST_DSN_ENV,
        "CONFORMDAG_PLATFORM_DSN",
        "PGDATABASE",
        "PGHOST",
        "PGHOSTADDR",
        "PGPASSWORD",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGUSER",
        "PGOPTIONS",
    ):
        environment.pop(variable, None)
    environment["PGOPTIONS"] = f"-c statement_timeout={_CHILD_LOCK_TIMEOUT_MS} -c lock_timeout={_CHILD_LOCK_TIMEOUT_MS}"
    process = subprocess.Popen(
        [sys.executable, "-c", _INITIALIZER_CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        env=environment,
    )
    assert process.stdin is not None
    try:
        process.stdin.write(f"{database_url}\n")
        process.stdin.close()
    except OSError:
        _terminate_owned_children([process])
        raise AssertionError("Could not pass the disposable database URL to an initializer child over stdin.") from None
    return process


def _wait_for_initializer_backends(
    engine: Engine, children: list[subprocess.Popen[str]]
) -> list[tuple[int, list[int]]]:
    deadline = time.monotonic() + _BACKEND_OBSERVATION_TIMEOUT_SECONDS
    query = text(
        "SELECT waiting.pid, pg_blocking_pids(waiting.pid) "
        "FROM pg_stat_activity AS waiting "
        "WHERE waiting.datname = current_database() "
        "AND waiting.pid <> pg_backend_pid() "
        "AND waiting.query ILIKE '%pg_advisory_lock%' "
        "AND waiting.wait_event_type = 'Lock' "
        "AND cardinality(pg_blocking_pids(waiting.pid)) > 0"
    )
    while True:
        for child in children:
            if child.poll() is not None:
                pytest.fail(
                    "An initializer child exited before both advisory-lock waiters were observed.", pytrace=False
                )
        with engine.connect() as connection:
            rows = connection.execute(query).all()
        waiting_backends = [(int(row[0]), [int(blocker) for blocker in row[1]]) for row in rows]
        if len(waiting_backends) >= 2:
            return waiting_backends
        if time.monotonic() >= deadline:
            pytest.fail(
                "Did not observe both child backends blocked by the held PostgreSQL advisory lock.", pytrace=False
            )
        # The query-visible lock wait is the assertion; this only throttles bounded polling.
        time.sleep(0.025)


def _terminate_owned_children(children: list[subprocess.Popen[str]]) -> None:
    for child in children:
        if child.poll() is None:
            with suppress(ProcessLookupError):
                child.terminate()
    for child in children:
        if child.poll() is None:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


class _ClaimOutcome(NamedTuple):
    backend_pid: int
    scan_id: str | None
    attempts: int | None
    status: str | None


class _ScanSnapshot(NamedTuple):
    backend_pid: int
    status: str
    attempts: int
    claimed_at: datetime | None
    finished_at: datetime | None
    error: str | None


def _seed_repository(session: Session, repository_id: str) -> None:
    session.add(RepositoryRow(id=repository_id, name=f"C26 {repository_id}", path=f"dags/{repository_id}"))
    session.flush()


def _claim_from_worker(
    factory: sessionmaker[Session],
    stale_cutoff: datetime,
    max_attempts: int,
    connected: Event,
    backend_pids: list[int],
    *,
    commit_claim: bool,
) -> _ClaimOutcome:
    with factory() as session:
        backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(backend_pid, int)
        backend_pids.append(backend_pid)
        connected.set()
        claimed = claim_queued_scan(session, stale_cutoff, max_attempts)
        if claimed is None:
            session.rollback()
            return _ClaimOutcome(backend_pid, None, None, None)

        outcome = _ClaimOutcome(backend_pid, claimed.id, claimed.attempts, claimed.status)
        if commit_claim:
            session.commit()
        else:
            session.rollback()
        return outcome


def _read_scan_snapshot(factory: sessionmaker[Session], scan_id: str) -> _ScanSnapshot:
    with factory() as session:
        backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(backend_pid, int)
        scan = session.get(ScanRow, scan_id)
        assert scan is not None
        return _ScanSnapshot(
            backend_pid,
            scan.status,
            scan.attempts,
            scan.claimed_at,
            scan.finished_at,
            scan.error,
        )


@pytest.mark.postgres
def test_two_claimers_cannot_claim_the_same_locked_queued_scan(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg03-repo"
    scan_id = "c26-pg03-only-queued-scan"
    seed_factory = postgres_database.session_factory
    with seed_factory() as seed_session:
        _seed_repository(seed_session, repository_id)
        seed_session.add(ScanRow(id=scan_id, repository_id=repository_id, status="queued", attempts=0))
        seed_session.commit()

    first_factory = postgres_database.new_session_factory(initialize=False)
    second_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    stale_cutoff = datetime.now(UTC) - timedelta(minutes=1)
    connected = Event()
    worker_backend_pids: list[int] = []
    with ThreadPoolExecutor(max_workers=1) as executor, first_factory() as first_session:
        first_pid = first_session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(first_pid, int)
        first_claim = claim_queued_scan(first_session, stale_cutoff, max_attempts=3)
        assert first_claim is not None
        assert (first_claim.id, first_claim.status, first_claim.attempts) == (scan_id, "running", 1)
        assert first_session.in_transaction()

        before_competitor = _read_scan_snapshot(reader_factory, scan_id)
        assert before_competitor.backend_pid != first_pid
        assert (before_competitor.status, before_competitor.attempts) == ("queued", 0)
        assert before_competitor.claimed_at is None and before_competitor.finished_at is None

        future = executor.submit(
            _claim_from_worker,
            second_factory,
            stale_cutoff,
            3,
            connected,
            worker_backend_pids,
            commit_claim=False,
        )
        try:
            assert connected.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert len(worker_backend_pids) == 1
            second_backend_pid = worker_backend_pids[0]
            assert second_backend_pid != first_pid
            second_outcome = future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)
            assert first_session.in_transaction(), "the first caller must still hold its uncommitted claim"
            assert second_outcome.backend_pid == second_backend_pid
            assert (second_outcome.scan_id, second_outcome.attempts, second_outcome.status) == (
                None,
                None,
                None,
            )
            first_session.commit()
        finally:
            if first_session.in_transaction():
                first_session.rollback()
            if not future.done():
                future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)

    after_commit = _read_scan_snapshot(reader_factory, scan_id)
    assert after_commit.backend_pid not in (first_pid, second_outcome.backend_pid)
    assert (after_commit.status, after_commit.attempts) == ("running", 1)
    assert after_commit.claimed_at is not None
    assert after_commit.finished_at is None


@pytest.mark.postgres
def test_skip_locked_claims_next_queued_scan_while_oldest_is_held(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg04-repo"
    oldest_id = "c26-pg04-oldest-queued-scan"
    next_id = "c26-pg04-next-queued-scan"
    now = datetime.now(UTC)
    with postgres_database.session_factory() as seed_session:
        _seed_repository(seed_session, repository_id)
        seed_session.add_all(
            [
                ScanRow(
                    id=oldest_id,
                    repository_id=repository_id,
                    status="queued",
                    attempts=0,
                    created_at=now - timedelta(minutes=10),
                ),
                ScanRow(
                    id=next_id,
                    repository_id=repository_id,
                    status="queued",
                    attempts=0,
                    created_at=now - timedelta(minutes=5),
                ),
            ]
        )
        seed_session.commit()

    first_factory = postgres_database.new_session_factory(initialize=False)
    second_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    stale_cutoff = now - timedelta(hours=1)
    connected = Event()
    worker_backend_pids: list[int] = []
    with ThreadPoolExecutor(max_workers=1) as executor, first_factory() as first_session:
        first_pid = first_session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(first_pid, int)
        first_claim = claim_queued_scan(first_session, stale_cutoff, max_attempts=3)
        assert first_claim is not None
        assert (first_claim.id, first_claim.status, first_claim.attempts) == (oldest_id, "running", 1)

        future = executor.submit(
            _claim_from_worker,
            second_factory,
            stale_cutoff,
            3,
            connected,
            worker_backend_pids,
            commit_claim=True,
        )
        try:
            assert connected.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert len(worker_backend_pids) == 1
            second_backend_pid = worker_backend_pids[0]
            assert second_backend_pid != first_pid
            second_outcome = future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)
            assert first_session.in_transaction(), "the oldest row must remain locked until its caller commits"
            assert second_outcome.backend_pid == second_backend_pid
            assert (second_outcome.scan_id, second_outcome.attempts, second_outcome.status) == (
                next_id,
                1,
                "running",
            )

            while_first_is_locked = {
                scan_id: _read_scan_snapshot(reader_factory, scan_id) for scan_id in (oldest_id, next_id)
            }
            assert while_first_is_locked[oldest_id].backend_pid not in (first_pid, second_outcome.backend_pid)
            assert while_first_is_locked[next_id].backend_pid not in (first_pid, second_outcome.backend_pid)
            assert (while_first_is_locked[oldest_id].status, while_first_is_locked[oldest_id].attempts) == (
                "queued",
                0,
            )
            assert (while_first_is_locked[next_id].status, while_first_is_locked[next_id].attempts) == (
                "running",
                1,
            )
            first_session.commit()
        finally:
            if first_session.in_transaction():
                first_session.rollback()
            if not future.done():
                future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)

    final_states = {scan_id: _read_scan_snapshot(reader_factory, scan_id) for scan_id in (oldest_id, next_id)}
    assert final_states[oldest_id].status == final_states[next_id].status == "running"
    assert final_states[oldest_id].attempts == final_states[next_id].attempts == 1
    assert final_states[oldest_id].claimed_at is not None and final_states[next_id].claimed_at is not None
    assert {first_claim.id, second_outcome.scan_id} == {oldest_id, next_id}


@pytest.mark.postgres
def test_stale_running_claim_is_reclaimed_once_with_attempt_increment(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg05-reclaim-repo"
    scan_id = "c26-pg05-stale-running-scan"
    old_claimed_at = datetime.now(UTC) - timedelta(hours=2)
    with postgres_database.session_factory() as seed_session:
        _seed_repository(seed_session, repository_id)
        seed_session.add(
            ScanRow(
                id=scan_id,
                repository_id=repository_id,
                status="running",
                attempts=0,
                claimed_at=old_claimed_at,
            )
        )
        seed_session.commit()

    first_factory = postgres_database.new_session_factory(initialize=False)
    second_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    stale_cutoff = datetime.now(UTC) - timedelta(hours=1)
    connected = Event()
    worker_backend_pids: list[int] = []
    with ThreadPoolExecutor(max_workers=1) as executor, first_factory() as first_session:
        first_pid = first_session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(first_pid, int)
        reclaimed = claim_queued_scan(first_session, stale_cutoff, max_attempts=3)
        assert reclaimed is not None
        assert (reclaimed.id, reclaimed.status, reclaimed.attempts) == (scan_id, "running", 1)
        assert reclaimed.claimed_at is not None and reclaimed.claimed_at > old_claimed_at

        future = executor.submit(
            _claim_from_worker,
            second_factory,
            stale_cutoff,
            3,
            connected,
            worker_backend_pids,
            commit_claim=False,
        )
        try:
            assert connected.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert len(worker_backend_pids) == 1
            second_backend_pid = worker_backend_pids[0]
            assert second_backend_pid != first_pid
            second_outcome = future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)
            assert first_session.in_transaction()
            assert second_outcome.backend_pid == second_backend_pid
            assert second_outcome.scan_id is None
            before_commit = _read_scan_snapshot(reader_factory, scan_id)
            assert before_commit.backend_pid not in (first_pid, second_outcome.backend_pid)
            assert (before_commit.status, before_commit.attempts, before_commit.claimed_at) == (
                "running",
                0,
                old_claimed_at,
            )
            first_session.commit()
        finally:
            if first_session.in_transaction():
                first_session.rollback()
            if not future.done():
                future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)

    after_commit = _read_scan_snapshot(reader_factory, scan_id)
    assert (after_commit.status, after_commit.attempts) == ("running", 1)
    assert after_commit.claimed_at is not None and after_commit.claimed_at > old_claimed_at
    assert after_commit.finished_at is None


@pytest.mark.postgres
def test_exhausted_stale_claim_is_caller_committed_with_claim_time_preserved(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg05-exhausted-repo"
    scan_id = "c26-pg05-exhausted-running-scan"
    max_attempts = 3
    old_claimed_at = datetime.now(UTC) - timedelta(hours=2)
    with postgres_database.session_factory() as seed_session:
        _seed_repository(seed_session, repository_id)
        seed_session.add(
            ScanRow(
                id=scan_id,
                repository_id=repository_id,
                status="running",
                attempts=max_attempts,
                claimed_at=old_claimed_at,
                error="previous worker error",
            )
        )
        seed_session.commit()

    first_factory = postgres_database.new_session_factory(initialize=False)
    second_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    stale_cutoff = datetime.now(UTC) - timedelta(hours=1)
    connected = Event()
    worker_backend_pids: list[int] = []
    with ThreadPoolExecutor(max_workers=1) as executor, first_factory() as first_session:
        first_pid = first_session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(first_pid, int)
        exhausted = claim_queued_scan(first_session, stale_cutoff, max_attempts=max_attempts)
        assert exhausted is None
        staged_failure = first_session.get(ScanRow, scan_id)
        assert staged_failure is not None
        assert staged_failure.status == "failed"
        assert staged_failure.error == "abandoned by a previous worker; attempt budget exhausted"
        assert staged_failure.finished_at is not None
        assert staged_failure.claimed_at == old_claimed_at
        assert first_session.in_transaction()

        future = executor.submit(
            _claim_from_worker,
            second_factory,
            stale_cutoff,
            max_attempts,
            connected,
            worker_backend_pids,
            commit_claim=False,
        )
        try:
            assert connected.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert len(worker_backend_pids) == 1
            second_backend_pid = worker_backend_pids[0]
            assert second_backend_pid != first_pid
            second_outcome = future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)
            assert first_session.in_transaction()
            assert second_outcome.backend_pid == second_backend_pid
            assert second_outcome.scan_id is None
            before_commit = _read_scan_snapshot(reader_factory, scan_id)
            assert before_commit.backend_pid not in (first_pid, second_outcome.backend_pid)
            assert (before_commit.status, before_commit.attempts, before_commit.claimed_at) == (
                "running",
                max_attempts,
                old_claimed_at,
            )
            assert before_commit.finished_at is None
            assert before_commit.error == "previous worker error"
            first_session.commit()
        finally:
            if first_session.in_transaction():
                first_session.rollback()
            if not future.done():
                future.result(timeout=_CLAIM_WORKER_TIMEOUT_SECONDS)

    after_commit = _read_scan_snapshot(reader_factory, scan_id)
    assert (after_commit.status, after_commit.attempts, after_commit.claimed_at) == (
        "failed",
        max_attempts,
        old_claimed_at,
    )
    assert after_commit.error == "abandoned by a previous worker; attempt budget exhausted"
    assert after_commit.finished_at is not None


@pytest.mark.postgres
def test_stale_running_claim_precedes_an_older_queued_scan(postgres_database: PostgresTestDatabase) -> None:
    repository_id = "c26-pg05-precedence-repo"
    queued_id = "c26-pg05-older-queued-scan"
    stale_id = "c26-pg05-stale-running-scan"
    now = datetime.now(UTC)
    old_claimed_at = now - timedelta(days=2)
    with postgres_database.session_factory() as seed_session:
        _seed_repository(seed_session, repository_id)
        seed_session.add_all(
            [
                ScanRow(
                    id=queued_id,
                    repository_id=repository_id,
                    status="queued",
                    attempts=0,
                    created_at=now - timedelta(days=3),
                ),
                ScanRow(
                    id=stale_id,
                    repository_id=repository_id,
                    status="running",
                    attempts=1,
                    created_at=now - timedelta(days=1),
                    claimed_at=old_claimed_at,
                ),
            ]
        )
        seed_session.commit()

    claimant_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    with claimant_factory() as claimant:
        claimant_pid = claimant.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(claimant_pid, int)
        claimed = claim_queued_scan(claimant, now - timedelta(hours=1), max_attempts=3)
        assert claimed is not None
        assert (claimed.id, claimed.status, claimed.attempts) == (stale_id, "running", 2)
        assert claimed.claimed_at is not None and claimed.claimed_at > old_claimed_at
        claimant.commit()

    stale_snapshot = _read_scan_snapshot(reader_factory, stale_id)
    queued_snapshot = _read_scan_snapshot(reader_factory, queued_id)
    assert stale_snapshot.backend_pid != claimant_pid
    assert (stale_snapshot.status, stale_snapshot.attempts) == ("running", 2)
    assert stale_snapshot.claimed_at is not None and stale_snapshot.claimed_at > old_claimed_at
    assert (queued_snapshot.status, queued_snapshot.attempts, queued_snapshot.claimed_at) == ("queued", 0, None)


@pytest.mark.postgres
def test_worker_once_commits_exhausted_stale_scan_before_returning_none(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg05-worker-exhausted-repo"
    scan_id = "c26-pg05-worker-exhausted-running-scan"
    max_attempts = 3
    old_claimed_at = datetime.now(UTC) - timedelta(hours=2)
    with postgres_database.session_factory() as seed_session:
        _seed_repository(seed_session, repository_id)
        seed_session.add(
            ScanRow(
                id=scan_id,
                repository_id=repository_id,
                status="running",
                attempts=max_attempts,
                claimed_at=old_claimed_at,
            )
        )
        seed_session.commit()

    reader_factory = postgres_database.new_session_factory(initialize=False)
    handled_scan_id = run_worker_once(
        postgres_database.session_factory,
        postgres_database.url.render_as_string(hide_password=False),
        WorkerSettings(max_attempts=max_attempts, idle_seconds=60),
    )

    assert handled_scan_id is None
    persisted = _read_scan_snapshot(reader_factory, scan_id)
    assert (persisted.status, persisted.attempts, persisted.claimed_at) == (
        "failed",
        max_attempts,
        old_claimed_at,
    )
    assert persisted.error == "abandoned by a previous worker; attempt budget exhausted"
    assert persisted.finished_at is not None


class _FindingArtifactSnapshot(NamedTuple):
    id: int
    scan_id: str
    repository_id: str
    policy_id: str
    policy_version: str
    status: str
    severity: str
    file_path: str | None
    start_line: int | None
    end_line: int | None
    fingerprint: str
    explanation: str | None
    remediation: str | None
    fix_json: dict[str, object] | None
    suppressed: bool


class _ScanArtifactSnapshot(NamedTuple):
    backend_pid: int
    id: str
    repository_id: str
    status: str
    trigger: str
    attempts: int
    created_at: datetime
    claimed_at: datetime | None
    finished_at: datetime | None
    result_fingerprint: str | None
    complete: bool | None
    report_json: dict[str, object] | None
    error: str | None
    findings: tuple[_FindingArtifactSnapshot, ...]


class _BlockedBackend(NamedTuple):
    pid: int
    state: str
    wait_event_type: str | None
    wait_event: str | None
    blocker_pids: tuple[int, ...]
    query: str


class _WorkerOutcome(NamedTuple):
    backend_pid: int
    applied: bool


def _report_for(label: str) -> ScanReport:
    """Return distinct canonical ingestion values for the PostgreSQL fence tests."""
    return ScanReport(
        complete=True,
        result_fingerprint=f"{label}-result-fingerprint",
        run=RunMetadata(
            tool_version="c26-postgres-fencing-test",
            policy_pack_id=label,
            policy_pack_version="1.0.0",
            timestamp=datetime.now(UTC),
        ),
        findings=[
            Finding(
                policy_id=f"{label}-policy",
                policy_version="1.0.0",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
                enforcement=EnforcementType.DETERMINISTIC,
                location=FindingLocation(file=Path(f"dags/{label}.py"), start_line=7, end_line=9),
                explanation=f"{label} explanation λ",
                remediation=f"{label} remediation",
                fix=RemediationPayload(
                    fix_kind="manual",
                    action=RemediationAction.MANUAL,
                    hint=f"{label} fix hint",
                ),
                fingerprint=f"{label}-finding-fingerprint",
                suppressed=True,
            )
        ],
    )


def _seed_running_scan_with_report(
    factory: sessionmaker[Session],
    scan_id: str,
    repository_id: str,
    report: ScanReport,
    claimed_at: datetime,
    *,
    attempts: int = 1,
) -> None:
    with factory() as session:
        _seed_repository(session, repository_id)
        scan = ScanRow(
            id=scan_id,
            repository_id=repository_id,
            status=ScanStatus.RUNNING.value,
            attempts=attempts,
            claimed_at=claimed_at,
            error="previous-attempt context",
        )
        session.add(scan)
        session.flush()
        _RUNNER_INGEST(session, scan, report)
        session.commit()


def _read_artifact_snapshot(session: Session, scan_id: str) -> _ScanArtifactSnapshot:
    """Read the full scan artifact and normalized findings using an independent reader."""
    session.expire_all()
    backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
    assert isinstance(backend_pid, int)
    scan = session.get(ScanRow, scan_id)
    assert scan is not None
    findings = session.scalars(select(FindingRow).where(FindingRow.scan_id == scan_id).order_by(FindingRow.id)).all()
    return _ScanArtifactSnapshot(
        backend_pid=backend_pid,
        id=scan.id,
        repository_id=scan.repository_id,
        status=scan.status,
        trigger=scan.trigger,
        attempts=scan.attempts,
        created_at=scan.created_at,
        claimed_at=scan.claimed_at,
        finished_at=scan.finished_at,
        result_fingerprint=scan.result_fingerprint,
        complete=scan.complete,
        report_json=scan.report_json,
        error=scan.error,
        findings=tuple(
            _FindingArtifactSnapshot(
                id=finding.id,
                scan_id=finding.scan_id,
                repository_id=finding.repository_id,
                policy_id=finding.policy_id,
                policy_version=finding.policy_version,
                status=finding.status,
                severity=finding.severity,
                file_path=finding.file_path,
                start_line=finding.start_line,
                end_line=finding.end_line,
                fingerprint=finding.fingerprint,
                explanation=finding.explanation,
                remediation=finding.remediation,
                fix_json=finding.fix_json,
                suppressed=finding.suppressed,
            )
            for finding in findings
        ),
    )


def _set_runner_race_timeouts(session: Session) -> None:
    """Lengthen only these race-test sessions' safety bounds, never their assertions."""
    session.execute(text(f"SET lock_timeout = '{_RACE_LOCK_TIMEOUT_MS}ms'"))
    session.execute(text(f"SET statement_timeout = '{_RACE_STATEMENT_TIMEOUT_MS}ms'"))


def _wait_for_backend_blocked_by(
    monitor: Session,
    waiting_pid: int,
    blocker_pid: int,
    worker_finished: Event,
) -> _BlockedBackend:
    """Observe a real PostgreSQL lock wait; polling duration is only a bounded failure guard."""
    query = text(
        "SELECT state, wait_event_type, wait_event, pg_blocking_pids(pid), query "
        "FROM pg_stat_activity "
        "WHERE pid = :waiting_pid AND datname = current_database()"
    )
    deadline = time.monotonic() + _ROW_LOCK_OBSERVATION_TIMEOUT_SECONDS
    while True:
        row = monitor.execute(query, {"waiting_pid": waiting_pid}).one_or_none()
        if row is not None:
            state = str(row[0])
            wait_event_type = str(row[1]) if row[1] is not None else None
            wait_event = str(row[2]) if row[2] is not None else None
            blocker_pids = tuple(int(pid) for pid in row[3])
            query_text = str(row[4])
            if state == "active" and wait_event_type == "Lock" and blocker_pid in blocker_pids:
                return _BlockedBackend(
                    waiting_pid,
                    state,
                    wait_event_type,
                    wait_event,
                    blocker_pids,
                    query_text,
                )
        if worker_finished.is_set():
            pytest.fail("The competing PostgreSQL writer completed before the expected row-lock wait was observed.")
        if time.monotonic() >= deadline:
            pytest.fail(f"Did not observe backend {waiting_pid} blocked by backend {blocker_pid} in pg_stat_activity.")
        # PostgreSQL's reported lock wait, not elapsed time, is the race assertion.
        time.sleep(0.025)


def _complete_in_worker(
    factory: sessionmaker[Session],
    scan_id: str,
    report: ScanReport,
    backend_pids: list[int],
    connected: Event,
    ingestion_staged: Event,
    transition_started: Event,
    finished: Event,
) -> _WorkerOutcome:
    try:
        with factory() as session:
            _set_runner_race_timeouts(session)
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(backend_pid, int)
            backend_pids.append(backend_pid)
            connected.set()
            scan = session.get(ScanRow, scan_id)
            assert scan is not None
            _RUNNER_INGEST(session, scan, report)
            ingestion_staged.set()
            transition_started.set()
            applied = transition_running_scan(
                session,
                scan_id,
                ScanStatus.SUCCEEDED,
                expected_attempt=1,
            )
            return _WorkerOutcome(backend_pid, applied)
    finally:
        finished.set()


def _cancel_in_worker(
    factory: sessionmaker[Session],
    scan_id: str,
    backend_pids: list[int],
    connected: Event,
    transition_started: Event,
    finished: Event,
) -> _WorkerOutcome:
    try:
        with factory() as session:
            _set_runner_race_timeouts(session)
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(backend_pid, int)
            backend_pids.append(backend_pid)
            connected.set()
            transition_started.set()
            applied = transition_scan_to_cancelled(session, scan_id)
            return _WorkerOutcome(backend_pid, applied)
    finally:
        finished.set()


def _assert_cancelled_with_original_artifacts(
    snapshot: _ScanArtifactSnapshot,
    original: _ScanArtifactSnapshot,
) -> None:
    assert snapshot.status == ScanStatus.CANCELLED.value
    assert snapshot.attempts == original.attempts
    assert snapshot.claimed_at is None
    assert snapshot.finished_at is not None
    assert snapshot.error == original.error
    assert snapshot.report_json == original.report_json
    assert snapshot.result_fingerprint == original.result_fingerprint
    assert snapshot.complete == original.complete
    assert snapshot.findings == original.findings


@pytest.mark.postgres
def test_stale_attempt_cannot_heartbeat_requeue_or_replace_newer_attempt_artifacts(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg06-fencing-repo"
    scan_id = "c26-pg06-reclaimed-scan"
    stale_claimed_at = datetime.now(UTC) - timedelta(hours=2)
    original_report = _report_for("pg06-original")
    _seed_running_scan_with_report(
        postgres_database.session_factory,
        scan_id,
        repository_id,
        original_report,
        stale_claimed_at,
    )

    claim_factory = postgres_database.new_session_factory(initialize=False)
    stale_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    reader = reader_factory()
    try:
        with claim_factory() as claimant:
            claimant_pid = claimant.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(claimant_pid, int)
            reclaimed = claim_queued_scan(claimant, datetime.now(UTC) - timedelta(hours=1), max_attempts=3)
            assert reclaimed is not None
            assert (reclaimed.id, reclaimed.status, reclaimed.attempts) == (scan_id, ScanStatus.RUNNING.value, 2)
            assert reclaimed.claimed_at is not None and reclaimed.claimed_at > stale_claimed_at
            newer_claimed_at = reclaimed.claimed_at
            claimant.commit()

        after_claim = _read_artifact_snapshot(reader, scan_id)
        assert after_claim.backend_pid != claimant_pid
        assert after_claim.status == ScanStatus.RUNNING.value
        assert after_claim.attempts == 2
        assert after_claim.claimed_at == newer_claimed_at
        assert after_claim.report_json == original_report.model_dump(mode="json")
        assert after_claim.result_fingerprint == original_report.result_fingerprint
        assert after_claim.complete is True
        assert len(after_claim.findings) == 1

        with stale_factory() as stale_heartbeat:
            assert heartbeat_running_scan(stale_heartbeat, scan_id, attempt=1) is False
        assert _read_artifact_snapshot(reader, scan_id) == after_claim

        with stale_factory() as stale_requeue:
            assert (
                transition_running_scan(
                    stale_requeue,
                    scan_id,
                    ScanStatus.QUEUED,
                    requeue=True,
                    expected_attempt=1,
                )
                is False
            )
        assert _read_artifact_snapshot(reader, scan_id) == after_claim

        stale_report = _report_for("pg06-stale-replacement")
        with stale_factory() as stale_finalizer:
            stale_scan = stale_finalizer.get(ScanRow, scan_id)
            assert stale_scan is not None
            _RUNNER_INGEST(stale_finalizer, stale_scan, stale_report)
            assert (
                transition_running_scan(
                    stale_finalizer,
                    scan_id,
                    ScanStatus.SUCCEEDED,
                    expected_attempt=1,
                )
                is False
            )
        assert _read_artifact_snapshot(reader, scan_id) == after_claim

        with stale_factory() as fresh_heartbeat:
            assert heartbeat_running_scan(fresh_heartbeat, scan_id, attempt=2) is True
        after_heartbeat = _read_artifact_snapshot(reader, scan_id)
        assert after_heartbeat.backend_pid == after_claim.backend_pid
        assert after_heartbeat.status == ScanStatus.RUNNING.value
        assert after_heartbeat.attempts == 2
        assert after_heartbeat.claimed_at is not None and after_heartbeat.claimed_at >= newer_claimed_at
        assert after_heartbeat.report_json == after_claim.report_json
        assert after_heartbeat.findings == after_claim.findings

        fresh_report = _report_for("pg06-current-replacement")
        with stale_factory() as fresh_finalizer:
            fresh_scan = fresh_finalizer.get(ScanRow, scan_id)
            assert fresh_scan is not None
            _RUNNER_INGEST(fresh_finalizer, fresh_scan, fresh_report)
            assert (
                transition_running_scan(
                    fresh_finalizer,
                    scan_id,
                    ScanStatus.SUCCEEDED,
                    expected_attempt=2,
                )
                is True
            )

        completed = _read_artifact_snapshot(reader, scan_id)
        assert completed.backend_pid == after_claim.backend_pid
        assert completed.status == ScanStatus.SUCCEEDED.value
        assert completed.attempts == 2
        assert completed.claimed_at is None
        assert completed.finished_at is not None
        assert completed.error is None
        assert completed.report_json == fresh_report.model_dump(mode="json")
        assert completed.result_fingerprint == fresh_report.result_fingerprint
        assert completed.complete is True
        assert [finding.fingerprint for finding in completed.findings] == [fresh_report.findings[0].fingerprint]
        fresh_fix = fresh_report.findings[0].fix
        assert fresh_fix is not None
        assert completed.findings[0].fix_json == fresh_fix.model_dump(mode="json")
    finally:
        reader.close()


@pytest.mark.postgres
def test_cancellation_wins_while_runner_autoflush_is_blocked_and_rolls_back_replacement(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg07-cancel-wins-repo"
    scan_id = "c26-pg07-cancel-wins-scan"
    original_report = _report_for("pg07-cancel-original")
    runner_report = _report_for("pg07-cancel-runner")
    _seed_running_scan_with_report(
        postgres_database.session_factory,
        scan_id,
        repository_id,
        original_report,
        datetime.now(UTC) - timedelta(minutes=1),
    )

    winner_factory = postgres_database.new_session_factory(initialize=False)
    runner_factory = postgres_database.new_session_factory(initialize=False)
    monitor_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    connected = Event()
    ingestion_staged = Event()
    transition_started = Event()
    worker_finished = Event()
    worker_backend_pids: list[int] = []

    with (
        ThreadPoolExecutor(max_workers=1) as executor,
        winner_factory() as cancellation_winner,
        monitor_factory() as monitor,
        reader_factory() as reader,
    ):
        _set_runner_race_timeouts(cancellation_winner)
        winner_pid = cancellation_winner.scalar(text("SELECT pg_backend_pid()"))
        monitor_pid = monitor.scalar(text("SELECT pg_backend_pid()"))
        original = _read_artifact_snapshot(reader, scan_id)
        assert isinstance(winner_pid, int) and isinstance(monitor_pid, int)
        assert original.status == ScanStatus.RUNNING.value
        assert len(original.findings) == 1
        locked_scan = cancellation_winner.scalars(select(ScanRow).where(ScanRow.id == scan_id).with_for_update()).one()
        assert locked_scan.status == ScanStatus.RUNNING.value

        future = executor.submit(
            _complete_in_worker,
            runner_factory,
            scan_id,
            runner_report,
            worker_backend_pids,
            connected,
            ingestion_staged,
            transition_started,
            worker_finished,
        )
        try:
            assert connected.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert ingestion_staged.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert transition_started.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert len(worker_backend_pids) == 1
            runner_pid = worker_backend_pids[0]
            assert len({winner_pid, runner_pid, monitor_pid, original.backend_pid}) == 4

            blocked = _wait_for_backend_blocked_by(monitor, runner_pid, winner_pid, worker_finished)
            assert blocked.wait_event_type == "Lock"
            blocked_query = blocked.query.upper()
            assert "INSERT INTO FINDINGS" in blocked_query or (
                "UPDATE SCANS SET" in blocked_query and "REPORT_JSON" in blocked_query
            )
            assert _read_artifact_snapshot(reader, scan_id) == original

            assert transition_scan_to_cancelled(cancellation_winner, scan_id) is True
        finally:
            if cancellation_winner.in_transaction():
                cancellation_winner.rollback()
            if not future.done():
                future.result(timeout=_RUNNER_RACE_WORKER_TIMEOUT_SECONDS)

        runner_outcome = future.result(timeout=_RUNNER_RACE_WORKER_TIMEOUT_SECONDS)
        assert runner_outcome.backend_pid == worker_backend_pids[0]
        assert runner_outcome.applied is False
        cancelled = _read_artifact_snapshot(reader, scan_id)
        assert cancelled.backend_pid == original.backend_pid
        _assert_cancelled_with_original_artifacts(cancelled, original)


@pytest.mark.postgres
def test_runner_flush_wins_before_cancel_and_later_cancellation_loses(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg07-runner-wins-repo"
    scan_id = "c26-pg07-runner-wins-scan"
    original_report = _report_for("pg07-runner-original")
    runner_report = _report_for("pg07-runner-winner")
    _seed_running_scan_with_report(
        postgres_database.session_factory,
        scan_id,
        repository_id,
        original_report,
        datetime.now(UTC) - timedelta(minutes=1),
    )

    runner_factory = postgres_database.new_session_factory(initialize=False)
    cancellation_factory = postgres_database.new_session_factory(initialize=False)
    monitor_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)
    connected = Event()
    transition_started = Event()
    worker_finished = Event()
    worker_backend_pids: list[int] = []

    with (
        ThreadPoolExecutor(max_workers=1) as executor,
        runner_factory() as runner_winner,
        monitor_factory() as monitor,
        reader_factory() as reader,
    ):
        _set_runner_race_timeouts(runner_winner)
        runner_pid = runner_winner.scalar(text("SELECT pg_backend_pid()"))
        monitor_pid = monitor.scalar(text("SELECT pg_backend_pid()"))
        original = _read_artifact_snapshot(reader, scan_id)
        assert isinstance(runner_pid, int) and isinstance(monitor_pid, int)
        assert original.status == ScanStatus.RUNNING.value
        assert len(original.findings) == 1

        runner_scan = runner_winner.get(ScanRow, scan_id)
        assert runner_scan is not None
        _RUNNER_INGEST(runner_winner, runner_scan, runner_report)
        runner_winner.flush()

        future = executor.submit(
            _cancel_in_worker,
            cancellation_factory,
            scan_id,
            worker_backend_pids,
            connected,
            transition_started,
            worker_finished,
        )
        try:
            assert connected.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert transition_started.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert len(worker_backend_pids) == 1
            cancellation_pid = worker_backend_pids[0]
            assert len({runner_pid, cancellation_pid, monitor_pid, original.backend_pid}) == 4

            blocked = _wait_for_backend_blocked_by(monitor, cancellation_pid, runner_pid, worker_finished)
            assert blocked.wait_event_type == "Lock"
            assert "UPDATE SCANS SET STATUS" in blocked.query.upper()
            assert _read_artifact_snapshot(reader, scan_id) == original

            assert (
                transition_running_scan(
                    runner_winner,
                    scan_id,
                    ScanStatus.SUCCEEDED,
                    expected_attempt=1,
                )
                is True
            )
        finally:
            if runner_winner.in_transaction():
                runner_winner.rollback()
            if not future.done():
                future.result(timeout=_RUNNER_RACE_WORKER_TIMEOUT_SECONDS)

        cancel_outcome = future.result(timeout=_RUNNER_RACE_WORKER_TIMEOUT_SECONDS)
        assert cancel_outcome.backend_pid == worker_backend_pids[0]
        assert cancel_outcome.applied is False
        completed = _read_artifact_snapshot(reader, scan_id)
        assert completed.backend_pid == original.backend_pid
        assert completed.status == ScanStatus.SUCCEEDED.value
        assert completed.attempts == original.attempts
        assert completed.claimed_at is None
        assert completed.finished_at is not None
        assert completed.error is None
        assert completed.report_json == runner_report.model_dump(mode="json")
        assert completed.result_fingerprint == runner_report.result_fingerprint
        assert completed.complete is True
        assert len(completed.findings) == 1
        assert completed.findings[0].fingerprint == runner_report.findings[0].fingerprint
        winner_fix = runner_report.findings[0].fix
        assert winner_fix is not None
        assert completed.findings[0].fix_json == winner_fix.model_dump(mode="json")


class _SuppressionWorkerOutcome(NamedTuple):
    backend_pid: int
    reused_backend_pid: int | None
    conflict_message: str | None
    rollback_restored_session: bool
    recovered_suppression_id: str | None


def _create_competing_suppression(
    factory: sessionmaker[Session],
    connected: Event,
    finished: Event,
    backend_pids: list[int],
) -> _SuppressionWorkerOutcome:
    """Try the contested identity, then recover and commit through that same Session."""
    try:
        with factory() as session:
            _set_runner_race_timeouts(session)
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(backend_pid, int)
            backend_pids.append(backend_pid)
            connected.set()
            try:
                create_suppression(
                    session,
                    policy_id="C26-PG08-contended-policy",
                    fingerprint="c" * 64,
                    reason="losing duplicate writer",
                    owner="pg08-loser",
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            except ConflictError as conflict:
                # C25 keeps rollback ownership with the caller, even after a failed flush.
                assert session.in_transaction()
                assert session.is_active is False
                session.rollback()
                restored = session.is_active and not session.in_transaction()
                reused_backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
                assert isinstance(reused_backend_pid, int)
                recovery = create_suppression(
                    session,
                    policy_id="C26-PG08-independent-b",
                    fingerprint="b" * 64,
                    reason="writer B independent write",
                    owner="pg08-writer-b",
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
                session.commit()
                return _SuppressionWorkerOutcome(
                    backend_pid,
                    reused_backend_pid,
                    str(conflict),
                    restored,
                    recovery.id,
                )

            session.commit()
            return _SuppressionWorkerOutcome(backend_pid, None, None, False, None)
    finally:
        finished.set()


@pytest.mark.postgres
def test_concurrent_suppression_conflict_rolls_back_and_reuses_losing_session(
    postgres_database: PostgresTestDatabase,
) -> None:
    """Exercise the actual unique-index wait and service conflict mapping on separate backends."""
    winner_factory = postgres_database.new_session_factory(initialize=False)
    competitor_factory = postgres_database.new_session_factory(initialize=False)
    monitor_factory = postgres_database.new_session_factory(initialize=False)
    connected = Event()
    worker_finished = Event()
    worker_backend_pids: list[int] = []

    with (
        ThreadPoolExecutor(max_workers=1) as executor,
        winner_factory() as winner,
        monitor_factory() as monitor,
    ):
        _set_runner_race_timeouts(winner)
        winner_pid = winner.scalar(text("SELECT pg_backend_pid()"))
        monitor_pid = monitor.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(winner_pid, int) and isinstance(monitor_pid, int)
        assert winner_pid != monitor_pid

        winning_suppression = create_suppression(
            winner,
            policy_id="C26-PG08-contended-policy",
            fingerprint="c" * 64,
            reason="winning duplicate writer",
            owner="pg08-winner",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        winner_independent = create_suppression(
            winner,
            policy_id="C26-PG08-independent-a",
            fingerprint="a" * 64,
            reason="writer A independent write",
            owner="pg08-writer-a",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert winner.in_transaction()

        future = executor.submit(
            _create_competing_suppression,
            competitor_factory,
            connected,
            worker_finished,
            worker_backend_pids,
        )
        try:
            assert connected.wait(timeout=_BACKEND_OBSERVATION_TIMEOUT_SECONDS)
            assert len(worker_backend_pids) == 1
            competitor_pid = worker_backend_pids[0]
            assert competitor_pid not in (winner_pid, monitor_pid)
            blocked = _wait_for_backend_blocked_by(monitor, competitor_pid, winner_pid, worker_finished)
            assert blocked.wait_event_type == "Lock"
            assert "INSERT INTO SUPPRESSIONS" in blocked.query.upper()
            assert winner.in_transaction(), "writer A must retain the unique-index conflict until commit"

            # The uncommitted winner and its independent write are invisible to another backend.
            with postgres_database.new_session_factory(initialize=False)() as reader:
                assert (
                    reader.scalar(
                        select(SuppressionRow).where(
                            SuppressionRow.policy_id == "C26-PG08-contended-policy",
                            SuppressionRow.fingerprint == "c" * 64,
                        )
                    )
                    is None
                )
                assert reader.scalar(select(SuppressionRow).where(SuppressionRow.id == winner_independent.id)) is None
            winner.commit()
        finally:
            if winner.in_transaction():
                winner.rollback()
            if not future.done():
                future.result(timeout=_RUNNER_RACE_WORKER_TIMEOUT_SECONDS)

        outcome = future.result(timeout=_RUNNER_RACE_WORKER_TIMEOUT_SECONDS)
        assert outcome.backend_pid == competitor_pid
        assert outcome.reused_backend_pid == outcome.backend_pid
        assert outcome.conflict_message == "suppression already exists for this policy finding"
        assert outcome.rollback_restored_session is True
        assert outcome.recovered_suppression_id is not None

    reader_factory = postgres_database.new_session_factory(initialize=False)
    with reader_factory() as reader:
        identity_rows = reader.scalars(
            select(SuppressionRow).where(
                SuppressionRow.policy_id == "C26-PG08-contended-policy",
                SuppressionRow.fingerprint == "c" * 64,
            )
        ).all()
        assert len(identity_rows) == 1
        assert identity_rows[0].id == winning_suppression.id
        assert identity_rows[0].reason == "winning duplicate writer"

        independent_rows = reader.scalars(
            select(SuppressionRow).where(
                SuppressionRow.policy_id.in_(["C26-PG08-independent-a", "C26-PG08-independent-b"])
            )
        ).all()
        assert {(row.policy_id, row.fingerprint, row.reason) for row in independent_rows} == {
            ("C26-PG08-independent-a", "a" * 64, "writer A independent write"),
            ("C26-PG08-independent-b", "b" * 64, "writer B independent write"),
        }
        assert {row.id for row in independent_rows} == {winner_independent.id, outcome.recovered_suppression_id}


@pytest.mark.postgres
def test_baseline_eligibility_and_retention_keep_zero_preserve_newest_scan_row(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg09-repo"
    other_repository_id = "c26-pg09-other-repo"
    t0 = datetime(2026, 3, 1, tzinfo=UTC)
    t1 = datetime(2026, 3, 2, tzinfo=UTC)
    t2 = datetime(2026, 3, 3, tzinfo=UTC)
    baseline_id = "c26-pg09-baseline"
    failed_id = "c26-pg09-failed"
    incomplete_id = "c26-pg09-incomplete"
    tied_lower_id = "c26-pg09-tie-a"
    tied_higher_id = "c26-pg09-tie-z"
    newest_null_report_id = "c26-pg09-newest-null-report"
    baseline_fingerprint = "9" * 64
    scan_rows = [
        ScanRow(
            id=failed_id,
            repository_id=repository_id,
            status=ScanStatus.FAILED.value,
            complete=True,
            created_at=t0 - timedelta(days=2),
            result_fingerprint="f" * 64,
            report_json={"failure": True},
        ),
        ScanRow(
            id=incomplete_id,
            repository_id=repository_id,
            status=ScanStatus.SUCCEEDED.value,
            complete=False,
            created_at=t0 - timedelta(days=1),
            result_fingerprint="i" * 64,
            report_json={"complete": False},
        ),
        ScanRow(
            id=baseline_id,
            repository_id=repository_id,
            status=ScanStatus.SUCCEEDED.value,
            complete=True,
            created_at=t0,
            result_fingerprint="r" * 64,
            report_json={"baseline": "will be pruned"},
        ),
        ScanRow(
            id=tied_lower_id,
            repository_id=repository_id,
            status=ScanStatus.SUCCEEDED.value,
            complete=True,
            created_at=t1,
            result_fingerprint="a" * 64,
            report_json={"tie": "a"},
        ),
        ScanRow(
            id=tied_higher_id,
            repository_id=repository_id,
            status=ScanStatus.SUCCEEDED.value,
            complete=True,
            created_at=t1,
            result_fingerprint="z" * 64,
            report_json={"tie": "z"},
        ),
        ScanRow(
            id=newest_null_report_id,
            repository_id=repository_id,
            status=ScanStatus.QUEUED.value,
            complete=None,
            created_at=t2,
            result_fingerprint="n" * 64,
            report_json=None,
        ),
        ScanRow(
            id="c26-pg09-other-repository-succeeded",
            repository_id=other_repository_id,
            status=ScanStatus.SUCCEEDED.value,
            complete=True,
            created_at=t2,
            result_fingerprint="o" * 64,
            report_json={"other": True},
        ),
    ]

    with postgres_database.session_factory() as setup:
        setup.add_all(
            [
                RepositoryRow(
                    id=repository_id,
                    name="C26 PG09 primary repository",
                    path="dags/c26_pg09",
                    baseline_scan_id=None,
                ),
                RepositoryRow(
                    id=other_repository_id,
                    name="C26 PG09 other repository",
                    path="dags/c26_pg09_other",
                ),
                *scan_rows,
            ]
        )
        setup.flush()
        setup.add_all(
            [
                FindingRow(
                    scan_id=scan.id,
                    repository_id=scan.repository_id,
                    policy_id="C26-PG09",
                    policy_version="1.0.0",
                    status="violation",
                    severity="high",
                    fingerprint=baseline_fingerprint if scan.id == baseline_id else f"fingerprint-{scan.id}",
                )
                for scan in scan_rows
            ]
        )
        setup.commit()

    with postgres_database.session_factory() as eligibility:
        assignment = set_baseline(eligibility, repository_id, baseline_id)
        eligibility.commit()
        assert assignment.baseline_scan_id == baseline_id
        assert eligible_baseline(eligibility, repository_id, baseline_id) is not None
        assert eligible_baseline(eligibility, repository_id, "c26-pg09-other-repository-succeeded") is None
        assert eligible_baseline(eligibility, repository_id, failed_id) is None
        assert eligible_baseline(eligibility, repository_id, incomplete_id) is None
        assert eligible_baseline(eligibility, repository_id, newest_null_report_id) is None

    retention_factory = postgres_database.new_session_factory(initialize=False)
    with retention_factory() as retention:
        # The lexically greatest ID wins an equal-created_at tie in the newest set.
        assert retention_target_scan_ids(retention, repository_id, keep=2) == [
            failed_id,
            incomplete_id,
            baseline_id,
            tied_lower_id,
        ]
        targets = retention_target_scan_ids(retention, repository_id, keep=0)
        assert targets == [failed_id, incomplete_id, baseline_id, tied_lower_id, tied_higher_id]
        for scan_id in targets:
            prune_scan_artifact(retention, scan_id)
        retention.commit()

    reader_factory = postgres_database.new_session_factory(initialize=False)
    with reader_factory() as reader:
        scans = {
            scan.id: scan for scan in reader.scalars(select(ScanRow).where(ScanRow.repository_id == repository_id))
        }
        assert set(scans) == {
            failed_id,
            incomplete_id,
            baseline_id,
            tied_lower_id,
            tied_higher_id,
            newest_null_report_id,
        }
        for scan_id in targets:
            scan = scans[scan_id]
            original_scan = next(row for row in scan_rows if row.id == scan_id)
            assert scan.report_json is None
            assert scan.status == original_scan.status
            assert scan.created_at == original_scan.created_at
            assert scan.result_fingerprint == original_scan.result_fingerprint
            assert scan.complete is original_scan.complete
            findings = reader.scalars(select(FindingRow).where(FindingRow.scan_id == scan_id)).all()
            expected_fingerprint = baseline_fingerprint if scan_id == baseline_id else f"fingerprint-{scan_id}"
            assert [finding.fingerprint for finding in findings] == [expected_fingerprint]

        protected = scans[newest_null_report_id]
        assert protected.report_json is None
        assert protected.status == ScanStatus.QUEUED.value
        assert protected.result_fingerprint == "n" * 64
        baseline = eligible_baseline(reader, repository_id, baseline_id)
        assert baseline is not None
        assert baseline.status == ScanStatus.SUCCEEDED.value and baseline.complete is True
        repository = reader.get(RepositoryRow, repository_id)
        assert repository is not None and repository.baseline_scan_id == baseline_id
        resolved_baseline = _RUNNER_BASELINE(reader, repository_id, repository.baseline_scan_id)
        assert resolved_baseline is not None
        assert resolved_baseline.fingerprints == frozenset({baseline_fingerprint})


@pytest.mark.postgres
def test_nested_scan_report_and_fix_round_trip_through_fenced_runner_ingestion_as_jsonb(
    postgres_database: PostgresTestDatabase,
) -> None:
    repository_id = "c26-pg10-jsonb-repo"
    scan_id = "c26-pg10-jsonb-scan"
    claimed_at = datetime.now(UTC) - timedelta(minutes=1)
    original_report = _report_for("pg10-before")
    _seed_running_scan_with_report(
        postgres_database.session_factory,
        scan_id,
        repository_id,
        original_report,
        claimed_at,
    )

    report = ScanReport(
        complete=True,
        result_fingerprint="c26-pg10-result-fingerprint",
        files_scanned=[Path("dags/café.py"), Path("dags/nested.py")],
        policies_evaluated=["C26-PG10"],
        policies_skipped=["optional-check"],
        findings=[
            Finding(
                policy_id="C26-PG10",
                policy_version="1.0.0",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
                enforcement=EnforcementType.DETERMINISTIC,
                location=FindingLocation(file=Path("dags/café.py"), start_line=12, end_line=14),
                evidence=FindingEvidence(text="nested Unicode evidence λ 雪", start_line=12, end_line=14),
                explanation="contains a real nested report value",
                remediation=None,
                fix=RemediationPayload(
                    fix_kind="owner-field",
                    action=RemediationAction.SET_KWARG,
                    kwarg="owner",
                    target=RemediationTarget(line=12, column=4, enclosing="dag", node="dag-call"),
                    value="data-platform",
                    hint=None,
                ),
                fingerprint="c26-pg10-finding-fingerprint",
                suppressed=False,
            )
        ],
        issues=[
            RunIssue(
                code="PG10-INFO",
                message="non-fatal Unicode issue é",
                path=Path("dags/café.py"),
                phase="scan",
                fatal=False,
            )
        ],
        run=RunMetadata(
            tool_version="c26-postgres-jsonb-test",
            input_hashes={"dags/café.py": "hash-λ"},
            policy_pack_id="c26-pg10",
            policy_pack_version="1.0.0",
            resolved_configuration={
                "enabled": True,
                "optional": None,
                "unicode": "configuration 雪",
                "steps": [
                    {
                        "name": "prepare",
                        "active": False,
                        "attributes": {"values": [None, True, {"nested": "λ"}]},
                    },
                    {"name": "finish", "active": True, "attributes": {}},
                ],
            },
            environment={"LANG": "C.UTF-8"},
            timestamp=datetime(2026, 4, 5, 6, 7, 8, tzinfo=UTC),
        ),
    )
    expected_json = report.model_dump(mode="json")
    expected_fix_json = report.findings[0].fix.model_dump(mode="json") if report.findings[0].fix else None
    assert expected_fix_json is not None

    completion_factory = postgres_database.new_session_factory(initialize=False)
    with completion_factory() as completion:
        completion_backend_pid = completion.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(completion_backend_pid, int)
        scan = completion.get(ScanRow, scan_id)
        assert scan is not None
        _RUNNER_INGEST(completion, scan, report)
        assert (
            transition_running_scan(
                completion,
                scan_id,
                ScanStatus.SUCCEEDED,
                expected_attempt=1,
            )
            is True
        )
        assert not completion.in_transaction(), "the fenced winning transition owns its commit"

    inspector = inspect(_factory_engine(postgres_database.session_factory))
    scan_column_types = {column["name"]: column["type"] for column in inspector.get_columns("scans", schema="public")}
    finding_column_types = {
        column["name"]: column["type"] for column in inspector.get_columns("findings", schema="public")
    }
    assert isinstance(scan_column_types["report_json"], JSONB)
    assert isinstance(finding_column_types["fix_json"], JSONB)

    reader_factory = postgres_database.new_session_factory(initialize=False)
    with reader_factory() as reader:
        snapshot = _read_artifact_snapshot(reader, scan_id)
        assert snapshot.backend_pid != completion_backend_pid
        assert snapshot.status == ScanStatus.SUCCEEDED.value
        assert snapshot.attempts == 1
        assert snapshot.report_json == expected_json == report.model_dump(mode="json")
        assert snapshot.result_fingerprint == report.result_fingerprint == "c26-pg10-result-fingerprint"
        assert snapshot.complete is report.complete is True
        assert len(snapshot.findings) == 1
        finding = snapshot.findings[0]
        assert finding.fingerprint == report.findings[0].fingerprint == "c26-pg10-finding-fingerprint"
        assert finding.fix_json == expected_fix_json
        assert expected_json["run"]["resolved_configuration"] == {
            "enabled": True,
            "optional": None,
            "unicode": "configuration 雪",
            "steps": [
                {"name": "prepare", "active": False, "attributes": {"values": [None, True, {"nested": "λ"}]}},
                {"name": "finish", "active": True, "attributes": {}},
            ],
        }


@pytest.mark.postgres
def test_flush_failure_rollback_isolated_and_same_session_reusable(
    postgres_database: PostgresTestDatabase,
) -> None:
    failed_repository_id = "c26-pg11-rolled-back-repo"
    orphan_scan_id = "c26-pg11-orphan-scan"
    recovered_repository_id = "c26-pg11-recovered-repo"
    writer_factory = postgres_database.new_session_factory(initialize=False)
    reader_factory = postgres_database.new_session_factory(initialize=False)

    with writer_factory() as writer:
        original_backend_pid = writer.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(original_backend_pid, int)
        writer.add(
            RepositoryRow(
                id=failed_repository_id,
                name="C26 PG11 repository preceding foreign-key failure",
                path="dags/c26_pg11_rolled_back",
            )
        )
        writer.flush()
        writer.add(
            ScanRow(
                id=orphan_scan_id,
                repository_id="c26-pg11-missing-parent",
                status=ScanStatus.QUEUED.value,
            )
        )
        with pytest.raises(IntegrityError):
            writer.flush()

        assert writer.is_active is False
        writer.rollback()
        assert writer.is_active is True
        assert not writer.in_transaction()
        assert writer.scalar(text("SELECT pg_backend_pid()")) == original_backend_pid

        with reader_factory() as reader:
            assert reader.get(RepositoryRow, failed_repository_id) is None
            assert reader.get(ScanRow, orphan_scan_id) is None

        writer.add(
            RepositoryRow(
                id=recovered_repository_id,
                name="C26 PG11 same-session recovery",
                path="dags/c26_pg11_recovered",
            )
        )
        writer.commit()

    with reader_factory() as reader:
        assert reader.get(RepositoryRow, failed_repository_id) is None
        assert reader.get(ScanRow, orphan_scan_id) is None
        recovered = reader.get(RepositoryRow, recovered_repository_id)
        assert recovered is not None
        assert recovered.name == "C26 PG11 same-session recovery"


@pytest.mark.postgres
def test_disposable_database_cleanup_removes_only_its_owned_database_and_backends(
    postgres_admin: PostgresAdmin,
) -> None:
    owned_database_name: str | None = None
    backend_pid: int | None = None

    with postgres_admin.disposable_database() as database:
        owned_database_name = database.name
        assert owned_database_name.startswith("conformdag_c26_")
        factory = database.initialize()
        with factory() as session:
            backend_pid = session.scalar(text("SELECT pg_backend_pid()"))
            active_database = session.scalar(text("SELECT current_database()"))
            assert isinstance(backend_pid, int)
            assert active_database == owned_database_name

    assert owned_database_name is not None
    assert backend_pid is not None
    with postgres_admin.engine.connect() as maintenance:
        remaining_databases = (
            maintenance.execute(
                text("SELECT datname FROM pg_database WHERE datname = :owned_name"),
                {"owned_name": owned_database_name},
            )
            .scalars()
            .all()
        )
        remaining_backends = (
            maintenance.execute(
                text("SELECT pid FROM pg_stat_activity WHERE datname = :owned_name"),
                {"owned_name": owned_database_name},
            )
            .scalars()
            .all()
        )

    assert remaining_databases == []
    assert remaining_backends == []
    assert owned_database_name not in postgres_admin.owned_database_names
