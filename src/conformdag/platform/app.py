"""FastAPI application exposing the stable versioned platform HTTP API."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from conformdag.models import ScanReport
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    SuppressionRow,
    new_id,
    utcnow,
)
from conformdag.platform.logging import install_json_logging
from conformdag.platform.packs import PackError, PackService
from conformdag.platform.workspace import WorkspaceError, WorkspaceFile, load_workspace
from conformdag.reporting import render_html, render_sarif

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).resolve().parent / "static"


class PlatformSettings(BaseModel):
    """Operator-supplied platform configuration resolved from the environment."""

    dsn: str
    admin_token: str | None = None
    retention_keep: int = 50


def load_settings() -> PlatformSettings:
    """Resolve platform settings from the environment."""
    dsn = os.environ.get("CONFORMDAG_PLATFORM_DSN")
    if not dsn:
        raise RuntimeError("platform requires CONFORMDAG_PLATFORM_DSN")
    token = os.environ.get("CONFORMDAG_PLATFORM_TOKEN")
    retention = int(os.environ.get("CONFORMDAG_PLATFORM_RETENTION_KEEP", "50"))
    return PlatformSettings(dsn=dsn, admin_token=token, retention_keep=retention)


class RepositoryCreate(BaseModel):
    """Registration payload for one local DAG repository."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    path: str
    policy_pack: str | None = None
    airflow_profile: str | None = None


class WorkspaceLoadRequest(BaseModel):
    """Optional explicit path of the workspace file to register."""

    path: str | None = None


class PolicyUpsertRequest(BaseModel):
    """Payload for creating or updating a policy in a pack."""

    title: str
    version: str
    status: str
    severity: str
    check_kind: str
    check_config: dict[str, Any]
    source_document: str
    source_section: str
    invariant: str
    safe_path: str | None = None


class SuppressionCreate(BaseModel):
    """Creation payload for an operational platform suppression."""

    policy_id: str
    fingerprint: str
    reason: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    expires_at: datetime


class SuppressionUpdate(BaseModel):
    """Editable fields for an existing platform suppression."""

    reason: str | None = None
    owner: str | None = None
    expires_at: datetime | None = None


class BaselineSetRequest(BaseModel):
    """Selection payload marking one scan as a repository's baseline."""

    scan_id: str


def require_admin(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    """Reject mutation requests unless the single-admin bearer token matches."""
    settings: PlatformSettings = request.app.state.settings
    if not settings.admin_token:
        raise HTTPException(
            status_code=503,
            detail="platform admin token is not configured; mutations are disabled",
        )
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(status_code=401, detail="admin authentication required")


def _factory(request: Request) -> sessionmaker[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    return factory


def _register_workspace_packs(service: PackService, workspace: WorkspaceFile) -> None:
    """Register every workspace pack (and per-repo pack) with the pack service."""
    for pack in workspace.policy_packs:
        service.register(pack.name, pack.path)
    for repository in workspace.repositories:
        if repository.policy_pack is not None:
            service.register(f"repo/{repository.name}", repository.policy_pack)


def _health() -> dict[str, str]:
    """Return the liveness payload."""
    return {"status": "ok"}


def register_repository(request: Request, payload: RepositoryCreate) -> dict[str, str]:
    """Register one existing local DAG repository."""
    root = _resolve_existing_directory(payload.path)
    pack = _resolve_existing_file(payload.policy_pack) if payload.policy_pack else None
    factory = _factory(request)
    with factory() as session:
        duplicate = session.scalars(select(RepositoryRow).where(RepositoryRow.name == payload.name)).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="repository name already registered")
        row = RepositoryRow(
            id=new_id(),
            name=payload.name,
            path=str(root),
            policy_pack=str(pack) if pack else None,
            airflow_profile=payload.airflow_profile,
        )
        session.add(row)
        session.commit()
        return {"id": row.id, "name": row.name}


def load_workspace_file(request: Request, payload: WorkspaceLoadRequest) -> dict[str, int]:
    """Register every workspace repository that is not already present."""
    workspace, _ = load_workspace(Path(payload.path).resolve() if payload.path else None)
    _register_workspace_packs(request.app.state.pack_service, workspace)
    factory = _factory(request)
    registered = 0
    with factory() as session:
        existing_names = {row.name for row in session.scalars(select(RepositoryRow)).all()}
        for repository in workspace.repositories:
            if repository.name in existing_names:
                continue
            session.add(
                RepositoryRow(
                    id=new_id(),
                    name=repository.name,
                    path=str(repository.path),
                    policy_pack=str(repository.policy_pack) if repository.policy_pack else None,
                    airflow_profile=repository.airflow_profile,
                )
            )
            registered += 1
        session.commit()
    return {"repositories_registered": registered}


def list_repositories(request: Request) -> list[dict[str, str | None]]:
    """List every registered DAG repository."""
    factory = _factory(request)
    with factory() as session:
        rows = session.scalars(select(RepositoryRow).order_by(RepositoryRow.name)).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "path": row.path,
                "policy_pack": row.policy_pack,
                "airflow_profile": row.airflow_profile,
                "baseline_scan_id": row.baseline_scan_id,
            }
            for row in rows
        ]


