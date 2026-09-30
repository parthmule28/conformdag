"""Read-only overview and trend HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request

import conformdag.platform.app as platform_app
from conformdag.platform.aggregates import OverviewData, OverviewScanData, RepositoryTrendsData, TrendPointData
from conformdag.platform.app import API_PREFIX
from conformdag.platform.contracts import (
    OverviewResponse,
    OverviewScan,
    RepositoryTrendsResponse,
    TrendPoint,
)
from conformdag.platform.db import utcnow
from conformdag.platform.services import NotFoundError
from conformdag.platform.services import repositories as repository_service

_factory = platform_app.session_factory_for


def _trend_point_response(point: TrendPointData) -> TrendPoint:
    return TrendPoint(
        date=point.date,
        completed_scan_count=point.completed_scan_count,
        fail_finding_count=point.fail_finding_count,
        error_finding_count=point.error_finding_count,
        suppressed_finding_count=point.suppressed_finding_count,
        new_finding_count=point.new_finding_count,
    )


def _overview_scan_response(scan: OverviewScanData) -> OverviewScan:
    return OverviewScan(
        scan_id=scan.scan_id,
        repository_id=scan.repository_id,
        repository_name=scan.repository_name,
        status=scan.status,
        created_at=scan.created_at,
        finished_at=scan.finished_at,
        complete=scan.complete,
        gate_passed=scan.gate_passed,
    )


def _overview_response(data: OverviewData) -> OverviewResponse:
    return OverviewResponse(
        repository_count=data.repository_count,
        completed_scan_count=data.completed_scan_count,
        active_scan_count=data.active_scan_count,
        current_failure_count=data.current_failure_count,
        current_error_count=data.current_error_count,
        current_new_finding_count=data.current_new_finding_count,
        trends=[_trend_point_response(point) for point in data.trends],
        recent_scans=[_overview_scan_response(scan) for scan in data.recent_scans],
    )


def _repository_trends_response(data: RepositoryTrendsData) -> RepositoryTrendsResponse:
    return RepositoryTrendsResponse(
        repository_id=data.repository_id,
        points=[_trend_point_response(point) for point in data.points],
    )


def overview(request: Request, days: Annotated[int, Query(ge=1, le=365)] = 30) -> OverviewResponse:
    """Return read-only overview aggregates across registered repositories."""
    factory = _factory(request)
    with factory() as session:
        data = repository_service.overview(session, now=utcnow(), days=days)
    return _overview_response(data)


def repository_trends(
    request: Request, repository_id: str, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> RepositoryTrendsResponse:
    """Return read-only daily trend aggregates for one repository."""
    factory = _factory(request)
    with factory() as session:
        try:
            data = repository_service.repository_trends(session, repository_id=repository_id, now=utcnow(), days=days)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _repository_trends_response(data)


def register_routes(app: FastAPI) -> None:
    """Register overview routes in compatibility order."""
    app.get(API_PREFIX + "/overview")(overview)
    app.get(API_PREFIX + "/repos/{repository_id}/trends")(repository_trends)
