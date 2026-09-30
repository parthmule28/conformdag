"""Operational suppression HTTP routes."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

import conformdag.platform.app as platform_app
from conformdag.platform.app import API_PREFIX, require_admin
from conformdag.platform.contracts import SuppressionCreate, SuppressionResponse, SuppressionUpdate
from conformdag.platform.services import ConflictError, NotFoundError
from conformdag.platform.services import suppressions as suppression_service
from conformdag.platform.services.suppressions import SuppressionRecord

_factory = platform_app.session_factory_for


def _suppression_response(record: SuppressionRecord) -> SuppressionResponse:
    return SuppressionResponse(
        id=record.id,
        policy_id=record.policy_id,
        fingerprint=record.fingerprint,
        reason=record.reason,
        owner=record.owner,
        created_at=record.created_at,
        expires_at=record.expires_at,
        source=record.source,
    )


def list_suppressions(request: Request) -> list[SuppressionResponse]:
    """List the operational suppression layer with audit fields."""
    with _factory(request)() as session:
        records = suppression_service.list_suppressions(session)
    return [_suppression_response(record) for record in records]


def create_suppression(request: Request, payload: SuppressionCreate) -> SuppressionResponse:
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
        return _suppression_response(result)


def update_suppression(request: Request, suppression_id: str, payload: SuppressionUpdate) -> SuppressionResponse:
    """Update the editable audit fields of one platform suppression."""
    with _factory(request)() as session:
        try:
            result = suppression_service.update_suppression(
                session, suppression_id, reason=payload.reason, owner=payload.owner, expires_at=payload.expires_at
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return _suppression_response(result)


def register_routes(app: FastAPI) -> None:
    """Register suppression endpoints in compatibility order."""
    app.get(API_PREFIX + "/suppressions")(list_suppressions)
    app.post(API_PREFIX + "/suppressions", dependencies=[Depends(require_admin)])(create_suppression)
    app.patch(API_PREFIX + "/suppressions/{suppression_id}", dependencies=[Depends(require_admin)])(update_suppression)