def trigger_scan(request: Request, repository_id: str) -> dict[str, str]:
    """Queue one scan for a registered repository."""
    factory = _factory(request)
    with factory() as session:
        repository = session.get(RepositoryRow, repository_id)
        if repository is None:
            raise HTTPException(status_code=404, detail="repository not registered")
        scan = ScanRow(id=new_id(), repository_id=repository_id, status="queued", trigger="dashboard")
        session.add(scan)
        session.commit()
        return {"scan_id": scan.id, "status": scan.status}


def cancel_scan(request: Request, scan_id: str) -> dict[str, str]:
    """Cancel one queued or running scan."""
    factory = _factory(request)
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="scan not found")
        if scan.status not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail=f"scan already {scan.status}")
        scan.status = "cancelled"
        scan.finished_at = utcnow()
        session.commit()
        return {"scan_id": scan_id, "status": "cancelled"}


def scan_status(request: Request, scan_id: str) -> dict[str, object]:
    """Return the current status of one scan."""
    factory = _factory(request)
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="scan not found")
        return {
            "scan_id": scan.id,
            "repository_id": scan.repository_id,
            "status": scan.status,
            "created_at": scan.created_at,
            "finished_at": scan.finished_at,
            "complete": scan.complete,
            "result_fingerprint": scan.result_fingerprint,
            "error": scan.error,
            "gate_passed": (
                cast("dict[str, object]", scan.report_json.get("gate_result") or {}).get("passed")
                if scan.report_json
                else None
            ),
        }


def scan_history(request: Request, repository_id: str) -> list[dict[str, object]]:
    """Return the scan history of one repository, newest first."""
    factory = _factory(request)
    with factory() as session:
        rows = session.scalars(
            select(ScanRow).where(ScanRow.repository_id == repository_id).order_by(ScanRow.created_at.desc())
        ).all()
        return [
            {
                "scan_id": row.id,
                "status": row.status,
                "created_at": row.created_at,
                "finished_at": row.finished_at,
                "result_fingerprint": row.result_fingerprint,
            }
            for row in rows
        ]


def set_baseline(request: Request, repository_id: str, payload: BaselineSetRequest) -> dict[str, str]:
    """Mark one finished scan as the baseline for its repository."""
    factory = _factory(request)
    with factory() as session:
        repository = session.get(RepositoryRow, repository_id)
        if repository is None:
            raise HTTPException(status_code=404, detail="repository not registered")
        scan = session.get(ScanRow, payload.scan_id)
        if scan is None or scan.repository_id != repository_id:
            raise HTTPException(status_code=404, detail="scan not found for this repository")
        repository.baseline_scan_id = payload.scan_id
        session.commit()
        return {"repository_id": repository_id, "baseline_scan_id": payload.scan_id}


