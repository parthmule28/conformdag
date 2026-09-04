"""Subprocess scan runner: executes one claimed scan and persists its report."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from conformdag.analysis import ParseCache
from conformdag.models import ScanReport
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    create_session_factory,
    utcnow,
)
from conformdag.reporting import normalize_report
from conformdag.scan import scan_repository

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
                fingerprint=finding.fingerprint,
                explanation=finding.explanation,
                remediation=finding.remediation,
                fix_json=finding.fix.model_dump(mode="json") if finding.fix else None,
                suppressed=finding.suppressed,
            )
        )


def execute_scan(scan_id: str, dsn: str) -> int:
    """Run one claimed scan inside this subprocess and persist the outcome."""
    factory = create_session_factory(dsn)
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None or scan.status != "running":
            print(f"scan {scan_id} is not claimable for execution", file=sys.stderr)
            return 2
        repository = session.get(RepositoryRow, scan.repository_id)
        if repository is None:
            scan.status = "failed"
            scan.error = "repository row disappeared"
            scan.finished_at = utcnow()
            session.commit()
            return 2
        pack = repository.policy_pack
        try:
            report = scan_repository(
                Path(repository.path), Path(pack) if pack else None, parse_cache=worker_parse_cache()
            )
        except PERSISTENT_FAILURES as exc:
            scan.status = "failed"
            scan.error = str(exc)
            scan.finished_at = utcnow()
            session.commit()
            return 1
        session.expire_all()
        refreshed = session.get(ScanRow, scan_id)
        if refreshed is not None and refreshed.status == "cancelled":
            print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
            return 0
        _ingest(session, scan, normalize_report(report))
        scan.status = "succeeded"
        scan.finished_at = utcnow()
        session.commit()
        return 0


def main() -> None:
    """Entry point for the subprocess scan runner."""
    parser = argparse.ArgumentParser(description="Execute one platform scan.")
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    raise SystemExit(execute_scan(args.scan_id, args.dsn))


if __name__ == "__main__":
    main()
