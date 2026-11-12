"""Platform scan lifecycle persistence operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from conformdag.platform.domain import ScanStatus
from conformdag.platform.persistence.models import ScanRow, utcnow


def stale_running_cutoff(idle_seconds: int) -> datetime:
    """Return the cutoff before which a running scan is considered abandoned."""
    return datetime.now(UTC) - timedelta(seconds=idle_seconds)


def claim_queued_scan(session: Session, stale_cutoff: datetime, max_attempts: int) -> ScanRow | None:
    """Claim one queued scan, or re-claim an abandoned run within the attempt bound."""
    abandoned = (
        select(ScanRow)
        .where(
            ScanRow.status == ScanStatus.RUNNING.value,
            ScanRow.claimed_at.is_not(None),
            ScanRow.claimed_at < stale_cutoff,
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    abandoned_scan = session.scalars(abandoned).first()
    if abandoned_scan is not None:
        if abandoned_scan.attempts >= max_attempts:
            abandoned_scan.status = ScanStatus.FAILED.value
            abandoned_scan.error = "abandoned by a previous worker; attempt budget exhausted"
            abandoned_scan.finished_at = utcnow()
            return None
        abandoned_scan.attempts += 1
        abandoned_scan.claimed_at = utcnow()
        return abandoned_scan
    queued = (
        select(ScanRow)
        .where(ScanRow.status == ScanStatus.QUEUED.value)
        .order_by(ScanRow.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    queued_scan = session.scalars(queued).first()
    if queued_scan is None:
        return None
    queued_scan.status = ScanStatus.RUNNING.value
    queued_scan.claimed_at = utcnow()
    queued_scan.attempts += 1
    return queued_scan


def transition_running_scan(
    session: Session,
    scan_id: str,
    status: ScanStatus,
    error: str | None = None,
    *,
    requeue: bool = False,
    expected_attempt: int | None = None,
) -> bool:
    """Conditionally transition a running scan to ``status``.

    Returns True when the transition was applied. The conditional UPDATE makes
    cancellation win over any concurrent worker or runner outcome: a scan that
    was cancelled after the caller's last explicit status check is never
    overwritten, and the caller's pending changes are rolled back instead.
    Requeueing clears the claim timestamp so the scan re-enters the queue;
    terminal transitions stamp ``finished_at``.
    """
    valid_target = (status is ScanStatus.QUEUED and requeue) or (
        status in (ScanStatus.SUCCEEDED, ScanStatus.FAILED) and not requeue
    )
    if not valid_target:
        raise ValueError(f"invalid running scan transition target: {status!r} with requeue={requeue}")
    predicates = [ScanRow.id == scan_id, ScanRow.status == ScanStatus.RUNNING.value]
    if expected_attempt is not None:
        predicates.append(ScanRow.attempts == expected_attempt)
    statement = update(ScanRow).where(*predicates).values(status=status.value, error=error)
    statement = (
        statement.values(claimed_at=None) if requeue else statement.values(claimed_at=None, finished_at=utcnow())
    )
    applied = cast("CursorResult[Any]", session.execute(statement))
    if applied.rowcount:
        session.commit()
        return True
    session.rollback()
    return False


def transition_scan_to_cancelled(session: Session, scan_id: str) -> bool:
    """Atomically cancel a queued or running scan, allowing one winner."""
    statement = (
        update(ScanRow)
        .where(ScanRow.id == scan_id, ScanRow.status.in_((ScanStatus.QUEUED.value, ScanStatus.RUNNING.value)))
        .values(status=ScanStatus.CANCELLED.value, claimed_at=None, finished_at=utcnow())
    )
    applied = cast("CursorResult[Any]", session.execute(statement))
    if applied.rowcount:
        session.commit()
        return True
    session.rollback()
    return False


def heartbeat_running_scan(session: Session, scan_id: str, attempt: int) -> bool:
    """Refresh a running scan claim only while its status and attempt remain current."""
    predicates = [ScanRow.id == scan_id, ScanRow.status == ScanStatus.RUNNING.value, ScanRow.attempts == attempt]
    statement = update(ScanRow).where(*predicates).values(claimed_at=utcnow())
    applied = cast("CursorResult[Any]", session.execute(statement))
    if applied.rowcount:
        session.commit()
        return True
    session.rollback()
    return False
