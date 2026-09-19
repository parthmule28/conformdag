"""FastAPI application exposing the stable versioned platform HTTP API."""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import ColumnElement, false, func, nullslast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse
from starlette.types import Scope

from conformdag.models import ScanReport
from conformdag.platform.aggregates import build_overview, build_repository_trends
from conformdag.platform.contracts import (
    FindingResponse,
    GateResponse,
    GateUpsertRequest,
    OverviewResponse,
    RepositoryTrendsResponse,
    ScanSummaryResponse,
)
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    SuppressionRow,
    count_scans,
    eligible_baseline,
    new_id,
    transition_scan_to_cancelled,
    utcnow,
)
from conformdag.platform.logging import install_json_logging
from conformdag.platform.packs import PackError, PackNotFoundError, PackService
from conformdag.platform.workspace import WorkspaceError, WorkspaceFile, load_workspace
from conformdag.policy import PolicyValidationError
from conformdag.reporting import render_html, render_sarif

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _is_spa_route(path: str) -> bool:
    """Return whether a missing static path is eligible for the SPA shell."""
    normalized = path.strip("/")
    if normalized == "" or normalized.startswith("assets/"):
        return normalized == ""
    return "." not in normalized.rsplit("/", maxsplit=1)[-1]


class DashboardStaticFiles(StaticFiles):
    """Serve the built dashboard while preserving missing-asset 404 responses."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not _is_spa_route(path):
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and _is_spa_route(path):
            return await super().get_response("index.html", scope)
        return response


class PlatformSettings(BaseModel):
    """Operator-supplied platform configuration resolved from the environment."""

    dsn: str
    admin_token: str | None = None
    retention_keep: int = Field(default=50, ge=1)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    workspace: Path | None = None

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if origin == "*":
                raise ValueError("wildcard CORS origins are unsafe when credentials are enabled")
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError(f"invalid CORS origin: {origin}")
        return origins


def load_settings() -> PlatformSettings:
    """Resolve platform settings from the environment."""
    dsn = os.environ.get("CONFORMDAG_PLATFORM_DSN")
    if not dsn:
        raise RuntimeError("platform requires CONFORMDAG_PLATFORM_DSN")
    token = os.environ.get("CONFORMDAG_PLATFORM_TOKEN")
    retention = int(os.environ.get("CONFORMDAG_PLATFORM_RETENTION_KEEP", "50"))
    cors_raw = os.environ.get("CONFORMDAG_PLATFORM_CORS_ORIGINS", "http://localhost:5173")
    origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]
    workspace_raw = os.environ.get("CONFORMDAG_WORKSPACE")
    workspace = Path(workspace_raw) if workspace_raw else None
    return PlatformSettings(
        dsn=dsn, admin_token=token, retention_keep=retention, cors_origins=origins, workspace=workspace
    )


class RepositoryCreate(BaseModel):
    """Registration payload for one local DAG repository."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    path: str
    policy_pack: str | None = None
    airflow_profile: str | None = Field(default=None, max_length=32)


class WorkspaceLoadRequest(BaseModel):
    """Optional explicit path of the workspace file to register."""

    path: str | None = None


