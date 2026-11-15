"""Focused worker ownership and lifecycle-correlation contracts."""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from conformdag.application import execute_scan as application_execute_scan
from conformdag.baselines import Baseline
from conformdag.models import ScanReport, Suppression
from conformdag.platform import runner as runner_module
from conformdag.platform import worker as worker_module
from conformdag.platform.db import RepositoryRow, ScanRow, initialize_session_factory
from conformdag.platform.domain import ScanStatus
from conformdag.platform.logging import JsonFormatter
from conformdag.platform.worker import RunnerOutcome, WorkerSettings


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    """Create a real file-backed database through the production migration path."""
    return initialize_session_factory(f"sqlite:///{tmp_path / 'worker-lifecycle.sqlite'}")


def _seed_queued_scan(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="worker-lifecycle", path="."))
        session.add(
            ScanRow(
                id="scan",
                repository_id="repo",
                status=ScanStatus.QUEUED.value,
                attempts=0,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()


def _run_once_with_json_logs(
    factory: sessionmaker[Session], settings: WorkerSettings
) -> tuple[str | None, list[dict[str, object]]]:
    """Run once while capturing the worker's actual JSON-formatted log records."""
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter())
    worker_logger = logging.getLogger("conformdag.worker")
    namespace_logger = logging.getLogger("conformdag")
    previous_worker_level = worker_logger.level
    previous_namespace_propagate = namespace_logger.propagate
    worker_logger.addHandler(handler)
    worker_logger.setLevel(logging.INFO)
    try:
        handled = worker_module.run_worker_once(factory, "sqlite://", settings)
        log_text = output.getvalue()
    finally:
        worker_logger.removeHandler(handler)
        worker_logger.setLevel(previous_worker_level)
        namespace_logger.propagate = previous_namespace_propagate
        handler.close()

    payloads: list[dict[str, object]] = []
    for line in log_text.splitlines():
        payload = json.loads(line)
        if isinstance(payload, dict):
            payloads.append(cast("dict[str, object]", payload))
    return handled, payloads


def test_worker_runner_imports_keep_lifecycle_and_application_ownership_distinct() -> None:
    worker_imports = vars(worker_module)
    runner_imports = vars(runner_module)

    assert worker_module.RunnerOutcome is RunnerOutcome
    assert worker_module.run_worker_once.__module__ == worker_module.__name__
    assert worker_module.execute_claimed_scan.__module__ == worker_module.__name__
    assert {
        "Finding",
        "ScanReport",
        "classify_report",
        "execute_application_scan",
        "scan_repository",
    }.isdisjoint(worker_imports)

    assert runner_module.execute_scan.__module__ == runner_module.__name__
    assert runner_module.execute_application_scan is application_execute_scan
    assert runner_module.Baseline is Baseline
    assert runner_module.ScanReport is ScanReport
    assert runner_module.Suppression is Suppression
    assert {
        "subprocess",
        "Popen",
        "RunnerOutcome",
        "WorkerSettings",
        "execute_claimed_scan",
        "run_worker_once",
    }.isdisjoint(runner_imports)


def test_worker_lifecycle_json_logs_correlate_a_late_outcome_to_its_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _factory(tmp_path)
    _seed_queued_scan(factory)
    credential = "c27-worker-late-outcome-credential"

    def reclaim_before_late_outcome(
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
        return RunnerOutcome(error=f"password={credential}")

    # Keep the worker's existing child-invocation seam; no subprocess is launched.
    monkeypatch.setattr(worker_module, "execute_claimed_scan", reclaim_before_late_outcome)

    handled, payloads = _run_once_with_json_logs(factory, WorkerSettings())

    assert handled == "scan"
    lifecycle = [payload for payload in payloads if payload.get("logger") == "conformdag.worker"]
    assert [payload.get("message") for payload in lifecycle] == ["scan_claimed", "scan_finished"]
    assert [payload.get("scan_id") for payload in lifecycle] == ["scan", "scan"]

    finished_error = lifecycle[1].get("error")
    assert isinstance(finished_error, str)
    assert credential not in finished_error
    assert "[REDACTED]" in finished_error

    with factory() as reader:
        scan = reader.get(ScanRow, "scan")
        assert scan is not None
        assert scan.status == ScanStatus.RUNNING.value
        assert scan.attempts == 2
        assert scan.error is None

    attempts = [payload.get("attempt") for payload in lifecycle]
    assert all(type(attempt) is int for attempt in attempts), f"Expected integer claim attempts, got {attempts!r}"
    assert attempts == [1, 1]
