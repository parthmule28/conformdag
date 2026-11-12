"""Worker-level transaction boundary tests against migrated file-backed SQLite."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import select
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
from conformdag.platform import worker as worker_module
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    initialize_session_factory,
    retention_target_scan_ids,
    transition_running_scan,
)
from conformdag.platform.domain import ScanStatus
from conformdag.platform.worker import RunnerOutcome, WorkerSettings, run_worker_once

_runner_ingest = cast("Callable[[Session, ScanRow, ScanReport], None]", runner_module.__dict__["_ingest"])


class _InjectedFailure(RuntimeError):
    """A deterministic exception injected after a real retention flush."""


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    """Create a real file-backed database through the production Alembic startup path."""
    return initialize_session_factory(f"sqlite:///{tmp_path / 'worker-transactions.sqlite'}")


def _seed(factory: sessionmaker[Session], scans: Iterable[ScanRow]) -> None:
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="worker-transactions", path="."))
        session.add_all(scans)
        session.commit()


def _scan(
    scan_id: str,
    status: ScanStatus,
    *,
    created_at: datetime,
    attempts: int = 0,
    claimed_at: datetime | None = None,
    report_json: dict[str, object] | None = None,
    result_fingerprint: str | None = None,
    complete: bool | None = None,
    error: str | None = None,
) -> ScanRow:
    return ScanRow(
        id=scan_id,
        repository_id="repo",
        status=status.value,
        attempts=attempts,
        created_at=created_at,
        claimed_at=claimed_at,
        report_json=report_json,
        result_fingerprint=result_fingerprint,
        complete=complete,
        error=error,
    )


def _created(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def _worker_report() -> ScanReport:
    return ScanReport(
        complete=True,
        result_fingerprint="worker-result-fingerprint",
        run=RunMetadata(
            tool_version="worker-transaction-test",
            policy_pack_id="worker-transaction-test",
            policy_pack_version="1.0.0",
            timestamp=_created(5),
        ),
        findings=[
            Finding(
                policy_id="worker-policy",
                policy_version="1.0.0",
                status=FindingStatus.FAIL,
                severity=Severity.HIGH,
                enforcement=EnforcementType.DETERMINISTIC,
                location=FindingLocation(file=Path("dags/worker.py"), start_line=7),
                fingerprint="worker-finding-fingerprint",
            )
        ],
    )


def _assert_artifact_state(factory: sessionmaker[Session], *, worker_status: ScanStatus) -> None:
    """Assert independent readers see the full unpruned artifact set."""
    with factory() as reader:
        for scan_id in ("oldest", "middle", "kept"):
            row = reader.get(ScanRow, scan_id)
            assert row is not None
            assert row.report_json == {"artifact": scan_id}
            assert row.result_fingerprint == f"{scan_id}-result-fingerprint"
            assert row.complete is True
        worker_scan = reader.get(ScanRow, "worker")
        assert worker_scan is not None
        assert worker_scan.status == worker_status.value
        assert worker_scan.attempts == 1
        assert worker_scan.finished_at is not None
        assert worker_scan.error is None
        assert worker_scan.report_json == _worker_report().model_dump(mode="json")
        assert worker_scan.result_fingerprint == "worker-result-fingerprint"
        assert worker_scan.complete is True
        findings = reader.scalars(select(FindingRow).order_by(FindingRow.scan_id)).all()
        assert [(finding.scan_id, finding.fingerprint) for finding in findings] == [
            ("kept", "kept-finding-fingerprint"),
            ("middle", "middle-finding-fingerprint"),
            ("oldest", "oldest-finding-fingerprint"),
            ("worker", "worker-finding-fingerprint"),
        ]


def test_worker_commits_queued_claim_before_invoking_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _factory(tmp_path)
    _seed(factory, [_scan("scan", ScanStatus.QUEUED, created_at=_created(1))])
    child_observations: list[tuple[str, int]] = []

    def execute_child(
        session_factory: sessionmaker[Session],
        _dsn: str,
        scan_id: str,
        _settings: WorkerSettings,
        claim_attempt: int,
    ) -> RunnerOutcome:
        with session_factory() as reader:
            scan = reader.get(ScanRow, scan_id)
            assert scan is not None
            assert scan.status == ScanStatus.RUNNING.value
            assert scan.attempts == claim_attempt == 1
            assert scan.claimed_at is not None
        child_observations.append((scan_id, claim_attempt))

        # Model a real runner's fenced terminal write, which commits in its own session.
        with session_factory() as runner:
            assert transition_running_scan(runner, scan_id, ScanStatus.SUCCEEDED, expected_attempt=claim_attempt)
        return RunnerOutcome()

    monkeypatch.setattr(worker_module, "execute_claimed_scan", execute_child)

    assert run_worker_once(factory, "sqlite://", WorkerSettings()) == "scan"

    assert child_observations == [("scan", 1)]
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.SUCCEEDED.value
        assert scan.attempts == 1
        assert scan.finished_at is not None


def test_worker_commits_failed_when_stale_attempt_budget_is_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _factory(tmp_path)
    stale_claim = datetime.now(UTC) - timedelta(days=1)
    _seed(
        factory,
        [
            _scan(
                "stale",
                ScanStatus.RUNNING,
                created_at=_created(1),
                attempts=3,
                claimed_at=stale_claim,
            )
        ],
    )
    real_claim = worker_module.claim_queued_scan
    claim_was_exhausted: list[bool] = []

    def observe_claim(session: Session, stale_cutoff: datetime, max_attempts: int) -> ScanRow | None:
        claimed = real_claim(session, stale_cutoff, max_attempts)
        claim_was_exhausted.append(claimed is None)
        return claimed

    def child_must_not_run(
        _session_factory: sessionmaker[Session],
        _dsn: str,
        _scan_id: str,
        _settings: WorkerSettings,
        _claim_attempt: int,
    ) -> RunnerOutcome:
        raise AssertionError("worker must not invoke a child when no claim is returned")

    monkeypatch.setattr(worker_module, "claim_queued_scan", observe_claim)
    monkeypatch.setattr(worker_module, "execute_claimed_scan", child_must_not_run)

    assert run_worker_once(factory, "sqlite://", WorkerSettings(max_attempts=3)) is None

    assert claim_was_exhausted == [True]
    with factory() as reader:
        scan = reader.get(ScanRow, "stale")
        assert scan is not None
        assert scan.status == ScanStatus.FAILED.value
        assert scan.attempts == 3
        assert scan.finished_at is not None
        assert scan.error == "abandoned by a previous worker; attempt budget exhausted"


def test_abrupt_child_invocation_failure_leaves_committed_running_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _factory(tmp_path)
    _seed(factory, [_scan("scan", ScanStatus.QUEUED, created_at=_created(1))])
    invocation_observations: list[str] = []

    def fail_after_claim(
        session_factory: sessionmaker[Session],
        _dsn: str,
        scan_id: str,
        _settings: WorkerSettings,
        claim_attempt: int,
    ) -> RunnerOutcome:
        with session_factory() as reader:
            scan = reader.get(ScanRow, scan_id)
            assert scan is not None
            assert scan.status == ScanStatus.RUNNING.value
            assert scan.attempts == claim_attempt == 1
            assert scan.claimed_at is not None
        invocation_observations.append(scan_id)
        raise _InjectedFailure("injected abrupt child invocation failure")

    monkeypatch.setattr(worker_module, "execute_claimed_scan", fail_after_claim)

    with pytest.raises(_InjectedFailure, match="abrupt child invocation failure"):
        run_worker_once(factory, "sqlite://", WorkerSettings())

    assert invocation_observations == ["scan"]
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 1
        assert scan.claimed_at is not None
        assert scan.finished_at is None


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_error", "terminal"),
    [
        (
            RunnerOutcome(error="temporary child failure", retryable=True),
            ScanStatus.QUEUED,
            "temporary child failure",
            False,
        ),
        (RunnerOutcome(error="terminal child failure"), ScanStatus.FAILED, "terminal child failure", True),
    ],
    ids=["retry-commits-queued", "terminal-failure-commits-failed"],
)
def test_worker_commits_retry_and_terminal_transitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: RunnerOutcome,
    expected_status: ScanStatus,
    expected_error: str,
    terminal: bool,
) -> None:
    factory = _factory(tmp_path)
    _seed(factory, [_scan("scan", ScanStatus.QUEUED, created_at=_created(1))])

    def return_outcome(
        _session_factory: sessionmaker[Session],
        _dsn: str,
        _scan_id: str,
        _settings: WorkerSettings,
        _claim_attempt: int,
    ) -> RunnerOutcome:
        return outcome

    monkeypatch.setattr(worker_module, "execute_claimed_scan", return_outcome)

    assert run_worker_once(factory, "sqlite://", WorkerSettings()) == "scan"

    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == expected_status.value
        assert scan.attempts == 1
        assert scan.error == expected_error
        assert scan.claimed_at is None
        assert (scan.finished_at is not None) is terminal


def test_worker_fences_a_late_outcome_from_a_reclaimed_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _factory(tmp_path)
    _seed(factory, [_scan("scan", ScanStatus.QUEUED, created_at=_created(1))])

    def reclaim_then_return_stale_outcome(
        session_factory: sessionmaker[Session],
        _dsn: str,
        scan_id: str,
        _settings: WorkerSettings,
        claim_attempt: int,
    ) -> RunnerOutcome:
        assert claim_attempt == 1
        with session_factory() as newer_worker:
            scan = newer_worker.get(ScanRow, scan_id)
            assert scan is not None
            assert scan.status == ScanStatus.RUNNING.value
            scan.attempts = 2
            scan.claimed_at = datetime.now(UTC)
            newer_worker.commit()
        return RunnerOutcome(error="late terminal outcome")

    monkeypatch.setattr(worker_module, "execute_claimed_scan", reclaim_then_return_stale_outcome)

    assert run_worker_once(factory, "sqlite://", WorkerSettings()) == "scan"

    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 2
        assert scan.claimed_at is not None
        assert scan.finished_at is None
        assert scan.error is None


def test_retention_failure_rolls_back_all_pruning_after_lifecycle_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _factory(tmp_path)
    artifact_ids = ("oldest", "middle", "kept")
    scans = [
        _scan(
            scan_id,
            ScanStatus.SUCCEEDED,
            created_at=_created(day),
            report_json={"artifact": scan_id},
            result_fingerprint=f"{scan_id}-result-fingerprint",
            complete=True,
        )
        for day, scan_id in enumerate(artifact_ids, start=1)
    ]
    scans.append(_scan("worker", ScanStatus.QUEUED, created_at=_created(4)))
    _seed(factory, scans)
    with factory() as setup:
        setup.add_all(
            [
                FindingRow(
                    scan_id=scan_id,
                    repository_id="repo",
                    policy_id=f"policy-{scan_id}",
                    policy_version="1.0.0",
                    status="FAIL",
                    severity="high",
                    fingerprint=f"{scan_id}-finding-fingerprint",
                )
                for scan_id in artifact_ids
            ]
        )
        setup.commit()

    real_targets: Callable[[Session, str, int], list[str]] = worker_module.retention_target_scan_ids
    real_prune: Callable[[Session, str], None] = worker_module.prune_scan_artifact
    observed_targets: list[list[str]] = []
    pruned: list[str] = []

    def observe_targets(session: Session, repository_id: str, keep: int) -> list[str]:
        targets = real_targets(session, repository_id, keep)
        observed_targets.append(targets)
        return targets

    def flush_first_real_prune_then_fail(session: Session, scan_id: str) -> None:
        pruned.append(scan_id)
        real_prune(session, scan_id)
        if len(pruned) == 1:
            session.flush()
            staged = session.get(ScanRow, scan_id)
            assert staged is not None
            assert staged.report_json is None
            assert staged.result_fingerprint == f"{scan_id}-result-fingerprint"
            assert observed_targets == [["oldest", "middle"]]
            assert scan_id == "oldest"

            # The runner's fenced completion has committed, but this maintenance
            # transaction's flushed artifact clear remains invisible to another reader.
            _assert_artifact_state(factory, worker_status=ScanStatus.SUCCEEDED)
            raise _InjectedFailure("injected after first retention artifact flush")

    def successful_outcome(
        session_factory: sessionmaker[Session],
        _dsn: str,
        scan_id: str,
        _settings: WorkerSettings,
        claim_attempt: int,
    ) -> RunnerOutcome:
        with session_factory() as reader:
            scan = reader.get(ScanRow, scan_id)
            assert scan is not None
            assert scan.status == ScanStatus.RUNNING.value
            assert scan.attempts == claim_attempt == 1
        with session_factory() as runner:
            scan = runner.get(ScanRow, scan_id)
            assert scan is not None
            _runner_ingest(runner, scan, _worker_report())
            assert transition_running_scan(runner, scan_id, ScanStatus.SUCCEEDED, expected_attempt=claim_attempt)
        return RunnerOutcome()

    monkeypatch.setattr(worker_module, "retention_target_scan_ids", observe_targets)
    monkeypatch.setattr(worker_module, "prune_scan_artifact", flush_first_real_prune_then_fail)
    monkeypatch.setattr(worker_module, "execute_claimed_scan", successful_outcome)

    with pytest.raises(_InjectedFailure, match="first retention artifact flush"):
        run_worker_once(factory, "sqlite://", WorkerSettings(retention_keep=2))

    assert observed_targets == [["oldest", "middle"]]
    assert pruned == ["oldest"]
    _assert_artifact_state(factory, worker_status=ScanStatus.SUCCEEDED)


def test_newest_scan_row_is_protected_when_it_has_no_report(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    _seed(
        factory,
        [
            _scan(
                scan_id,
                ScanStatus.SUCCEEDED,
                created_at=_created(day),
                report_json={"artifact": scan_id} if scan_id == "oldest" else None,
            )
            for day, scan_id in enumerate(("oldest", "newest-without-report"), start=1)
        ],
    )

    with factory() as session:
        targets = retention_target_scan_ids(session, "repo", keep=1)

    assert targets == ["oldest"]
    with factory() as session:
        newest = session.get(ScanRow, "newest-without-report")
        assert newest is not None
        assert newest.report_json is None
