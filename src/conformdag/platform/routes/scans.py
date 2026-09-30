"""Scan lifecycle, baseline, report, finding, and export HTTP routes."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response

import conformdag.platform.app as platform_app
from conformdag.platform.app import API_PREFIX, BaselineSetRequest, require_admin
from conformdag.platform.contracts import FindingResponse, ScanSummaryResponse
from conformdag.platform.services import ConflictError, NotFoundError
from conformdag.platform.services import baselines as baseline_service
from conformdag.platform.services import scans as scan_service
from conformdag.reporting import render_html, render_sarif

_factory = platform_app.session_factory_for


def trigger_scan(request: Request, repository_id: str) -> dict[str, str]:
    """Queue one scan for a registered repository."""
    with _factory(request)() as session:
        try:
            result = scan_service.queue_scan(session, repository_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result


def cancel_scan(request: Request, scan_id: str) -> dict[str, str]:
    """Cancel one queued or running scan."""
    with _factory(request)() as session:
        try:
            return scan_service.cancel_scan(session, scan_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def scan_status(request: Request, scan_id: str) -> dict[str, object]:
    """Return the current status of one scan."""
    with _factory(request)() as session:
        try:
            return scan_service.scan_status(session, scan_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def scan_history(
    request: Request,
    repository_id: str,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScanSummaryResponse]:
    """Return the scan history of one repository, newest first.

    Ordering is ``created_at`` descending with ``scan id`` descending as the
    tie-breaker, so entries sharing a timestamp keep a deterministic order.
    ``X-Total-Count`` carries the repository's unpaged scan count.
    """
    with _factory(request)() as session:
        page = scan_service.scan_history(session, repository_id, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(page.total)
    return page.items


def set_baseline(request: Request, repository_id: str, payload: BaselineSetRequest) -> dict[str, str]:
    """Mark one finished scan as the baseline for its repository."""
    with _factory(request)() as session:
        try:
            result = baseline_service.set_baseline(session, repository_id, payload.scan_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        session.commit()
        return result


def scan_report(request: Request, scan_id: str) -> dict[str, Any]:
    """Return the canonical report JSON artifact for one scan."""
    with _factory(request)() as session:
        try:
            return scan_service.load_report(session, scan_id).model_dump(mode="json")
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


def scan_findings(
    request: Request,
    scan_id: str,
    response: Response,
    status: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
    policy_id: Annotated[str | None, Query()] = None,
    file_path: Annotated[str | None, Query()] = None,
    suppressed: Annotated[bool | None, Query()] = None,
    baseline_status: Annotated[str | None, Query(pattern="^(existing|new)$")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FindingResponse]:
    """List normalized findings with server-side filters and pagination.

    ``baseline_status`` is ``"existing"`` or ``"new"`` when the repository
    has a same-repository successful baseline scan. It is ``None`` when no
    usable baseline is configured; that state is not treated as ``existing``,
    and both baseline-status filters return no rows in that case. Filters are
    applied before counting, so ``X-Total-Count`` always carries the unpaged
    number of matching findings, and ordering is deterministic.
    """
    filters = scan_service.FindingFilters(
        status=status,
        severity=severity,
        policy_id=policy_id,
        file_path=file_path,
        suppressed=suppressed,
        baseline_status=baseline_status,
    )
    with _factory(request)() as session:
        try:
            page = scan_service.scan_findings(session, scan_id, filters=filters, limit=limit, offset=offset)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    response.headers["X-Total-Count"] = str(page.total)
    return page.items


def export_scan(request: Request, scan_id: str, scan_format: str) -> Response:
    """Export one stored canonical report as json, sarif, or html."""
    with _factory(request)() as session:
        try:
            report = scan_service.load_report(session, scan_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if scan_format == "json":
        return Response(report.model_dump_json(indent=2) + "\n", media_type="application/json")
    if scan_format == "sarif":
        payload = json.dumps(render_sarif(report), indent=2, sort_keys=True) + "\n"
        return Response(payload, media_type="application/sarif+json")
    if scan_format == "html":
        return Response(render_html(report, include_evidence=True), media_type="text/html")
    raise HTTPException(status_code=404, detail="export format must be json, sarif, or html")


def register_routes(app: FastAPI) -> None:
    """Register scan-family routes in compatibility order."""
    app.post(API_PREFIX + "/repos/{repository_id}/scans", dependencies=[Depends(require_admin)])(trigger_scan)
    app.post(API_PREFIX + "/scans/{scan_id}/cancel", dependencies=[Depends(require_admin)])(cancel_scan)
    app.get(API_PREFIX + "/scans/{scan_id}")(scan_status)
    app.get(API_PREFIX + "/repos/{repository_id}/scans")(scan_history)
    app.put(API_PREFIX + "/repos/{repository_id}/baseline", dependencies=[Depends(require_admin)])(set_baseline)
    app.get(API_PREFIX + "/scans/{scan_id}/report")(scan_report)
    app.get(API_PREFIX + "/scans/{scan_id}/findings")(scan_findings)
    app.get(API_PREFIX + "/scans/{scan_id}/export/{scan_format}")(export_scan)
