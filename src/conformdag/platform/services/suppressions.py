"""Operational suppression persistence and audit fields."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conformdag.platform.db import SuppressionRow, new_id
from conformdag.platform.services import ConflictError, NotFoundError


def _payload(row: SuppressionRow) -> dict[str, object]:
    return {
        "id": row.id,
        "policy_id": row.policy_id,
        "fingerprint": row.fingerprint,
        "reason": row.reason,
        "owner": row.owner,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "source": row.source,
    }


def list_suppressions(session: Session) -> list[dict[str, object]]:
    """Return suppression audit records in creation order."""
    rows = session.scalars(select(SuppressionRow).order_by(SuppressionRow.created_at)).all()
    return [_payload(row) for row in rows]


def create_suppression(
    session: Session, *, policy_id: str, fingerprint: str, reason: str, owner: str, expires_at: datetime
) -> dict[str, object]:
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
    return _payload(row)


def update_suppression(
    session: Session, suppression_id: str, *, reason: str | None, owner: str | None, expires_at: datetime | None
) -> dict[str, object]:
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
    return _payload(row)
