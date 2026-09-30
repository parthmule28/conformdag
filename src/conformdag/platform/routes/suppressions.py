"""Operational suppression HTTP routes."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

import conformdag.platform.app as platform_app
from conformdag.platform.app import API_PREFIX, SuppressionCreate, SuppressionUpdate, require_admin
from conformdag.platform.services import ConflictError, NotFoundError
from conformdag.platform.services import suppressions as suppression_service

_factory = platform_app.session_factory_for


def list_suppressions(request: Request) -> list[dict[str, object]]:
    """List the operational suppression layer with audit fields."""
    with _factory(request)() as session:
        return suppression_service.list_suppressions(session)


def create_suppression(request: Request, payload: SuppressionCreate) -> dict[str, object]:
    """Create one operational suppression owned by the platform."""
    with _factory(request)() as session:
        try:
            result = suppression_service.create_suppression(
                session,
                policy_id=payload.policy_id,
                fingerprint=payload.fingerprint,
                reason=payload.reason,
                owner=payload.owner,
                expires_at=payload.expires_at,
            )
            session.commit()
        except ConflictError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return result


def update_suppression(request: Request, suppression_id: str, payload: SuppressionUpdate) -> dict[str, object]:
    """Update the editable audit fields of one platform suppression."""
    with _factory(request)() as session:
        try:
            result = suppression_service.update_suppression(
                session, suppression_id, reason=payload.reason, owner=payload.owner, expires_at=payload.expires_at
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result


def register_routes(app: FastAPI) -> None:
    """Register suppression endpoints in compatibility order."""
    app.get(API_PREFIX + "/suppressions")(list_suppressions)
    app.post(API_PREFIX + "/suppressions", dependencies=[Depends(require_admin)])(create_suppression)
    app.patch(API_PREFIX + "/suppressions/{suppression_id}", dependencies=[Depends(require_admin)])(update_suppression)