def scan_report(request: Request, scan_id: str) -> dict[str, Any]:
    """Return the canonical report JSON artifact for one scan."""
    return _load_report(_factory(request), scan_id).model_dump(mode="json")


def scan_findings(request: Request, scan_id: str, status: str | None = None) -> list[dict[str, object]]:
    """List normalized findings for one scan, optionally filtered by status."""
    factory = _factory(request)
    with factory() as session:
        query = select(FindingRow).where(FindingRow.scan_id == scan_id)
        if status:
            query = query.where(FindingRow.status == status.upper())
        rows = session.scalars(query.order_by(FindingRow.policy_id, FindingRow.file_path)).all()
        return [_finding_payload(row) for row in rows]


def export_scan(request: Request, scan_id: str, scan_format: str) -> Response:
    """Export one stored canonical report as json, sarif, or html."""
    report = _load_report(_factory(request), scan_id)
    if scan_format == "json":
        return Response(report.model_dump_json(indent=2) + "\n", media_type="application/json")
    if scan_format == "sarif":
        payload = json.dumps(render_sarif(report), indent=2, sort_keys=True) + "\n"
        return Response(payload, media_type="application/sarif+json")
    if scan_format == "html":
        return Response(render_html(report, include_evidence=True), media_type="text/html")
    raise HTTPException(status_code=404, detail="export format must be json, sarif, or html")


def list_suppressions(request: Request) -> list[dict[str, object]]:
    """List the operational suppression layer with audit fields."""
    factory = _factory(request)
    with factory() as session:
        rows = session.scalars(select(SuppressionRow).order_by(SuppressionRow.created_at)).all()
        return [_suppression_payload(row) for row in rows]


def create_suppression(request: Request, payload: SuppressionCreate) -> dict[str, object]:
    """Create one operational suppression owned by the platform."""
    factory = _factory(request)
    with factory() as session:
        row = SuppressionRow(
            id=new_id(),
            policy_id=payload.policy_id,
            fingerprint=payload.fingerprint,
            reason=payload.reason,
            owner=payload.owner,
            expires_at=payload.expires_at,
            source="platform",
        )
        session.add(row)
        session.commit()
        return _suppression_payload(row)


def update_suppression(request: Request, suppression_id: str, payload: SuppressionUpdate) -> dict[str, object]:
    """Update the editable audit fields of one platform suppression."""
    factory = _factory(request)
    with factory() as session:
        row = session.get(SuppressionRow, suppression_id)
        if row is None:
            raise HTTPException(status_code=404, detail="suppression not found")
        if payload.reason is not None:
            row.reason = payload.reason
        if payload.owner is not None:
            row.owner = payload.owner
        if payload.expires_at is not None:
            row.expires_at = payload.expires_at
        session.commit()
        return _suppression_payload(row)


