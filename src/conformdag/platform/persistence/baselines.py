"""Platform baseline eligibility persistence operations."""

from __future__ import annotations

from sqlalchemy.orm import Session

from conformdag.platform.domain import ScanStatus
from conformdag.platform.persistence.models import ScanRow


def eligible_baseline(session: Session, repository_id: str, scan_id: str) -> ScanRow | None:
    """Return the scan row when it may serve as one repository's baseline.

    A baseline must belong to the same repository and be a succeeded, complete
    scan; queued, running, failed, cancelled, and incomplete scans are never
    eligible.
    """
    scan = session.get(ScanRow, scan_id)
    if scan is None or scan.repository_id != repository_id:
        return None
    if ScanStatus(scan.status) is not ScanStatus.SUCCEEDED or scan.complete is not True:
        return None
    return scan
