"""Scan lifecycle commands and stored scan read queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy import ColumnElement, false, func, nullslast, select
from sqlalchemy.orm import Session

from conformdag.models import ScanReport
from conformdag.platform.contracts import FindingResponse, ScanSummaryResponse
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    count_scans,
    eligible_baseline,
    new_id,
    transition_scan_to_cancelled,
)
from conformdag.platform.domain import ScanStatus, ScanTrigger
from conformdag.platform.services import ConflictError, NotFoundError
from conformdag.platform.services.repositories import require_repository


@dataclass(frozen=True)
class Page[T]:
    """Detached page and its unpaged matching count."""

    items: list[T]
    total: int


@dataclass(frozen=True)
class FindingFilters:
    """Optional domain filters independent of HTTP query binding."""

    status: str | None = None
    severity: str | None = None
    policy_id: str | None = None
    file_path: str | None = None
    suppressed: bool | None = None
    baseline_status: str | None = None


def queue_scan(session: Session, repository_id: str) -> dict[str, str]:
    """Queue a dashboard-triggered scan for an existing repository."""
    require_repository(session, repository_id)
    scan = ScanRow(
        id=new_id(), repository_id=repository_id, status=ScanStatus.QUEUED.value, trigger=ScanTrigger.DASHBOARD.value
    )
    session.add(scan)
    return {"scan_id": scan.id, "status": ScanStatus.QUEUED.value}


def cancel_scan(session: Session, scan_id: str) -> dict[str, str]:
    """Cancel through the existing atomic, transaction-owning transition."""
    scan = session.get(ScanRow, scan_id)
    if scan is None:
        raise NotFoundError("scan not found")
    if not transition_scan_to_cancelled(session, scan_id):
        current = session.get(ScanRow, scan_id)
        status = ScanStatus(current.status).value if current is not None else "gone"
        raise ConflictError(f"scan already {status}")
    return {"scan_id": scan_id, "status": ScanStatus.CANCELLED.value}


def scan_status(session: Session, scan_id: str) -> dict[str, object]:
    """Read one scan's persisted status and gate summary."""
    scan = session.get(ScanRow, scan_id)
    if scan is None:
        raise NotFoundError("scan not found")
    return {
        "scan_id": scan.id,
        "repository_id": scan.repository_id,
        "status": ScanStatus(scan.status).value,
        "created_at": scan.created_at,
        "finished_at": scan.finished_at,
        "complete": scan.complete,
        "result_fingerprint": scan.result_fingerprint,
        "error": scan.error,
        "gate_passed": cast("dict[str, object]", scan.report_json.get("gate_result") or {}).get("passed")
        if scan.report_json
        else None,
    }


def scan_history(session: Session, repository_id: str, *, limit: int, offset: int) -> Page[ScanSummaryResponse]:
    """Read newest-first history, counting even scans beyond this page."""
    total = count_scans(session, repository_id)
    rows = session.scalars(
        select(ScanRow)
        .where(ScanRow.repository_id == repository_id)
        .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items: list[ScanSummaryResponse] = []
    for row in rows:
        gate = cast("dict[str, object]", row.report_json.get("gate_result") or {}) if row.report_json else {}
        items.append(
            ScanSummaryResponse(
                scan_id=row.id,
                status=ScanStatus(row.status),
                created_at=row.created_at,
                finished_at=row.finished_at,
                result_fingerprint=row.result_fingerprint,
                complete=row.complete,
                gate_passed=cast("bool | None", gate.get("passed")),
                artifact_available=row.report_json is not None,
            )
        )
    return Page(items, total)


def load_report(session: Session, scan_id: str) -> ScanReport:
    """Load the canonical stored artifact with the historical unavailable detail."""
    scan = session.get(ScanRow, scan_id)
    if scan is None or scan.report_json is None:
        raise NotFoundError("scan report not available")
    return ScanReport.model_validate(scan.report_json)


def _finding_payload(row: FindingRow, baseline_fingerprints: set[str] | None) -> FindingResponse:
    baseline_status = (
        None if baseline_fingerprints is None else ("existing" if row.fingerprint in baseline_fingerprints else "new")
    )
    return FindingResponse(
        policy_id=row.policy_id,
        policy_version=row.policy_version,
        status=row.status,
        severity=row.severity,
        file_path=row.file_path,
        start_line=row.start_line,
        end_line=row.end_line,
        fingerprint=row.fingerprint,
        explanation=row.explanation,
        remediation=row.remediation,
        fix=row.fix_json,
        suppressed=row.suppressed,
        baseline_status=baseline_status,
    )


def scan_findings(
    session: Session, scan_id: str, *, filters: FindingFilters, limit: int, offset: int
) -> Page[FindingResponse]:
    """Filter findings before counting, preserving baseline and deterministic ordering."""
    scan = session.get(ScanRow, scan_id)
    if scan is None:
        raise NotFoundError("scan not found")
    repository = session.get(RepositoryRow, scan.repository_id)
    baseline_fingerprints: set[str] | None = None
    baseline = (
        eligible_baseline(session, scan.repository_id, repository.baseline_scan_id)
        if repository is not None and repository.baseline_scan_id
        else None
    )
    if baseline is not None:
        baseline_fingerprints = set(
            session.scalars(select(FindingRow.fingerprint).where(FindingRow.scan_id == baseline.id)).all()
        )
    predicates: list[ColumnElement[bool]] = [FindingRow.scan_id == scan_id]
    if filters.status:
        predicates.append(FindingRow.status == filters.status.upper())
    if filters.severity:
        predicates.append(FindingRow.severity == filters.severity.lower())
    if filters.policy_id:
        predicates.append(FindingRow.policy_id == filters.policy_id)
    if filters.file_path:
        predicates.append(FindingRow.file_path == filters.file_path)
    if filters.suppressed is not None:
        predicates.append(FindingRow.suppressed == filters.suppressed)
    if filters.baseline_status is not None:
        if baseline_fingerprints is None:
            predicates.append(false())
        elif filters.baseline_status == "existing":
            predicates.append(FindingRow.fingerprint.in_(baseline_fingerprints))
        else:
            predicates.append(FindingRow.fingerprint.not_in(baseline_fingerprints))
    total = session.scalar(select(func.count()).select_from(FindingRow).where(*predicates)) or 0
    rows = session.scalars(
        select(FindingRow)
        .where(*predicates)
        .order_by(
            FindingRow.policy_id,
            nullslast(FindingRow.file_path),
            nullslast(FindingRow.start_line),
            FindingRow.fingerprint,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return Page([_finding_payload(row, baseline_fingerprints) for row in rows], total)
