"""Deterministic worker child-supervision characterization."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from conformdag.platform import worker as worker_module
from conformdag.platform.db import (
    RepositoryRow,
    ScanRow,
    initialize_session_factory,
    transition_scan_to_cancelled,
)
from conformdag.platform.domain import ScanStatus
from conformdag.platform.worker import RunnerOutcome, WorkerSettings


class _FakeClock:
    """Replace only worker-module monotonic calls with a deterministic sequence."""

    def __init__(self, ticks: tuple[float, ...]) -> None:
        self._ticks: Iterator[float] = iter(ticks)

    def monotonic(self) -> float:
        return next(self._ticks)


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    """Create a real file-backed database through the production migration path."""
    return initialize_session_factory(f"sqlite:///{tmp_path / 'worker-supervision.sqlite'}")


def _seed_scan(
    factory: sessionmaker[Session],
    *,
    status: ScanStatus,
    attempts: int,
    claimed_at: datetime | None = None,
) -> None:
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="worker-supervision", path="."))
        session.add(
            ScanRow(
                id="scan",
                repository_id="repo",
                status=status.value,
                attempts=attempts,
                claimed_at=claimed_at,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()


@pytest.mark.parametrize(
    ("returncode", "expected_error", "expected_retryable"),
    [
        (0, "", False),
        (1, "runner exited with code 1: password=[REDACTED]", False),
        (2, "runner exited with code 2: password=[REDACTED]", False),
        (-9, "runner exited with code -9: password=[REDACTED]", True),
    ],
    ids=["success", "ordinary-error", "other-error", "signal-retryable"],
)
def test_completed_child_exit_codes_keep_current_classification_and_redaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    returncode: int,
    expected_error: str,
    expected_retryable: bool,
) -> None:
    factory = _factory(tmp_path)
    _seed_scan(
        factory,
        status=ScanStatus.RUNNING,
        attempts=1,
        claimed_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    credential = "c27-worker-exit-code-credential"

    class CompletedProcess:
        def __init__(self) -> None:
            self.returncode = returncode
            self.communicate_timeouts: list[float | None] = []

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.communicate_timeouts.append(timeout)
            return "", f"password={credential}"

    process = CompletedProcess()

    def fake_popen(_arguments: list[str], **_kwargs: Any) -> CompletedProcess:
        return process

    monkeypatch.setattr(worker_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(worker_module, "time", _FakeClock((10.0, 10.0)))

    outcome = worker_module.execute_claimed_scan(
        factory,
        "sqlite://",
        "scan",
        WorkerSettings(poll_seconds=2.0, timeout_seconds=30),
        claim_attempt=1,
    )

    assert outcome.error == expected_error
    assert outcome.retryable is expected_retryable
    assert process.communicate_timeouts == [2.0]
    stderr = capsys.readouterr().err
    assert credential not in stderr
    assert "[REDACTED]" in stderr


def test_worker_bounds_poll_waits_refreshes_exact_attempt_and_drains_after_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = _factory(tmp_path)
    initial_claimed_at = datetime(2020, 1, 1, tzinfo=UTC)
    _seed_scan(factory, status=ScanStatus.RUNNING, attempts=1, claimed_at=initial_claimed_at)
    credential = "c27-worker-timeout-stderr-credential"
    heartbeat_sessions: list[Session] = []
    heartbeat_attempts: list[int] = []
    real_heartbeat = worker_module.heartbeat_running_scan

    def observe_heartbeat(session: Session, scan_id: str, attempt: int) -> bool:
        heartbeat_sessions.append(session)
        heartbeat_attempts.append(attempt)
        return real_heartbeat(session, scan_id, attempt)

    monkeypatch.setattr(worker_module, "heartbeat_running_scan", observe_heartbeat)

    class TimedOutProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.events: list[str] = []
            self.communicate_timeouts: list[float | None] = []

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.events.append(f"communicate({timeout})")
            self.communicate_timeouts.append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd="runner", timeout=timeout)
            return "", f"token={credential}"

        def poll(self) -> int | None:
            self.events.append("poll")
            return self.returncode

        def terminate(self) -> None:
            self.events.append("terminate")

        def wait(self, timeout: float | None = None) -> int:
            self.events.append(f"wait({timeout})")
            self.returncode = -15
            return self.returncode

    process = TimedOutProcess()

    def fake_popen(_arguments: list[str], **_kwargs: Any) -> TimedOutProcess:
        return process

    monkeypatch.setattr(worker_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(worker_module, "time", _FakeClock((10.0, 10.0, 12.0, 13.0)))

    outcome = worker_module.execute_claimed_scan(
        factory,
        "sqlite://",
        "scan",
        WorkerSettings(poll_seconds=2.0, timeout_seconds=3),
        claim_attempt=1,
    )

    assert outcome == RunnerOutcome(error="scan exceeded the 3s worker timeout", retryable=True)
    assert process.communicate_timeouts == [2.0, 1.0, None]
    assert process.events == [
        "communicate(2.0)",
        "communicate(1.0)",
        "poll",
        "terminate",
        "wait(5.0)",
        "wait(None)",
        "communicate(None)",
    ]
    assert heartbeat_attempts == [1, 1]
    assert len(heartbeat_sessions) == 2
    assert heartbeat_sessions[0] is not heartbeat_sessions[1]
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 1
        assert scan.claimed_at is not None
        refreshed_claim = scan.claimed_at.replace(tzinfo=UTC) if scan.claimed_at.tzinfo is None else scan.claimed_at
        assert refreshed_claim > initial_claimed_at
    stderr = capsys.readouterr().err
    assert credential not in stderr
    assert "[REDACTED]" in stderr


def test_worker_gracefully_terminates_and_drains_a_cancelled_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = _factory(tmp_path)
    _seed_scan(
        factory,
        status=ScanStatus.RUNNING,
        attempts=1,
        claimed_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    credential = "c27-worker-cancel-stderr-credential"

    class ResponsiveProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.events: list[str] = []

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.events.append(f"communicate({timeout})")
            if timeout is not None:
                with factory() as canceller:
                    assert transition_scan_to_cancelled(canceller, "scan")
                raise subprocess.TimeoutExpired(cmd="runner", timeout=timeout)
            return "", f"credential={credential}"

        def poll(self) -> int | None:
            self.events.append("poll")
            return self.returncode

        def terminate(self) -> None:
            self.events.append("terminate")

        def wait(self, timeout: float | None = None) -> int:
            self.events.append(f"wait({timeout})")
            self.returncode = -15
            return self.returncode

    process = ResponsiveProcess()

    def fake_popen(_arguments: list[str], **_kwargs: Any) -> ResponsiveProcess:
        return process

    monkeypatch.setattr(worker_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(worker_module, "time", _FakeClock((10.0, 10.0)))

    outcome = worker_module.execute_claimed_scan(
        factory,
        "sqlite://",
        "scan",
        WorkerSettings(poll_seconds=2.0, timeout_seconds=30),
        claim_attempt=1,
    )

    assert outcome == RunnerOutcome(cancelled=True)
    assert process.events == [
        "communicate(2.0)",
        "poll",
        "terminate",
        "wait(5.0)",
        "wait(None)",
        "communicate(None)",
    ]
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.CANCELLED.value
        assert scan.attempts == 1
    stderr = capsys.readouterr().err
    assert credential not in stderr
    assert "[REDACTED]" in stderr


def test_lost_heartbeat_kills_stubborn_child_and_preserves_reclaimed_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = _factory(tmp_path)
    _seed_scan(factory, status=ScanStatus.QUEUED, attempts=0)
    credential = "c27-worker-lost-heartbeat-stderr-credential"
    heartbeat_sessions: list[Session] = []
    heartbeat_attempts: list[int] = []
    heartbeat_results: list[bool] = []
    real_heartbeat = worker_module.heartbeat_running_scan

    def observe_heartbeat(session: Session, scan_id: str, attempt: int) -> bool:
        heartbeat_sessions.append(session)
        heartbeat_attempts.append(attempt)
        result = real_heartbeat(session, scan_id, attempt)
        heartbeat_results.append(result)
        return result

    monkeypatch.setattr(worker_module, "heartbeat_running_scan", observe_heartbeat)

    class StubbornProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.events: list[str] = []
            self.communicate_timeouts: list[float | None] = []

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.events.append(f"communicate({timeout})")
            self.communicate_timeouts.append(timeout)
            if timeout is not None:
                with factory() as newer_worker:
                    scan = newer_worker.get(ScanRow, "scan")
                    assert scan is not None
                    assert scan.status == ScanStatus.RUNNING.value
                    assert scan.attempts == 1
                    scan.claimed_at = datetime(2020, 1, 1, tzinfo=UTC)
                    newer_worker.flush()
                    reclaimed = worker_module.claim_queued_scan(
                        newer_worker,
                        datetime.now(UTC),
                        max_attempts=3,
                    )
                    assert reclaimed is not None
                    assert reclaimed.id == "scan"
                    assert reclaimed.attempts == 2
                    newer_worker.commit()
                raise subprocess.TimeoutExpired(cmd="runner", timeout=timeout)
            return "", f"token={credential}"

        def poll(self) -> int | None:
            self.events.append("poll")
            return self.returncode

        def terminate(self) -> None:
            self.events.append("terminate")

        def wait(self, timeout: float | None = None) -> int:
            self.events.append(f"wait({timeout})")
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd="runner", timeout=timeout)
            self.returncode = -9
            return self.returncode

        def kill(self) -> None:
            self.events.append("kill")

    process = StubbornProcess()

    def fake_popen(_arguments: list[str], **_kwargs: Any) -> StubbornProcess:
        return process

    monkeypatch.setattr(worker_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(worker_module, "time", _FakeClock((10.0, 10.0)))

    handled = worker_module.run_worker_once(
        factory,
        "sqlite://",
        WorkerSettings(poll_seconds=2.0, timeout_seconds=30, max_attempts=3),
    )

    assert handled == "scan"
    assert process.communicate_timeouts == [2.0, None]
    assert process.events == [
        "communicate(2.0)",
        "poll",
        "terminate",
        "wait(5.0)",
        "kill",
        "wait(None)",
        "communicate(None)",
    ]
    assert heartbeat_attempts == [1]
    assert heartbeat_results == [False]
    assert len(heartbeat_sessions) == 1
    stderr = capsys.readouterr().err
    assert credential not in stderr
    assert "[REDACTED]" in stderr
    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 2
        assert scan.error is None
