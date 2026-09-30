"""Scan lifecycle commands and stored scan read queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import ColumnElement, false, func, nullslast, select
from sqlalchemy.orm import Session

from conformdag.models import FindingStatus, RemediationPayload, ScanReport, Severity
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
from conformdag.platform.services import ConflictError, InvalidOperationError, NotFoundError
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


@dataclass(frozen=True)
class ScanTransition:
    """Detached result of a scan queue or cancellation transition."""

    scan_id: str
    status: ScanStatus


@dataclass(frozen=True)
class ScanStatusRecord:
    """Internal persisted scan status and completion summary."""

    scan_id: str
    repository_id: str
    status: ScanStatus
    created_at: datetime
    finished_at: datetime | None
    complete: bool | None
    result_fingerprint: str | None
    error: str | None
    gate_passed: bool | None


@dataclass(frozen=True)
class ScanSummaryRecord:
    """One internal scan history record with artifact availability."""

    scan_id: str
    status: ScanStatus
    created_at: datetime
    finished_at: datetime | None
    result_fingerprint: str | None
    complete: bool | None
    gate_passed: bool | None
    artifact_available: bool


@dataclass(frozen=True)
class FindingRecord:
    """One detached normalized finding for internal service consumers."""

    policy_id: str
    policy_version: str
    status: FindingStatus
    severity: Severity
    file_path: str | None
    start_line: int | None
    end_line: int | None
    fingerprint: str
    explanation: str | None
    remediation: str | None
    fix: RemediationPayload | None
    suppressed: bool
    baseline_status: Literal["existing", "new"] | None


def queue_scan(session: Session, repository_id: str) -> ScanTransition:
    """Queue a dashboard-triggered scan for an existing repository."""
    require_repository(session, repository_id)
    scan = ScanRow(
        id=new_id(), repository_id=repository_id, status=ScanStatus.QUEUED.value, trigger=ScanTrigger.DASHBOARD.value
    )
    session.add(scan)
    return ScanTransition(scan_id=scan.id, status=ScanStatus.QUEUED)


def cancel_scan(session: Session, scan_id: str) -> ScanTransition:
    """Cancel through the existing atomic, transaction-owning transition."""
    scan = session.get(ScanRow, scan_id)
    if scan is None:
        raise NotFoundError("scan not found")
    if not transition_scan_to_cancelled(session, scan_id):
        current = session.get(ScanRow, scan_id)
        status = ScanStatus(current.status).value if current is not None else "gone"
        raise ConflictError(f"scan already {status}")
    return ScanTransition(scan_id=scan_id, status=ScanStatus.CANCELLED)


def scan_status(session: Session, scan_id: str) -> ScanStatusRecord:
    """Read one scan's persisted status and gate summary."""
    scan = session.get(ScanRow, scan_id)
    if scan is None:
        raise NotFoundError("scan not found")
    gate = cast("dict[str, object]", scan.report_json.get("gate_result") or {}) if scan.report_json else {}
    return ScanStatusRecord(
        scan_id=scan.id,
        repository_id=scan.repository_id,
        status=ScanStatus(scan.status),
        created_at=scan.created_at,
        finished_at=scan.finished_at,
        complete=scan.complete,
        result_fingerprint=scan.result_fingerprint,
        error=scan.error,
        gate_passed=cast("bool | None", gate.get("passed")),
    )


def scan_history(session: Session, repository_id: str, *, limit: int, offset: int) -> Page[ScanSummaryRecord]:
    """Read newest-first history, counting even scans beyond this page."""
    total = count_scans(session, repository_id)
    rows = session.scalars(
        select(ScanRow)
        .where(ScanRow.repository_id == repository_id)
        .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items: list[ScanSummaryRecord] = []
    for row in rows:
        gate = cast("dict[str, object]", row.report_json.get("gate_result") or {}) if row.report_json else {}
        items.append(
            ScanSummaryRecord(
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


def _finding_payload(row: FindingRow, baseline_fingerprints: set[str] | None) -> FindingRecord:
    baseline_status: Literal["existing", "new"] | None = (
        None if baseline_fingerprints is None else ("existing" if row.fingerprint in baseline_fingerprints else "new")
    )
    fix = RemediationPayload.model_validate(row.fix_json) if row.fix_json is not None else None
    return FindingRecord(
        policy_id=row.policy_id,
        policy_version=row.policy_version,
        status=FindingStatus(row.status),
        severity=Severity(row.severity),
        file_path=row.file_path,
        start_line=row.start_line,
        end_line=row.end_line,
        fingerprint=row.fingerprint,
        explanation=row.explanation,
        remediation=row.remediation,
        fix=fix,
        suppressed=row.suppressed,
        baseline_status=baseline_status,
    )


def scan_findings(
    session: Session, scan_id: str, *, filters: FindingFilters, limit: int, offset: int
) -> Page[FindingRecord]:
    """Filter findings before counting, preserving baseline and deterministic ordering."""
    if filters.baseline_status is not None and filters.baseline_status not in {"existing", "new"}:
        raise InvalidOperationError("invalid baseline status")
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
