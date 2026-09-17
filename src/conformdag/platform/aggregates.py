"""Read-only overview and repository trend aggregates over persisted platform rows.

These aggregates query persisted ``RepositoryRow``, ``ScanRow``, and
``FindingRow`` data only. They never invoke the scan engine, an evaluator,
policy pack loading, or the worker, and they share the baseline fingerprint
semantics of the findings endpoint.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import cast

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from conformdag.platform.contracts import (
    OverviewResponse,
    OverviewScan,
    RepositoryTrendsResponse,
    TrendPoint,
)
from conformdag.platform.db import FindingRow, RepositoryRow, ScanRow, eligible_baseline

COMPLETED_STATUS = "succeeded"
ACTIVE_STATUSES = ("queued", "running")
RECENT_SCAN_LIMIT = 10


@dataclass
class _TrendTotals:
    """Mutable per-date accumulator for trend point aggregation."""

    completed_scan_count: int = 0
    fail_finding_count: int = 0
    error_finding_count: int = 0
    suppressed_finding_count: int = 0
    new_finding_count: int = 0


def build_overview(session: Session, now: datetime, days: int) -> OverviewResponse:
    """Return overview aggregates across every registered repository."""
    _require_positive_days(days)
    repositories = session.scalars(select(RepositoryRow).order_by(RepositoryRow.name)).all()
    latest = _latest_completed_scan_by_repository(session)
    findings_by_scan: dict[str, list[FindingRow]] = defaultdict(list)
    if latest:
        scan_ids = [scan.id for scan in latest.values()]
        for row in session.scalars(select(FindingRow).where(FindingRow.scan_id.in_(scan_ids))).all():
            findings_by_scan[row.scan_id].append(row)
    current_failure = 0
    current_error = 0
    current_new = 0
    for repository in repositories:
        scan = latest.get(repository.id)
        if scan is None:
            continue
        rows = findings_by_scan.get(scan.id, [])
        current_failure += sum(1 for row in rows if row.status == "FAIL" and not row.suppressed)
        current_error += sum(1 for row in rows if row.status == "ERROR" and not row.suppressed)
        baseline_fingerprints = _baseline_fingerprints(session, repository.id, repository.baseline_scan_id)
        if baseline_fingerprints is not None:
            current_new += sum(1 for row in rows if row.fingerprint not in baseline_fingerprints)
    repository_names = {repository.id: repository.name for repository in repositories}
    return OverviewResponse(
        repository_count=len(repositories),
        completed_scan_count=_count_completed_scans(session),
        active_scan_count=_count_active_scans(session),
        current_failure_count=current_failure,
        current_error_count=current_error,
        current_new_finding_count=current_new,
        trends=_trend_points(session, None, now, days),
        recent_scans=_recent_scans(session, repository_names),
    )


def build_repository_trends(session: Session, repository_id: str, now: datetime, days: int) -> RepositoryTrendsResponse:
    """Return daily trend points for one repository."""
    _require_positive_days(days)
    return RepositoryTrendsResponse(
        repository_id=repository_id,
        points=_trend_points(session, {repository_id}, now, days),
    )


def _require_positive_days(days: int) -> None:
    """Reject non-positive day windows for direct aggregate callers."""
    if days < 1:
        raise ValueError(f"days must be positive, got {days}")


def _baseline_fingerprints(session: Session, repository_id: str, baseline_scan_id: str | None) -> set[str] | None:
    """Return the baseline fingerprint set, or None without a usable baseline.

    Mirrors the findings endpoint: the configured baseline scan must pass
    ``eligible_baseline`` for the same repository before its fingerprints may
    define which findings count as new.
    """
    if not baseline_scan_id:
        return None
    baseline = eligible_baseline(session, repository_id, baseline_scan_id)
    if baseline is None:
        return None
    return set(session.scalars(select(FindingRow.fingerprint).where(FindingRow.scan_id == baseline.id)).all())


def _latest_completed_scan_by_repository(session: Session) -> dict[str, ScanRow]:
    """Map each repository to its newest succeeded, complete scan."""
    scans = session.scalars(
        select(ScanRow)
        .where(ScanRow.status == COMPLETED_STATUS, ScanRow.complete.is_(True))
        .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
    ).all()
    latest: dict[str, ScanRow] = {}
    for scan in scans:
        latest.setdefault(scan.repository_id, scan)
    return latest


def _count_completed_scans(session: Session) -> int:
    """Count every succeeded, complete scan regardless of the trend window."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(ScanRow)
            .where(ScanRow.status == COMPLETED_STATUS, ScanRow.complete.is_(True))
        )
        or 0
    )


