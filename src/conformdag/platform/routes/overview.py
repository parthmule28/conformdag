"""Read-only overview and trend HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request

import conformdag.platform.app as platform_app
from conformdag.platform.app import API_PREFIX
from conformdag.platform.contracts import OverviewResponse, RepositoryTrendsResponse
from conformdag.platform.db import utcnow
from conformdag.platform.services import NotFoundError
from conformdag.platform.services import repositories as repository_service

_factory = platform_app.session_factory_for


def overview(request: Request, days: Annotated[int, Query(ge=1, le=365)] = 30) -> OverviewResponse:
    """Return read-only overview aggregates across registered repositories."""
    factory = _factory(request)
    with factory() as session:
        return repository_service.overview(session, now=utcnow(), days=days)


def repository_trends(
    request: Request, repository_id: str, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> RepositoryTrendsResponse:
    """Return read-only daily trend aggregates for one repository."""
    factory = _factory(request)
    with factory() as session:
        try:
            return repository_service.repository_trends(session, repository_id=repository_id, now=utcnow(), days=days)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def register_routes(app: FastAPI) -> None:
    """Register overview routes in compatibility order."""
    app.get(API_PREFIX + "/overview")(overview)
    app.get(API_PREFIX + "/repos/{repository_id}/trends")(repository_trends)
