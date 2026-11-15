"""Focused runner lifecycle validation, application-adapter, and log-correlation tests."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from conformdag.analysis import ParseCache
from conformdag.application import EffectiveScanConfiguration, ScanExecutionResult, ScanOptions, ScanOverrides
from conformdag.models import ProjectConfig, RunIssue, RunMetadata, ScanReport
from conformdag.platform import runner as runner_module
from conformdag.platform.db import RepositoryRow, ScanRow, initialize_session_factory
from conformdag.platform.domain import ScanStatus
from conformdag.platform.logging import JsonFormatter


def _seed_running_scan(tmp_path: Path, *, attempts: int = 4) -> tuple[sessionmaker[Session], str]:
    """Create one RUNNING scan in an initialized file-backed SQLite database."""
    database = tmp_path / "runner-lifecycle.sqlite"
    dsn = f"sqlite:///{database}"
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    factory = initialize_session_factory(dsn)
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="runner-lifecycle", path=str(repository_root)))
        session.add(
            ScanRow(
                id="scan",
                repository_id="repo",
                status=ScanStatus.RUNNING.value,
                attempts=attempts,
            )
        )
        session.commit()
    return factory, dsn


def _report(*, complete: bool = True) -> ScanReport:
    """Build a small canonical report for deterministic runner application results."""
    return ScanReport(
        complete=complete,
        result_fingerprint="runner-lifecycle-report",
        run=RunMetadata(
            tool_version="runner-lifecycle-test",
            policy_pack_id="runner-lifecycle-test",
            policy_pack_version="1.0.0",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        issues=(
            [
                RunIssue(
                    code="LIFECYCLE_INCOMPLETE",
                    message="controlled incomplete result",
                    phase="discovery",
                    fatal=True,
                )
            ]
            if not complete
            else []
        ),
    )


def _execution_result(report: ScanReport) -> ScanExecutionResult:
    """Wrap a canonical report in the application workflow's result type."""
    return ScanExecutionResult(report=report, gate_result=report.gate_result)


def _stub_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runner lifecycle tests independent of repository configuration files."""

    def resolve_configuration(
        repository_root: Path, *, platform_overrides: ScanOverrides
    ) -> EffectiveScanConfiguration:
        del platform_overrides
        project = ProjectConfig()
        return EffectiveScanConfiguration(
            project=project,
            resolved_policy_pack=repository_root / project.scan.policy_pack,
            runtime=project.runtime,
            semantic=project.semantic,
        )

    monkeypatch.setattr(runner_module, "resolve_effective_configuration", resolve_configuration)


def _json_payload(record: logging.LogRecord) -> dict[str, object]:
    """Format one captured runner record with the production JSON formatter."""
    payload = json.loads(JsonFormatter().format(record))
    assert isinstance(payload, dict)
    return cast("dict[str, object]", payload)


@pytest.mark.parametrize(
    ("claim_attempt", "expected_exit", "expected_application_calls"),
    [
        (3, 2, 0),
        (4, 0, 1),
        (None, 0, 1),
    ],
    ids=["stale-attempt-rejected", "matching-attempt-accepted", "legacy-none-accepted"],
)
def test_runner_validates_claim_attempt_without_rejecting_legacy_callers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    claim_attempt: int | None,
    expected_exit: int,
    expected_application_calls: int,
) -> None:
    factory, dsn = _seed_running_scan(tmp_path, attempts=4)
    _stub_configuration(monkeypatch)
    application_calls: list[str] = []

    def execute_application(
        _options: ScanOptions,
        _configuration: EffectiveScanConfiguration,
        **_kwargs: object,
    ) -> ScanExecutionResult:
        application_calls.append("called")
        return _execution_result(_report())

    monkeypatch.setattr(runner_module, "execute_application_scan", execute_application)

    assert runner_module.execute_scan("scan", dsn, claim_attempt=claim_attempt) == expected_exit
    assert len(application_calls) == expected_application_calls
    with factory() as session:
        scan = session.get(ScanRow, "scan")
        assert scan is not None
        assert scan.attempts == 4
        assert scan.status == (ScanStatus.RUNNING.value if claim_attempt == 3 else ScanStatus.SUCCEEDED.value)


def test_runner_forwards_parse_cache_once_to_canonical_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _factory, dsn = _seed_running_scan(tmp_path, attempts=4)
    _stub_configuration(monkeypatch)
    expected_cache = ParseCache(tmp_path / "parse-cache")
    cache_resolutions: list[ParseCache] = []
    application_calls: list[dict[str, object]] = []

    def resolve_parse_cache() -> ParseCache:
        cache_resolutions.append(expected_cache)
        return expected_cache

    def execute_application(
        _options: ScanOptions,
        _configuration: EffectiveScanConfiguration,
        **kwargs: object,
    ) -> ScanExecutionResult:
        application_calls.append(kwargs)
        return _execution_result(_report())

    monkeypatch.setattr(runner_module, "worker_parse_cache", resolve_parse_cache)
    monkeypatch.setattr(runner_module, "execute_application_scan", execute_application)

    assert runner_module.execute_scan("scan", dsn, claim_attempt=4) == 0
    assert cache_resolutions == [expected_cache]
    assert len(application_calls) == 1
    assert application_calls[0].get("parse_cache") is expected_cache


@pytest.mark.parametrize(
    ("outcome", "claim_attempt", "expected_exit"),
    [
        ("success", None, 0),
        ("incomplete", 4, 1),
        ("persistent-failure", 4, 1),
    ],
    ids=["successful-report", "incomplete-report", "handled-persistent-failure"],
)
def test_runner_json_lifecycle_events_include_validated_attempt_and_redact_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: str,
    claim_attempt: int | None,
    expected_exit: int,
) -> None:
    _factory, dsn = _seed_running_scan(tmp_path, attempts=4)
    _stub_configuration(monkeypatch)
    credential = "c27-runner-lifecycle-secret"

    def execute_application(
        _options: ScanOptions,
        _configuration: EffectiveScanConfiguration,
        **_kwargs: object,
    ) -> ScanExecutionResult:
        if outcome == "persistent-failure":
            raise RuntimeError(f"password={credential}")
        return _execution_result(_report(complete=outcome == "success"))

    monkeypatch.setattr(runner_module, "execute_application_scan", execute_application)
    runner_logger = logging.getLogger("conformdag.runner")
    previous_propagate = runner_logger.propagate
    runner_logger.propagate = False
    runner_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="conformdag.runner"):
            exit_code = runner_module.execute_scan("scan", dsn, claim_attempt=claim_attempt)
    finally:
        runner_logger.removeHandler(caplog.handler)
        runner_logger.propagate = previous_propagate

    assert exit_code == expected_exit
    records = [record for record in caplog.records if record.name == "conformdag.runner"]
    payloads = [_json_payload(record) for record in records]
    assert [payload["message"] for payload in payloads] == ["scan_started", "scan_completed"]
    assert all(payload["scan_id"] == "scan" for payload in payloads)
    assert all(type(payload["attempt"]) is int and payload["attempt"] == 4 for payload in payloads)
    serialized = json.dumps(payloads)
    assert credential not in serialized
    if outcome == "persistent-failure":
        assert "[REDACTED]" in serialized
