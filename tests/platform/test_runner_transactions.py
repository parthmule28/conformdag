"""Runner-level transaction tests for atomic report ingestion and fenced completion."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from conformdag.application import EffectiveScanConfiguration, ScanExecutionResult, ScanOptions, ScanOverrides
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingLocation,
    FindingStatus,
    RunIssue,
    RunMetadata,
    ScanReport,
    Severity,
)
from conformdag.platform import runner as runner_module
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    initialize_session_factory,
    transition_scan_to_cancelled,
)
from conformdag.platform.domain import ScanStatus

_PREVIOUS_REPORT: dict[str, object] = {"artifact": "previous-attempt", "generation": 7}
_PREVIOUS_FINDINGS: tuple[tuple[object, ...], ...] = (
    (
        101,
        "OLD-POLICY-001",
        "0.9.0",
        "FAIL",
        "critical",
        "dags/previous_one.py",
        17,
        19,
        "previous-finding-fingerprint-1",
        "keep explanation one",
        "keep remediation one",
        {"action": "preserve", "line": 17},
        False,
    ),
    (
        102,
        "OLD-POLICY-002",
        "0.8.0",
        "PASS",
        "low",
        "dags/previous_two.py",
        29,
        None,
        "previous-finding-fingerprint-2",
        "keep explanation two",
        None,
        None,
        True,
    ),
)


class _InjectedFailure(RuntimeError):
    """Deterministic failure injected at a real runner SQL/flush boundary."""


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    """Create a real file-backed SQLite database through the Alembic startup path."""
    return initialize_session_factory(f"sqlite:///{tmp_path / 'runner-transactions.sqlite'}")


def _seed_running_attempt(factory: sessionmaker[Session], repository_root: Path) -> None:
    """Persist a RUNNING attempt with a previous report and two normalized findings."""
    repository_root.mkdir()
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="transaction-test", path=str(repository_root)))
        session.add(
            ScanRow(
                id="scan",
                repository_id="repo",
                status=ScanStatus.RUNNING.value,
                attempts=1,
                report_json=_PREVIOUS_REPORT,
                result_fingerprint="previous-report-fingerprint",
                complete=False,
            )
        )
        session.add_all(
            [
                FindingRow(
                    id=101,
                    scan_id="scan",
                    repository_id="repo",
                    policy_id="OLD-POLICY-001",
                    policy_version="0.9.0",
                    status="FAIL",
                    severity="critical",
                    file_path="dags/previous_one.py",
                    start_line=17,
                    end_line=19,
                    fingerprint="previous-finding-fingerprint-1",
                    explanation="keep explanation one",
                    remediation="keep remediation one",
                    fix_json={"action": "preserve", "line": 17},
                    suppressed=False,
                ),
                FindingRow(
                    id=102,
                    scan_id="scan",
                    repository_id="repo",
                    policy_id="OLD-POLICY-002",
                    policy_version="0.8.0",
                    status="PASS",
                    severity="low",
                    file_path="dags/previous_two.py",
                    start_line=29,
                    end_line=None,
                    fingerprint="previous-finding-fingerprint-2",
                    explanation="keep explanation two",
                    remediation=None,
                    fix_json=None,
                    suppressed=True,
                ),
            ]
        )
        session.commit()


def _finding_contents(row: FindingRow) -> tuple[object, ...]:
    return (
        row.id,
        row.policy_id,
        row.policy_version,
        row.status,
        row.severity,
        row.file_path,
        row.start_line,
        row.end_line,
        row.fingerprint,
        row.explanation,
        row.remediation,
        row.fix_json,
        row.suppressed,
    )


def _assert_previous_attempt(factory: sessionmaker[Session], *, status: ScanStatus, attempts: int) -> None:
    """Read committed state independently and prove the previous artifact is unchanged."""
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == status.value
        assert scan.attempts == attempts
        assert scan.report_json == _PREVIOUS_REPORT
        assert scan.result_fingerprint == "previous-report-fingerprint"
        assert scan.complete is False
        findings = reader.scalars(select(FindingRow).where(FindingRow.scan_id == "scan").order_by(FindingRow.id)).all()
        assert tuple(_finding_contents(row) for row in findings) == _PREVIOUS_FINDINGS


def _report(*, complete: bool = True) -> ScanReport:
    findings = [
        Finding(
            policy_id="NEW-POLICY-001",
            policy_version="1.2.0",
            status=FindingStatus.FAIL,
            severity=Severity.HIGH,
            enforcement=EnforcementType.DETERMINISTIC,
            location=FindingLocation(file=Path("dags/new_one.py"), start_line=3, end_line=5),
            fingerprint="new-finding-fingerprint-1",
            explanation="new explanation one",
            remediation="new remediation one",
        ),
        Finding(
            policy_id="NEW-POLICY-002",
            policy_version="2.0.0",
            status=FindingStatus.PASS,
            severity=Severity.LOW,
            enforcement=EnforcementType.DETERMINISTIC,
            location=FindingLocation(file=Path("dags/new_two.py"), start_line=11),
            fingerprint="new-finding-fingerprint-2",
            explanation="new explanation two",
        ),
    ]
    issues = [RunIssue(code="C25_INCOMPLETE", message="controlled incomplete result", phase="discovery", fatal=True)]
    return ScanReport(
        complete=complete,
        result_fingerprint="new-report-fingerprint",
        run=RunMetadata(
            tool_version="runner-transaction-test",
            policy_pack_id="runner-transaction-test",
            policy_pack_version="1.0.0",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        findings=findings,
        issues=issues if not complete else [],
    )


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch,
    factory: sessionmaker[Session],
    report: ScanReport,
    *,
    after_flush: Callable[[Session, Any], None] | None = None,
) -> None:
    """Route the public runner through the real database and a deterministic application result."""

    def create_runner_factory(_dsn: str) -> Callable[[], Session]:
        def create_session() -> Session:
            session = factory()
            if after_flush is not None:
                event.listen(session, "after_flush_postexec", after_flush)
            return session

        return create_session

    def resolve_configuration(
        _repository_root: Path, *, platform_overrides: ScanOverrides
    ) -> EffectiveScanConfiguration:
        del platform_overrides
        return cast("EffectiveScanConfiguration", object())

    def execute_application(
        _options: ScanOptions,
        _configuration: EffectiveScanConfiguration,
        **_kwargs: object,
    ) -> ScanExecutionResult:
        return ScanExecutionResult(report=report, gate_result=report.gate_result)

    monkeypatch.setattr(runner_module, "create_session_factory", create_runner_factory)
    monkeypatch.setattr(runner_module, "resolve_effective_configuration", resolve_configuration)
    monkeypatch.setattr(runner_module, "execute_application_scan", execute_application)


def _assert_new_report_committed(factory: sessionmaker[Session], report: ScanReport) -> None:
    expected_status = ScanStatus.SUCCEEDED if report.complete else ScanStatus.FAILED
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == expected_status.value
        assert scan.attempts == 1
        assert scan.finished_at is not None
        assert scan.report_json == report.model_dump(mode="json")
        assert scan.result_fingerprint == report.result_fingerprint
        assert scan.complete is report.complete
        if report.complete:
            assert scan.error is None
        else:
            assert scan.error == "scan incomplete: C25_INCOMPLETE: controlled incomplete result"

        findings = reader.scalars(select(FindingRow).where(FindingRow.scan_id == "scan").order_by(FindingRow.id)).all()
        assert [row.id not in {101, 102} for row in findings] == [True, True]
        assert [row.policy_id for row in findings] == ["NEW-POLICY-001", "NEW-POLICY-002"]
        assert [row.policy_version for row in findings] == ["1.2.0", "2.0.0"]
        assert [row.fingerprint for row in findings] == [
            "new-finding-fingerprint-1",
            "new-finding-fingerprint-2",
        ]
        assert [row.file_path for row in findings] == ["dags/new_one.py", "dags/new_two.py"]
        assert [row.start_line for row in findings] == [3, 11]
        assert [row.end_line for row in findings] == [5, None]
        assert [row.explanation for row in findings] == ["new explanation one", "new explanation two"]


@pytest.mark.parametrize(
    ("complete", "expected_exit"),
    [(True, 0), (False, 1)],
    ids=["complete-success", "incomplete-failure"],
)
def test_runner_fenced_completion_exposes_old_state_until_report_and_findings_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    complete: bool,
    expected_exit: int,
) -> None:
    factory = _factory(tmp_path)
    repository_root = tmp_path / "repository"
    _seed_running_attempt(factory, repository_root)
    report = _report(complete=complete)
    observed_before_completion: list[str] = []

    def observe_after_ingestion_flush(session: Session, _flush_context: Any) -> None:
        scan = session.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 1
        assert scan.report_json == report.model_dump(mode="json")
        assert scan.result_fingerprint == report.result_fingerprint
        assert scan.complete is report.complete
        staged_findings = session.scalars(
            select(FindingRow).where(FindingRow.scan_id == "scan").order_by(FindingRow.id)
        ).all()
        assert [row.fingerprint for row in staged_findings] == [
            "new-finding-fingerprint-1",
            "new-finding-fingerprint-2",
        ]
        _assert_previous_attempt(factory, status=ScanStatus.RUNNING, attempts=1)
        observed_before_completion.append("old committed state observed")

    _patch_runner(monkeypatch, factory, report, after_flush=observe_after_ingestion_flush)

    assert (
        runner_module.execute_scan("scan", f"sqlite:///{tmp_path / 'runner-transactions.sqlite'}", 1) == expected_exit
    )

    assert observed_before_completion == ["old committed state observed"]
    _assert_new_report_committed(factory, report)


def test_runner_exception_after_finding_delete_rolls_back_through_session_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _factory(tmp_path)
    _seed_running_attempt(factory, tmp_path / "repository")
    report = _report()
    _patch_runner(monkeypatch, factory, report)
    engine = factory.kw["bind"]
    assert isinstance(engine, Engine)
    deletes: list[str] = []

    def fail_after_delete(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("DELETE FROM FINDINGS"):
            deletes.append(statement)
            raise _InjectedFailure("injected after old finding DELETE")

    event.listen(engine, "after_cursor_execute", fail_after_delete)
    try:
        with pytest.raises(_InjectedFailure, match="after old finding DELETE"):
            runner_module.execute_scan("scan", f"sqlite:///{tmp_path / 'runner-transactions.sqlite'}", 1)
    finally:
        event.remove(engine, "after_cursor_execute", fail_after_delete)

    assert len(deletes) == 1
    _assert_previous_attempt(factory, status=ScanStatus.RUNNING, attempts=1)


def test_runner_exception_after_new_findings_flush_rolls_back_staged_report_and_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _factory(tmp_path)
    _seed_running_attempt(factory, tmp_path / "repository")
    report = _report()
    flush_observations: list[str] = []

    def fail_after_ingestion_flush(session: Session, _flush_context: Any) -> None:
        scan = session.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 1
        assert scan.report_json == report.model_dump(mode="json")
        assert scan.result_fingerprint == report.result_fingerprint
        assert scan.complete is report.complete
        staged_findings = session.scalars(
            select(FindingRow).where(FindingRow.scan_id == "scan").order_by(FindingRow.id)
        ).all()
        assert [row.fingerprint for row in staged_findings] == [
            "new-finding-fingerprint-1",
            "new-finding-fingerprint-2",
        ]
        _assert_previous_attempt(factory, status=ScanStatus.RUNNING, attempts=1)
        flush_observations.append("report and normalized findings flushed")
        raise _InjectedFailure("injected after new finding inserts flushed")

    _patch_runner(monkeypatch, factory, report, after_flush=fail_after_ingestion_flush)

    with pytest.raises(_InjectedFailure, match="after new finding inserts flushed"):
        runner_module.execute_scan("scan", f"sqlite:///{tmp_path / 'runner-transactions.sqlite'}", 1)

    assert flush_observations == ["report and normalized findings flushed"]
    _assert_previous_attempt(factory, status=ScanStatus.RUNNING, attempts=1)


@pytest.mark.parametrize(
    ("winner", "expected_status", "expected_attempts"),
    [
        ("cancellation", ScanStatus.CANCELLED, 1),
        ("reclaimed-attempt", ScanStatus.RUNNING, 2),
    ],
    ids=["cancellation-wins", "claim-attempt-advanced"],
)
def test_runner_lost_completion_fence_rolls_back_ingestion_and_preserves_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    winner: str,
    expected_status: ScanStatus,
    expected_attempts: int,
) -> None:
    factory = _factory(tmp_path)
    _seed_running_attempt(factory, tmp_path / "repository")
    report = _report()
    _patch_runner(monkeypatch, factory, report)
    real_ingest = cast("Callable[[Session, ScanRow, ScanReport], None]", runner_module.__dict__["_ingest"])
    runner_write_phase = False
    fenced_updates: list[str] = []
    engine = factory.kw["bind"]
    assert isinstance(engine, Engine)

    def install_winner_before_runner_write(session: Session, scan: ScanRow, current_report: ScanReport) -> None:
        nonlocal runner_write_phase
        with factory() as winner_session:
            if winner == "cancellation":
                assert transition_scan_to_cancelled(winner_session, scan.id) is True
            else:
                reclaimed = winner_session.get(ScanRow, scan.id)
                assert reclaimed is not None
                assert reclaimed.status == ScanStatus.RUNNING.value
                reclaimed.attempts = 2
                winner_session.commit()
        runner_write_phase = True
        real_ingest(session, scan, current_report)

    def record_real_completion_update(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if runner_write_phase and statement.lstrip().upper().startswith("UPDATE SCANS SET STATUS"):
            fenced_updates.append(statement)

    monkeypatch.setattr(runner_module, "_ingest", install_winner_before_runner_write)
    event.listen(engine, "before_cursor_execute", record_real_completion_update)
    try:
        assert runner_module.execute_scan("scan", f"sqlite:///{tmp_path / 'runner-transactions.sqlite'}", 1) == 0
    finally:
        event.remove(engine, "before_cursor_execute", record_real_completion_update)

    assert len(fenced_updates) == 1
    sql = fenced_updates[0].upper()
    assert "WHERE SCANS.ID = ?" in sql
    assert "SCANS.STATUS = ?" in sql
    assert "SCANS.ATTEMPTS = ?" in sql
    _assert_previous_attempt(factory, status=expected_status, attempts=expected_attempts)