def _count_active_scans(session: Session) -> int:
    """Count queued and running scans."""
    return int(
        session.scalar(select(func.count()).select_from(ScanRow).where(ScanRow.status.in_(ACTIVE_STATUSES))) or 0
    )


def _trend_points(session: Session, repository_ids: set[str] | None, now: datetime, days: int) -> list[TrendPoint]:
    """Aggregate completed scans and their findings into UTC-day points.

    Only successful complete scans with ``finished_at`` inside the UTC window
    contribute, so dates without completed scans are omitted instead of being
    fabricated as zero points.
    """
    cutoff = now - timedelta(days=days)
    conditions: list[ColumnElement[bool]] = [
        ScanRow.status == COMPLETED_STATUS,
        ScanRow.complete.is_(True),
        ScanRow.finished_at.is_not(None),
        ScanRow.finished_at > cutoff,
        ScanRow.finished_at <= now,
    ]
    if repository_ids is not None:
        conditions.append(ScanRow.repository_id.in_(repository_ids))
    scans = session.scalars(select(ScanRow).where(*conditions).order_by(ScanRow.finished_at, ScanRow.id)).all()
    if not scans:
        return []
    scan_dates = {scan.id: _utc_date(cast("datetime", scan.finished_at)) for scan in scans}
    baselines: dict[str, set[str] | None] = {}
    totals: dict[date, _TrendTotals] = defaultdict(_TrendTotals)
    scan_repository: dict[str, str] = {scan.id: scan.repository_id for scan in scans}
    for row in session.scalars(select(FindingRow).where(FindingRow.scan_id.in_(list(scan_dates)))).all():
        point = totals[scan_dates[row.scan_id]]
        if row.suppressed:
            point.suppressed_finding_count += 1
        elif row.status == "FAIL":
            point.fail_finding_count += 1
        elif row.status == "ERROR":
            point.error_finding_count += 1
        repository_id = scan_repository[row.scan_id]
        if repository_id not in baselines:
            repository = session.get(RepositoryRow, repository_id)
            baseline_scan_id = repository.baseline_scan_id if repository is not None else None
            baselines[repository_id] = _baseline_fingerprints(session, repository_id, baseline_scan_id)
        baseline_fingerprints = baselines[repository_id]
        if baseline_fingerprints is not None and row.fingerprint not in baseline_fingerprints:
            point.new_finding_count += 1
    for scan in scans:
        totals[scan_dates[scan.id]].completed_scan_count += 1
    return [
        TrendPoint(
            date=point_date,
            completed_scan_count=totals.completed_scan_count,
            fail_finding_count=totals.fail_finding_count,
            error_finding_count=totals.error_finding_count,
            suppressed_finding_count=totals.suppressed_finding_count,
            new_finding_count=totals.new_finding_count,
        )
        for point_date, totals in sorted(totals.items())
    ]


def _recent_scans(session: Session, repository_names: dict[str, str]) -> list[OverviewScan]:
    """Return the newest scan summaries of any status, newest first."""
    rows = session.scalars(
        select(ScanRow).order_by(ScanRow.created_at.desc(), ScanRow.id.desc()).limit(RECENT_SCAN_LIMIT)
    ).all()
    return [
        OverviewScan(
            scan_id=row.id,
            repository_id=row.repository_id,
            repository_name=repository_names.get(row.repository_id, ""),
            status=row.status,
            created_at=row.created_at,
            finished_at=row.finished_at,
            complete=row.complete,
            gate_passed=_gate_passed(row),
        )
        for row in rows
    ]


def _gate_passed(scan: ScanRow) -> bool | None:
    """Read the persisted gate verdict from the report artifact, if any."""
    if scan.report_json is None:
        return None
    gate_result = cast("dict[str, object]", scan.report_json.get("gate_result") or {})
    return cast("bool | None", gate_result.get("passed"))


def _utc_date(value: datetime) -> date:
    """Return the UTC calendar date of a timestamp that may be naive."""
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(UTC).date()