class PolicyUpsertRequest(BaseModel):
    """Payload for creating or updating a policy in a pack.

    Editable fields are required. Contract metadata fields (``source_version``,
    ``ownership``, ``scope``, ``exceptions``, ``enforcement``, ``safe_path``)
    are optional: an existing policy keeps its persisted value when the request
    omits them, while a new policy must carry them completely. ``tags`` follows
    the preserve-on-omit rule; an explicit empty list clears the tags.
    """

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
    source_version: str | None = None
    ownership: dict[str, Any] | None = None
    scope: dict[str, Any] | None = None
    exceptions: dict[str, Any] | None = None
    enforcement: dict[str, Any] | None = None
    tags: list[str] | None = None


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
    presented = (authorization or "").encode("utf-8")
    expected = f"Bearer {settings.admin_token}".encode()
    if not hmac.compare_digest(presented, expected):
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
        if not transition_scan_to_cancelled(session, scan_id):
            current = session.get(ScanRow, scan_id)
            status = current.status if current is not None else "gone"
            raise HTTPException(status_code=409, detail=f"scan already {status}")
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
    factory = _factory(request)
    with factory() as session:
        response.headers["X-Total-Count"] = str(count_scans(session, repository_id))
        rows = session.scalars(
            select(ScanRow)
            .where(ScanRow.repository_id == repository_id)
            .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        summaries: list[ScanSummaryResponse] = []
        for row in rows:
            gate_result = cast("dict[str, object]", row.report_json.get("gate_result") or {}) if row.report_json else {}
            summaries.append(
                ScanSummaryResponse(
                    scan_id=row.id,
                    status=row.status,
                    created_at=row.created_at,
                    finished_at=row.finished_at,
                    result_fingerprint=row.result_fingerprint,
                    complete=row.complete,
                    gate_passed=cast("bool | None", gate_result.get("passed")),
                    artifact_available=row.report_json is not None,
                )
            )
        return summaries


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
        if eligible_baseline(session, repository_id, payload.scan_id) is None:
            raise HTTPException(
                status_code=409,
                detail="scan is not eligible as a baseline: it must be a succeeded, complete scan",
            )
        repository.baseline_scan_id = payload.scan_id
        session.commit()
        return {"repository_id": repository_id, "baseline_scan_id": payload.scan_id}


def scan_report(request: Request, scan_id: str) -> dict[str, Any]:
    """Return the canonical report JSON artifact for one scan."""
    return _load_report(_factory(request), scan_id).model_dump(mode="json")


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
    factory = _factory(request)
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="scan not found")
        repository = session.get(RepositoryRow, scan.repository_id)
        baseline_fingerprints: set[str] | None = None
        baseline = (
            eligible_baseline(session, scan.repository_id, repository.baseline_scan_id)
            if repository is not None and repository.baseline_scan_id
            else None
        )
        if baseline is not None:
            baseline_fingerprints = set(
                session.scalars(select(FindingRow.fingerprint).where(FindingRow.scan_id == baseline.id)).all()
            )
        filters: list[ColumnElement[bool]] = [FindingRow.scan_id == scan_id]
        if status:
            filters.append(FindingRow.status == status.upper())
        if severity:
            filters.append(FindingRow.severity == severity.lower())
        if policy_id:
            filters.append(FindingRow.policy_id == policy_id)
        if file_path:
            filters.append(FindingRow.file_path == file_path)
        if suppressed is not None:
            filters.append(FindingRow.suppressed == suppressed)
        if baseline_status is not None:
            if baseline_fingerprints is None:
                filters.append(false())
            elif baseline_status == "existing":
                filters.append(FindingRow.fingerprint.in_(baseline_fingerprints))
            else:
                filters.append(FindingRow.fingerprint.not_in(baseline_fingerprints))
        total = session.scalar(select(func.count()).select_from(FindingRow).where(*filters)) or 0
        response.headers["X-Total-Count"] = str(total)
        rows = session.scalars(
            select(FindingRow)
            .where(*filters)
            .order_by(
                FindingRow.policy_id,
                nullslast(FindingRow.file_path),
                nullslast(FindingRow.start_line),
                FindingRow.fingerprint,
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return [_finding_payload(row, baseline_fingerprints) for row in rows]


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
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail="suppression already exists for this policy finding") from exc
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


def overview(request: Request, days: Annotated[int, Query(ge=1, le=365)] = 30) -> OverviewResponse:
    """Return read-only overview aggregates across registered repositories."""
    factory = _factory(request)
    with factory() as session:
        return build_overview(session, utcnow(), days)


def repository_trends(
    request: Request, repository_id: str, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> RepositoryTrendsResponse:
    """Return read-only daily trend aggregates for one repository."""
    factory = _factory(request)
    with factory() as session:
        if session.get(RepositoryRow, repository_id) is None:
            raise HTTPException(status_code=404, detail="repository not registered")
        return build_repository_trends(session, repository_id, utcnow(), days)


def create_app(
    session_factory: sessionmaker[Session], settings: PlatformSettings, workspace_path: Path | None = None
) -> FastAPI:
    """Build the platform FastAPI application bound to one session factory.

    Startup workspace contract: when a workspace file is explicitly configured
    (the ``workspace_path`` argument or ``settings.workspace`` from the
    ``CONFORMDAG_WORKSPACE`` environment variable), it is loaded and registered
    at startup and any load or parse failure aborts startup visibly. Without
    explicit configuration the default ``./conformdag-workspace.yaml`` is
    loaded opportunistically: a missing or malformed file only skips pack
    registration, and ``POST /api/v1/workspace/load`` remains available.
    """
    install_json_logging()
    app = FastAPI(title="ConformDAG Platform", version="1")
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],
    )
    app.state.pack_service = PackService()
    configured_workspace = workspace_path if workspace_path is not None else settings.workspace
    if configured_workspace is not None:
        workspace, _ = load_workspace(configured_workspace)
        _register_workspace_packs(app.state.pack_service, workspace)
    else:
        try:
            workspace, _ = load_workspace()
        except WorkspaceError:
            pass
        else:
            _register_workspace_packs(app.state.pack_service, workspace)

    def request_error_handler(request: Request, exc: Exception) -> Response:
        """Add request observability to Starlette's normal unhandled-error response."""
        request_id = cast(str, request.state.request_id)
        start = cast(float, request.state.request_started)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response = PlainTextResponse("Internal Server Error", status_code=500)
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

    app.add_exception_handler(Exception, request_error_handler)

    async def request_logging_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        request.state.request_id = request_id
        request.state.request_started = start
        response = await call_next(request)
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
    app.get(API_PREFIX + "/overview")(overview)
    app.get(API_PREFIX + "/repos/{repository_id}/trends")(repository_trends)

    app.get(API_PREFIX + "/packs")(_pack_list)
    app.get(API_PREFIX + "/packs/{pack_name}/policies")(_pack_policies)
    app.put(API_PREFIX + "/packs/{pack_name}/policies/{policy_id}", dependencies=[Depends(require_admin)])(
        _pack_upsert_policy
    )
    app.delete(API_PREFIX + "/packs/{pack_name}/policies/{policy_id}", dependencies=[Depends(require_admin)])(
        _pack_delete_policy
    )
    app.post(API_PREFIX + "/packs/{pack_name}/validate", dependencies=[Depends(require_admin)])(_pack_validate)

    app.get(API_PREFIX + "/packs/{pack_name}/gates")(_pack_gates)
    app.put(API_PREFIX + "/packs/{pack_name}/gates/{gate_id}", dependencies=[Depends(require_admin)])(_pack_upsert_gate)
    app.delete(API_PREFIX + "/packs/{pack_name}/gates/{gate_id}", dependencies=[Depends(require_admin)])(
        _pack_delete_gate
    )

    app.api_route("/api", methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE"])(_api_fallback)
    app.api_route("/api/{rest:path}", methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE"])(_api_fallback)
    if STATIC_DIR.is_dir():
        app.mount("/", DashboardStaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
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
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _pack_upsert_policy(
    request: Request, pack_name: str, policy_id: str, payload: PolicyUpsertRequest
) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.upsert_policy(pack_name, policy_id, payload.model_dump(mode="json"))
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PackError, PolicyValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "saved", "policy_id": policy_id}


def _pack_delete_policy(request: Request, pack_name: str, policy_id: str) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.delete_policy(pack_name, policy_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "deleted", "policy_id": policy_id}


def _pack_validate(request: Request, pack_name: str) -> dict[str, Any]:
    service: PackService = request.app.state.pack_service
    try:
        return service.validate_pack(pack_name)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _pack_gates(request: Request, pack_name: str) -> list[GateResponse]:
    service: PackService = request.app.state.pack_service
    try:
        return [GateResponse.model_validate(gate) for gate in service.list_gates(pack_name)]
    except PackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _pack_upsert_gate(request: Request, pack_name: str, gate_id: str, payload: GateUpsertRequest) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.upsert_gate(pack_name, gate_id, payload.model_dump(mode="json"))
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "saved", "gate_id": gate_id}


def _pack_delete_gate(request: Request, pack_name: str, gate_id: str) -> dict[str, str]:
    service: PackService = request.app.state.pack_service
    try:
        service.delete_gate(pack_name, gate_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "deleted", "gate_id": gate_id}


def _api_fallback(rest: str = "") -> dict[str, str]:
    """Return a JSON 404 for unknown API paths instead of the dashboard SPA."""
    raise HTTPException(status_code=404, detail=f"unknown API path: /api/{rest}")


def _load_report(session_factory: sessionmaker[Session], scan_id: str) -> ScanReport:
    with session_factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None or scan.report_json is None:
            raise HTTPException(status_code=404, detail="scan report not available")
        return ScanReport.model_validate(scan.report_json)


def _finding_payload(row: FindingRow, baseline_fingerprints: set[str] | None = None) -> FindingResponse:
    baseline_status: str | None = None
    if baseline_fingerprints is not None:
        baseline_status = "existing" if row.fingerprint in baseline_fingerprints else "new"
    return FindingResponse(
        policy_id=row.policy_id,
        policy_version=row.policy_version,
        status=row.status,
        severity=row.severity,
        file_path=row.file_path,
        start_line=row.start_line,
        end_line=row.end_line,
        fingerprint=row.fingerprint,
        explanation=row.explanation,
        remediation=row.remediation,
        fix=row.fix_json,
        suppressed=row.suppressed,
        baseline_status=baseline_status,
    )


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
