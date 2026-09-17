"""Subprocess scan runner: executes one claimed scan and persists its report."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from conformdag.analysis import ParseCache
from conformdag.config import load_project_config
from conformdag.gates import evaluate_pack_gates
from conformdag.models import GateResult, PolicyPack, ScanReport
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
from conformdag.platform.logging import install_json_logging
from conformdag.policy import resolve_configured_policy_pack, select_policy_pack
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


def _apply_platform_suppressions(session: Session, report: ScanReport) -> ScanReport:
    """Mark canonical findings matching an active platform suppression as suppressed."""
    active = session.scalars(select(SuppressionRow).where(SuppressionRow.expires_at > utcnow())).all()
    if not active:
        return report
    suppressed_identities = {(row.policy_id, row.fingerprint) for row in active}
    findings = [
        finding
        if finding.suppressed or (finding.policy_id, finding.fingerprint) not in suppressed_identities
        else finding.model_copy(update={"suppressed": True})
        for finding in report.findings
    ]
    return report.model_copy(update={"findings": findings})


def _incomplete_error(report: ScanReport) -> str:
    """Return a concise parse/discovery error for an incomplete report."""
    for issue in report.issues:
        if issue.fatal:
            return f"scan incomplete: {issue.code}: {issue.message}"
    return "scan incomplete: discovery did not finish"  # pragma: no cover - scan marks fatal issues


def _was_cancelled(session: Session, scan_id: str) -> bool:
    """Re-read the scan status with a fresh query so cancellation wins over any runner outcome."""
    return session.scalar(select(ScanRow.status).where(ScanRow.id == scan_id)) == "cancelled"


def execute_scan(scan_id: str, dsn: str) -> int:
    """Run one claimed scan inside this subprocess and persist the outcome."""
    logger = logging.getLogger("conformdag.runner")
    factory = create_session_factory(dsn)
    install_json_logging()
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None or scan.status != "running":
            print(f"scan {scan_id} is not claimable for execution", file=sys.stderr)
            return 2
        repository = session.get(RepositoryRow, scan.repository_id)
        if repository is None:
            transition_running_scan(session, scan_id, "failed", "repository row disappeared")
            return 2
        pack = repository.policy_pack
        try:
            logger.info("scan_started", extra={"scan_id": scan_id})
            report = scan_repository(
                Path(repository.path), Path(pack) if pack else None, parse_cache=worker_parse_cache()
            )
        except PERSISTENT_FAILURES as exc:
            logger.info("scan_completed", extra={"scan_id": scan_id, "error": str(exc)})
            if not transition_running_scan(session, scan_id, "failed", str(exc)):
                print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
                return 0
            return 1
        logger.info("scan_completed", extra={"scan_id": scan_id})
        report = _apply_platform_suppressions(session, report)
        normalized = normalize_report(report)
        if not normalized.complete:
            if _was_cancelled(session, scan_id):
                print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
                return 0
            _ingest(session, scan, normalized)
            if not transition_running_scan(session, scan_id, "failed", _incomplete_error(normalized)):
                print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
                return 0
            return 1
        gate_result: GateResult | None = None
        loaded_pack: PolicyPack | None = None
        try:
            repository_root = Path(repository.path)
            configured_pack = (
                Path(pack)
                if pack is not None
                else load_project_config(repository_root / "conformdag.yaml").scan.policy_pack
            )
            resolved_pack = resolve_configured_policy_pack(
                configured_pack,
                scan_root=repository_root,
                from_cli=pack is not None,
            )
            loaded_pack = select_policy_pack(resolved_pack, repository_root)
        except (ValueError, OSError):
            loaded_pack = None
        if loaded_pack is not None:
            baseline_report: ScanReport | None = None
            baseline_fingerprints: set[str] | None = None
            baseline_scan = (
                eligible_baseline(session, scan.repository_id, repository.baseline_scan_id)
                if repository.baseline_scan_id is not None
                else None
            )
            if baseline_scan is not None:
                if baseline_scan.report_json is not None:
                    baseline_report = ScanReport.model_validate(baseline_scan.report_json)
                else:
                    baseline_fingerprints = set(
                        session.scalars(
                            select(FindingRow.fingerprint).where(FindingRow.scan_id == baseline_scan.id)
                        ).all()
                    )
            gate_result = evaluate_pack_gates(
                loaded_pack,
                normalized,
                baseline_report,
                baseline_fingerprints=baseline_fingerprints,
            )
        if gate_result is not None:
            normalized = normalized.model_copy(update={"gate_result": gate_result})
        if _was_cancelled(session, scan_id):
            print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
            return 0
        _ingest(session, scan, normalized)
        if not transition_running_scan(session, scan_id, "succeeded"):
            print(f"scan {scan_id} was cancelled during execution", file=sys.stderr)
            return 0
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
