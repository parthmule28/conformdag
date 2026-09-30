"""FastAPI application exposing the stable versioned platform HTTP API."""

from __future__ import annotations

import hmac
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse
from starlette.types import Scope

# C14 compatibility re-export: Canonical owner: platform.contracts.
# Removal/deprecation decision: C30.
from conformdag.platform.contracts import BaselineSetRequest as BaselineSetRequest
from conformdag.platform.contracts import PolicyUpsertRequest as PolicyUpsertRequest
from conformdag.platform.contracts import PolicyVocabularyRequest as PolicyVocabularyRequest
from conformdag.platform.contracts import RepositoryCreate as RepositoryCreate
from conformdag.platform.contracts import SuppressionCreate as SuppressionCreate
from conformdag.platform.contracts import SuppressionUpdate as SuppressionUpdate
from conformdag.platform.contracts import WorkspaceLoadRequest as WorkspaceLoadRequest
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
