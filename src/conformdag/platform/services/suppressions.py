"""Operational suppression persistence and audit fields."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conformdag.platform.db import SuppressionRow, new_id
from conformdag.platform.services import ConflictError, NotFoundError


@dataclass(frozen=True)
class SuppressionRecord:
    """Detached suppression state with its platform audit fields."""

    id: str
    policy_id: str
    fingerprint: str
    reason: str
    owner: str
    created_at: datetime
    expires_at: datetime
    source: str


def _record(row: SuppressionRow) -> SuppressionRecord:
    return SuppressionRecord(
        id=row.id,
        policy_id=row.policy_id,
        fingerprint=row.fingerprint,
        reason=row.reason,
        owner=row.owner,
        created_at=row.created_at,
        expires_at=row.expires_at,
        source=row.source,
    )


def list_suppressions(session: Session) -> list[SuppressionRecord]:
    """Return suppression audit records in creation order."""
    rows = session.scalars(select(SuppressionRow).order_by(SuppressionRow.created_at)).all()
    return [_record(row) for row in rows]


def create_suppression(
    session: Session, *, policy_id: str, fingerprint: str, reason: str, owner: str, expires_at: datetime
) -> SuppressionRecord:
    """Create an operational suppression, surfacing identifiable unique conflicts."""
    row = SuppressionRow(
        id=new_id(),
        policy_id=policy_id,
        fingerprint=fingerprint,
        reason=reason,
        owner=owner,
        expires_at=expires_at,
        source="platform",
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        detail = str(exc.orig)
        if (
            "suppressions.policy_id, suppressions.fingerprint" in detail
            or "uq_suppressions_policy_fingerprint" in detail
        ):
            raise ConflictError("suppression already exists for this policy finding") from exc
        raise
    return _record(row)


def update_suppression(
    session: Session, suppression_id: str, *, reason: str | None, owner: str | None, expires_at: datetime | None
) -> SuppressionRecord:
    """Update only supplied non-null audit fields; the caller commits."""
    row = session.get(SuppressionRow, suppression_id)
    if row is None:
        raise NotFoundError("suppression not found")
    if reason is not None:
        row.reason = reason
    if owner is not None:
        row.owner = owner
    if expires_at is not None:
        row.expires_at = expires_at
    return _record(row)
