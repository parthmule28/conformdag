"""Platform scan artifact retention persistence operations."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conformdag.platform.persistence.models import ScanRow


def count_scans(session: Session, repository_id: str) -> int:
    """Return the number of scans recorded for one repository."""
    return int(
        session.scalar(select(func.count()).select_from(ScanRow).where(ScanRow.repository_id == repository_id)) or 0
    )


def retention_target_scan_ids(session: Session, repository_id: str, keep: int) -> list[str]:
    """Return scan ids beyond the newest ``keep`` for one repository.

    At least the single newest artifact is always protected, so a misconfigured
    ``keep`` below one can never prune the latest report.
    """
    newest = (
        select(ScanRow.id)
        .where(ScanRow.repository_id == repository_id)
        .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
        .limit(max(keep, 1))
        .subquery()
    )
    older = (
        select(ScanRow.id)
        .where(
            ScanRow.repository_id == repository_id,
            ScanRow.id.not_in(select(newest)),
        )
        .order_by(ScanRow.created_at.asc(), ScanRow.id.asc())
    )
    return list(session.scalars(older))


def prune_scan_artifact(session: Session, scan_id: str) -> None:
    """Clear the report artifact of one scan, keeping the row and its findings.

    Retention bounds artifact storage while normalized findings survive for
    trends, per design decision: findings forever, artifacts bounded.
    """
    scan = session.get(ScanRow, scan_id)
    if scan is not None:
        scan.report_json = None
