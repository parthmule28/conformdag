"""Subprocess scan runner: executes one claimed scan and persists its report."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from conformdag.analysis import ParseCache
from conformdag.application import (
    BaselineInput,
    ExecutionOutcome,
    ScanOptions,
    ScanOverrides,
    classify_report,
    coerce_platform_airflow_profile,
    resolve_effective_configuration,
)
from conformdag.application import execute_scan as execute_application_scan
from conformdag.models import ScanReport, Suppression
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    SuppressionRow,
    create_session_factory,
    eligible_baseline,
    transition_running_scan,
    utcnow,
)
from conformdag.platform.domain import ScanStatus
from conformdag.platform.logging import install_json_logging

PERSISTENT_FAILURES = (ValueError, OSError, RuntimeError)


def worker_parse_cache() -> ParseCache | None:
    """Resolve the worker-side parse cache directory, when enabled or defaulted."""
    configured = os.environ.get("CONFORMDAG_WORKER_PARSE_CACHE_DIR")
    if configured is None:
        return None
    return ParseCache(Path(configured))


def _ingest(session: Session, scan: ScanRow, report: ScanReport) -> None:
    """Persist the canonical report artifact and normalized finding rows.

    Re-claimed scans may carry partial findings from an abandoned attempt, so
    ingestion is idempotent: existing rows for the scan are removed first.
    """
    session.execute(delete(FindingRow).where(FindingRow.scan_id == scan.id))
    scan.report_json = report.model_dump(mode="json")
    scan.result_fingerprint = report.result_fingerprint
    scan.complete = report.complete
    for finding in report.findings:
        session.add(
            FindingRow(
                scan_id=scan.id,
                repository_id=scan.repository_id,
                policy_id=finding.policy_id,
                policy_version=finding.policy_version,
                status=finding.status.value,
                severity=finding.severity.value,
                file_path=finding.location.file.as_posix() if finding.location.file else None,
                start_line=finding.location.start_line,
                end_line=finding.location.end_line,
                fingerprint=finding.fingerprint,
                explanation=finding.explanation,
                remediation=finding.remediation,
                fix_json=finding.fix.model_dump(mode="json") if finding.fix else None,
                suppressed=finding.suppressed,
            )
        )


def _as_utc(value: datetime) -> datetime:
    """Interpret SQLite's naive UTC timestamps and normalize all DB times to UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _baseline_input(
    session: Session,
    repository_id: str,
    baseline_scan_id: str | None,
) -> BaselineInput | None:
    """Convert an eligible platform baseline into the application's canonical input."""
    if baseline_scan_id is None:
        return None
    baseline_scan = eligible_baseline(session, repository_id, baseline_scan_id)
    if baseline_scan is None:
        return None
    if baseline_scan.report_json is not None:
        return BaselineInput(report=ScanReport.model_validate(baseline_scan.report_json))
    fingerprints = frozenset(
        session.scalars(select(FindingRow.fingerprint).where(FindingRow.scan_id == baseline_scan.id)).all()
    )
    return BaselineInput(fingerprints=fingerprints)


def _operational_suppressions(session: Session) -> list[Suppression]:
    """Convert only active platform suppression rows into canonical application values."""
    active = session.scalars(select(SuppressionRow).where(SuppressionRow.expires_at > utcnow())).all()
    return [
        Suppression(
            fingerprint=row.fingerprint,
            policy_id=row.policy_id,
            reason=row.reason,
            owner=row.owner,
            created_at=_as_utc(row.created_at),
            expires_at=_as_utc(row.expires_at),
        )
        for row in active
    ]


def _incomplete_error(report: ScanReport) -> str:
    """Return a concise parse/discovery error for an incomplete report."""
    for issue in report.issues:
        if issue.fatal:
            return f"scan incomplete: {issue.code}: {issue.message}"
    return "scan incomplete: discovery did not finish"  # pragma: no cover - scan marks fatal issues


def _was_cancelled(session: Session, scan_id: str) -> bool:
    """Re-read the scan status with a fresh query so cancellation wins over any runner outcome."""
    status = session.scalar(select(ScanRow.status).where(ScanRow.id == scan_id))
    return status is not None and ScanStatus(status) is ScanStatus.CANCELLED


def execute_scan(scan_id: str, dsn: str, claim_attempt: int | None = None) -> int:
    """Run one claimed scan inside this subprocess and persist the outcome."""
    logger = logging.getLogger("conformdag.runner")
    factory = create_session_factory(dsn)
    install_json_logging()
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        if (
            scan is None
            or ScanStatus(scan.status) is not ScanStatus.RUNNING
            or (claim_attempt is not None and scan.attempts != claim_attempt)
        ):
            print(f"scan {scan_id} is not claimable for execution", file=sys.stderr)
            return 2
        repository = session.get(RepositoryRow, scan.repository_id)
        if repository is None:
            transition_running_scan(
                session,
                scan_id,
                ScanStatus.FAILED,
                "repository row disappeared",
                expected_attempt=claim_attempt,
            )
            return 2
        repository_root = Path(repository.path)
        try:
            logger.info("scan_started", extra={"scan_id": scan_id})
            airflow_profile = coerce_platform_airflow_profile(repository.airflow_profile)
            effective = resolve_effective_configuration(
                repository_root,
                platform_overrides=ScanOverrides(
                    policy_pack=Path(repository.policy_pack) if repository.policy_pack is not None else None,
                    airflow_profile=airflow_profile,
                ),
            )
            baseline = _baseline_input(session, scan.repository_id, repository.baseline_scan_id)
            operational_suppressions = _operational_suppressions(session)
            result = execute_application_scan(
                ScanOptions(repository_root),
                effective,
                baseline=baseline,
                operational_suppressions=operational_suppressions,
                parse_cache=worker_parse_cache(),
            )
        except PERSISTENT_FAILURES as exc:
            logger.info("scan_completed", extra={"scan_id": scan_id, "error": str(exc)})
            if not transition_running_scan(
                session, scan_id, ScanStatus.FAILED, str(exc), expected_attempt=claim_attempt
            ):
                print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
                return 0
            return 1
        logger.info("scan_completed", extra={"scan_id": scan_id})
        report = result.report
        if classify_report(report) is ExecutionOutcome.INCOMPLETE:
            if _was_cancelled(session, scan_id):
                print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
                return 0
            _ingest(session, scan, report)
            if not transition_running_scan(
                session,
                scan_id,
                ScanStatus.FAILED,
                _incomplete_error(report),
                expected_attempt=claim_attempt,
            ):
                print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
                return 0
            return 1
        if _was_cancelled(session, scan_id):
            print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
            return 0
        _ingest(session, scan, report)
        if not transition_running_scan(session, scan_id, ScanStatus.SUCCEEDED, expected_attempt=claim_attempt):
            print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
            return 0
        return 0


def main() -> None:
    """Entry point for the subprocess scan runner."""
    parser = argparse.ArgumentParser(description="Execute one platform scan.")
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--claim-attempt", type=int, required=True)
    parser.add_argument("--dsn")
    args = parser.parse_args()
    dsn = args.dsn or os.environ.get("CONFORMDAG_PLATFORM_DSN")
    if not dsn:
        parser.error("--dsn or CONFORMDAG_PLATFORM_DSN is required")
    raise SystemExit(execute_scan(args.scan_id, dsn, args.claim_attempt))


if __name__ == "__main__":
    main()
