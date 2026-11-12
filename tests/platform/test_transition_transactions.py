"""Real-database transaction-boundary tests for fenced scan transitions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from conformdag.models import (
    EnforcementType,
    Finding,
    FindingLocation,
    FindingStatus,
    RunMetadata,
    ScanReport,
    Severity,
)
from conformdag.platform import runner as runner_module
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    heartbeat_running_scan,
    initialize_session_factory,
    transition_running_scan,
    transition_scan_to_cancelled,
)
from conformdag.platform.domain import ScanStatus

_runner_ingest = cast("Callable[[Session, ScanRow, ScanReport], None]", runner_module.__dict__["_ingest"])


class _InjectedFailure(RuntimeError):
    """A deterministic SQL or pre-commit failure injected at the DB boundary."""


def _factory(tmp_path: Path, name: str = "platform.sqlite") -> sessionmaker[Session]:
    """Create a real SQLite database through the production Alembic startup path."""
    return initialize_session_factory(f"sqlite:///{tmp_path / name}")


def _report() -> ScanReport:
    """Return a canonical report containing one normalized finding."""
    return ScanReport(
        complete=True,
        result_fingerprint="new-report-fingerprint",
        run=RunMetadata(
            tool_version="transaction-test",
            policy_pack_id="transaction-test",
            policy_pack_version="1.0.0",
            timestamp=datetime.now(UTC),
        ),
        findings=[
            Finding(
                policy_id="AIR-TEST-001",
                policy_version="1.0.0",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
                enforcement=EnforcementType.DETERMINISTIC,
                location=FindingLocation(file=Path("dags/new.py"), start_line=3),
                fingerprint="new-finding-fingerprint",
            )
        ],
    )


def _seed_scan(factory: sessionmaker[Session], *, status: ScanStatus = ScanStatus.RUNNING, attempts: int = 1) -> None:
    """Create a scan with an earlier persisted report and finding to replace."""
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="repo", path="."))
        session.add(
            ScanRow(
                id="scan",
                repository_id="repo",
                status=status.value,
                attempts=attempts,
                report_json={"artifact": "previous"},
                result_fingerprint="previous-report-fingerprint",
                complete=False,
            )
        )
        session.add(
            FindingRow(
                scan_id="scan",
                repository_id="repo",
                policy_id="AIR-TEST-000",
                policy_version="1.0.0",
                status="FAIL",
                severity="high",
                fingerprint="previous-finding-fingerprint",
            )
        )
        session.commit()


def _assert_previous_ingestion(factory: sessionmaker[Session], *, status: ScanStatus, attempts: int) -> None:
    """Use an independent reader to verify old report/finding data remains durable."""
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == status.value
        assert scan.attempts == attempts
        assert scan.report_json == {"artifact": "previous"}
        assert scan.result_fingerprint == "previous-report-fingerprint"
        assert scan.complete is False
        findings = reader.scalars(select(FindingRow).where(FindingRow.scan_id == "scan")).all()
        assert [finding.fingerprint for finding in findings] == ["previous-finding-fingerprint"]


def test_fenced_completion_commits_runner_report_and_findings_together(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    _seed_scan(factory)
    report = _report()

    with factory() as runner_session:
        scan = runner_session.get(ScanRow, "scan")
        assert scan is not None
        _runner_ingest(runner_session, scan, report)
        assert transition_running_scan(runner_session, "scan", ScanStatus.SUCCEEDED, expected_attempt=1) is True

        # Read from a second session while the runner's session remains open.
        with factory() as reader:
            persisted_scan = reader.get(ScanRow, "scan")
            assert persisted_scan is not None
            assert persisted_scan.status == ScanStatus.SUCCEEDED.value
            assert persisted_scan.finished_at is not None
            assert persisted_scan.report_json == report.model_dump(mode="json")
            assert persisted_scan.result_fingerprint == report.result_fingerprint
            assert persisted_scan.complete is True
            findings = reader.scalars(select(FindingRow).where(FindingRow.scan_id == "scan")).all()
            assert [finding.fingerprint for finding in findings] == ["new-finding-fingerprint"]


@pytest.mark.parametrize("helper", ["running", "cancel", "heartbeat"])
def test_conditional_winner_commits_every_staged_session_change(tmp_path: Path, helper: str) -> None:
    """The helpers commit all session work; unrelated staged writes are hazardous, not a recipe."""
    factory = _factory(tmp_path)
    _seed_scan(factory)

    with factory() as writer:
        # This unrelated row intentionally characterizes the helper's whole-session commit scope.
        # Callers must not leave unrelated changes staged when invoking a transition helper.
        writer.add(RepositoryRow(id="unrelated", name="unrelated", path="."))
        if helper == "running":
            won = transition_running_scan(writer, "scan", ScanStatus.SUCCEEDED, expected_attempt=1)
        elif helper == "cancel":
            won = transition_scan_to_cancelled(writer, "scan")
        else:
            won = heartbeat_running_scan(writer, "scan", 1)
        assert won is True

    # A separate session sees the committed row and scan state.
    with factory() as reader:
        assert reader.get(RepositoryRow, "unrelated") is not None
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        if helper == "running":
            assert scan.status == ScanStatus.SUCCEEDED.value
            assert scan.finished_at is not None
        elif helper == "cancel":
            assert scan.status == ScanStatus.CANCELLED.value
        else:
            assert scan.status == ScanStatus.RUNNING.value
            assert scan.claimed_at is not None


def test_stale_heartbeat_rolls_back_other_pending_session_changes(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    _seed_scan(factory, attempts=2)

    with factory() as writer:
        writer.add(RepositoryRow(id="unrelated", name="unrelated", path="."))
        assert heartbeat_running_scan(writer, "scan", 1) is False

    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 2
        assert scan.claimed_at is None
        assert reader.get(RepositoryRow, "unrelated") is None


@pytest.mark.parametrize(
    ("status", "attempts", "expected_attempt"),
    [
        (ScanStatus.RUNNING, 2, 1),
        (ScanStatus.SUCCEEDED, 1, 1),
    ],
    ids=["stale-attempt", "terminal-row"],
)
def test_fenced_completion_loss_rolls_back_runner_ingestion_and_other_pending_work(
    tmp_path: Path, status: ScanStatus, attempts: int, expected_attempt: int
) -> None:
    factory = _factory(tmp_path)
    _seed_scan(factory, status=status, attempts=attempts)

    with factory() as runner_session:
        scan = runner_session.get(ScanRow, "scan")
        assert scan is not None
        _runner_ingest(runner_session, scan, _report())
        runner_session.add(RepositoryRow(id="unrelated", name="unrelated", path="."))

        assert (
            transition_running_scan(
                runner_session,
                "scan",
                ScanStatus.SUCCEEDED,
                expected_attempt=expected_attempt,
            )
            is False
        )

    _assert_previous_ingestion(factory, status=status, attempts=attempts)
    with factory() as reader:
        assert reader.get(RepositoryRow, "unrelated") is None


def test_cancellation_wins_once_and_late_runner_ingestion_is_rolled_back(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    _seed_scan(factory)

    with factory() as cancellation_winner:
        assert transition_scan_to_cancelled(cancellation_winner, "scan") is True

    with factory() as stale_runner:
        scan = stale_runner.get(ScanRow, "scan")
        assert scan is not None
        _runner_ingest(stale_runner, scan, _report())
        assert transition_running_scan(stale_runner, "scan", ScanStatus.SUCCEEDED, expected_attempt=1) is False

    with factory() as cancellation_loser:
        cancellation_loser.add(RepositoryRow(id="cancel-loser", name="cancel-loser", path="."))
        assert transition_scan_to_cancelled(cancellation_loser, "scan") is False

    _assert_previous_ingestion(factory, status=ScanStatus.CANCELLED, attempts=1)
    with factory() as reader:
        assert reader.get(RepositoryRow, "cancel-loser") is None


def test_sql_execute_failure_propagates_and_caller_rollback_discards_ingestion(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    _seed_scan(factory)
    engine = factory.kw["bind"]
    assert isinstance(engine, Engine)
    injected: list[str] = []

    def fail_transition_update(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("UPDATE SCANS SET STATUS"):
            injected.append("update")
            raise _InjectedFailure("injected conditional UPDATE failure")

    event.listen(engine, "before_cursor_execute", fail_transition_update)
    try:
        with factory() as caller:
            scan = caller.get(ScanRow, "scan")
            assert scan is not None
            _runner_ingest(caller, scan, _report())
            caller.add(RepositoryRow(id="unrelated", name="unrelated", path="."))
            with pytest.raises(_InjectedFailure, match="conditional UPDATE failure"):
                transition_running_scan(caller, "scan", ScanStatus.SUCCEEDED, expected_attempt=1)
            # The transition helper only handles conditional loss; exception cleanup belongs here.
            caller.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", fail_transition_update)

    assert injected == ["update"]
    _assert_previous_ingestion(factory, status=ScanStatus.RUNNING, attempts=1)
    with factory() as reader:
        assert reader.get(RepositoryRow, "unrelated") is None


def test_precommit_failure_propagates_and_caller_rollback_discards_ingestion(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    _seed_scan(factory)
    before_commit_calls = 0

    def fail_before_commit(_session: Session) -> None:
        nonlocal before_commit_calls
        before_commit_calls += 1
        raise _InjectedFailure("injected before-commit failure")

    with factory() as caller:
        scan = caller.get(ScanRow, "scan")
        assert scan is not None
        _runner_ingest(caller, scan, _report())
        caller.add(RepositoryRow(id="unrelated", name="unrelated", path="."))
        event.listen(caller, "before_commit", fail_before_commit)
        with pytest.raises(_InjectedFailure, match="before-commit failure"):
            transition_running_scan(caller, "scan", ScanStatus.SUCCEEDED, expected_attempt=1)
        # Do not treat a failed commit as an implicit rollback by the helper.
        caller.rollback()

    assert before_commit_calls == 1
    _assert_previous_ingestion(factory, status=ScanStatus.RUNNING, attempts=1)
    with factory() as reader:
        assert reader.get(RepositoryRow, "unrelated") is None
