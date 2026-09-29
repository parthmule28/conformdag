"""Repository baseline eligibility and assignment."""

from sqlalchemy.orm import Session

from conformdag.platform.db import ScanRow, eligible_baseline
from conformdag.platform.services import ConflictError, NotFoundError
from conformdag.platform.services.repositories import require_repository


def set_baseline(session: Session, repository_id: str, scan_id: str) -> dict[str, str]:
    """Assign an eligible same-repository scan without committing."""
    repository = require_repository(session, repository_id)
    scan = session.get(ScanRow, scan_id)
    if scan is None or scan.repository_id != repository_id:
        raise NotFoundError("scan not found for this repository")
    if eligible_baseline(session, repository_id, scan_id) is None:
        raise ConflictError("scan is not eligible as a baseline: it must be a succeeded, complete scan")
    repository.baseline_scan_id = scan_id
    return {"repository_id": repository_id, "baseline_scan_id": scan_id}