def create_app(session_factory: sessionmaker[Session], settings: PlatformSettings) -> FastAPI:
    """Build the platform FastAPI application bound to one session factory."""
    install_json_logging()
    app = FastAPI(title="ConformDAG Platform", version="1")
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.state.pack_service = PackService()
    try:
        workspace, _ = load_workspace()
    except WorkspaceError:
        pass
    else:
        _register_workspace_packs(app.state.pack_service, workspace)

    async def request_logging_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            response = Response(status_code=500)
            response.headers["X-Request-ID"] = request_id
            logging.getLogger("conformdag.platform.request").exception(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
            )
            return response
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("conformdag.platform.request").info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    app.middleware("http")(request_logging_middleware)

    app.get(API_PREFIX + "/health")(_health)
    app.post(API_PREFIX + "/repos", dependencies=[Depends(require_admin)])(register_repository)
    app.post(API_PREFIX + "/workspace/load", dependencies=[Depends(require_admin)])(load_workspace_file)
    app.get(API_PREFIX + "/repos")(list_repositories)
    app.post(API_PREFIX + "/repos/{repository_id}/scans", dependencies=[Depends(require_admin)])(trigger_scan)
    app.post(API_PREFIX + "/scans/{scan_id}/cancel", dependencies=[Depends(require_admin)])(cancel_scan)
    app.get(API_PREFIX + "/scans/{scan_id}")(scan_status)
    app.get(API_PREFIX + "/repos/{repository_id}/scans")(scan_history)
    app.put(API_PREFIX + "/repos/{repository_id}/baseline", dependencies=[Depends(require_admin)])(set_baseline)
    app.get(API_PREFIX + "/scans/{scan_id}/report")(scan_report)
    app.get(API_PREFIX + "/scans/{scan_id}/findings")(scan_findings)
    app.get(API_PREFIX + "/scans/{scan_id}/export/{scan_format}")(export_scan)
    app.get(API_PREFIX + "/suppressions")(list_suppressions)
    app.post(API_PREFIX + "/suppressions", dependencies=[Depends(require_admin)])(create_suppression)
    app.patch(API_PREFIX + "/suppressions/{suppression_id}", dependencies=[Depends(require_admin)])(update_suppression)

    app.get(API_PREFIX + "/packs")(_pack_list)
    app.get(API_PREFIX + "/packs/{pack_name}/policies")(_pack_policies)
    app.put(API_PREFIX + "/packs/{pack_name}/policies/{policy_id}", dependencies=[Depends(require_admin)])(
        _pack_upsert_policy
    )
    app.delete(API_PREFIX + "/packs/{pack_name}/policies/{policy_id}", dependencies=[Depends(require_admin)])(
        _pack_delete_policy
    )
    app.post(API_PREFIX + "/packs/{pack_name}/validate", dependencies=[Depends(require_admin)])(_pack_validate)

    app.api_route("/api/{rest:path}", methods=["GET", "POST", "PATCH", "DELETE"])(_api_fallback)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
    return app


def _pack_list(request: Request) -> list[dict[str, Any]]:
    service: PackService = request.app.state.pack_service
    return service.list_packs()


def _pack_policies(request: Request, pack_name: str) -> list[dict[str, Any]]:
    service: PackService = request.app.state.pack_service
    try:
        return service.list_policies(pack_name)
    except PackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _pack_upsert_policy(request: Request, pack_name: str, policy_id: str, payload: dict[str, Any]) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.upsert_policy(pack_name, policy_id, payload)
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "saved", "policy_id": policy_id}


def _pack_delete_policy(request: Request, pack_name: str, policy_id: str) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.delete_policy(pack_name, policy_id)
    except PackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "policy_id": policy_id}


def _pack_validate(request: Request, pack_name: str) -> dict[str, Any]:
    service: PackService = request.app.state.pack_service
    return service.validate_pack(pack_name)


def _api_fallback(rest: str) -> dict[str, str]:
    """Return a JSON 404 for unknown API paths instead of the dashboard SPA."""
    raise HTTPException(status_code=404, detail=f"unknown API path: /api/{rest}")


def _load_report(session_factory: sessionmaker[Session], scan_id: str) -> ScanReport:
    with session_factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None or scan.report_json is None:
            raise HTTPException(status_code=404, detail="scan report not available")
        return ScanReport.model_validate(scan.report_json)


def _finding_payload(row: FindingRow) -> dict[str, object]:
    return {
        "policy_id": row.policy_id,
        "policy_version": row.policy_version,
        "status": row.status,
        "severity": row.severity,
        "file_path": row.file_path,
        "start_line": row.start_line,
        "fingerprint": row.fingerprint,
        "explanation": row.explanation,
        "remediation": row.remediation,
        "fix": row.fix_json,
        "suppressed": row.suppressed,
    }


def _suppression_payload(row: SuppressionRow) -> dict[str, object]:
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


def _resolve_existing_directory(path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        raise HTTPException(status_code=422, detail=f"repository path does not exist: {resolved}")
    return resolved


def _resolve_existing_file(path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise HTTPException(status_code=422, detail=f"policy pack path does not exist: {resolved}")
    return resolved
