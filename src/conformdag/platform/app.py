"""FastAPI application exposing the stable versioned platform HTTP API."""

from __future__ import annotations

import hmac
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse
from starlette.types import Scope

from conformdag.application import coerce_platform_airflow_profile
from conformdag.platform.contracts import (
    PolicyVocabularyRequest,
)
from conformdag.platform.logging import install_json_logging
from conformdag.platform.packs import PackService
from conformdag.platform.workspace import WorkspaceError, WorkspaceFile, load_workspace

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
                raise ValueError("wildcard CORS origins are not supported; configure explicit origins")
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

    @field_validator("airflow_profile")
    @classmethod
    def validate_airflow_profile(cls, value: str | None) -> str | None:
        coerce_platform_airflow_profile(value)
        return value


class WorkspaceLoadRequest(BaseModel):
    """Optional explicit path of the workspace file to register."""

    path: str | None = None


class PolicyUpsertRequest(PolicyVocabularyRequest):
    """Payload for creating or updating a policy in a pack.

    ``deterministic_checks`` and ``configuration`` are the canonical transport
    vocabulary. ``check_kind`` and ``check_config`` are retained as a beta
    compatibility view: ``check_kind`` means ``configuration.kind`` and never
    means a deterministic evaluator check.

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
    check_kind: str | None = Field(
        default=None,
        deprecated=True,
        description="Compatibility alias for configuration.kind; never a deterministic check kind.",
    )
    check_config: dict[str, Any] | None = Field(
        default=None,
        deprecated=True,
        description="Compatibility alias for the canonical configuration object.",
    )
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


def session_factory_for(request: Request) -> sessionmaker[Session]:
    """Return the configured session factory for a route handler."""
    return _factory(request)


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
        allow_credentials=False,
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

    # Registration order is part of the stable API contract; keep fallbacks last.
    app.get(API_PREFIX + "/health")(_health)
    from conformdag.platform.routes import overview as overview_routes
    from conformdag.platform.routes import packs as pack_routes
    from conformdag.platform.routes import repositories as repository_routes
    from conformdag.platform.routes import scans as scan_routes
    from conformdag.platform.routes import suppressions as suppression_routes

    repository_routes.register_routes(app)
    scan_routes.register_routes(app)
    suppression_routes.register_routes(app)
    overview_routes.register_routes(app)
    pack_routes.register_routes(app)

    app.api_route("/api", methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE"])(_api_fallback)
    app.api_route("/api/{rest:path}", methods=["GET", "HEAD", "POST", "PATCH", "PUT", "DELETE"])(_api_fallback)
    if STATIC_DIR.is_dir():
        app.mount("/", DashboardStaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
    return app


def _api_fallback(rest: str = "") -> dict[str, str]:
    """Return a JSON 404 for unknown API paths instead of the dashboard SPA."""
    raise HTTPException(status_code=404, detail=f"unknown API path: /api/{rest}")
