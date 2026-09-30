"""Repository and workspace HTTP routes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

import conformdag.platform.app as platform_app
from conformdag.platform.app import API_PREFIX, RepositoryCreate, WorkspaceLoadRequest, require_admin
from conformdag.platform.packs import PackService
from conformdag.platform.services import ConflictError, InvalidOperationError
from conformdag.platform.services import repositories as repository_service
from conformdag.platform.workspace import WorkspaceFile, load_workspace

_factory = cast("Callable[[Request], sessionmaker[Session]]", platform_app.__dict__["_factory"])
_register_workspace_packs = cast(
    "Callable[[PackService, WorkspaceFile], None]", platform_app.__dict__["_register_workspace_packs"]
)


def register_repository(request: Request, payload: RepositoryCreate) -> dict[str, str]:
    """Register one existing local DAG repository."""
    factory = _factory(request)
    with factory() as session:
        try:
            result = repository_service.register_repository(
                session,
                name=payload.name,
                path=payload.path,
                policy_pack=payload.policy_pack,
                airflow_profile=payload.airflow_profile,
            )
        except ConflictError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidOperationError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session.commit()
        return result


def load_workspace_file(request: Request, payload: WorkspaceLoadRequest) -> dict[str, int]:
    """Register every workspace repository that is not already present."""
    workspace, _ = load_workspace(Path(payload.path).resolve() if payload.path else None)
    _register_workspace_packs(request.app.state.pack_service, workspace)
    factory = _factory(request)
    with factory() as session:
        registered = repository_service.register_workspace_repositories(session, workspace.repositories)
        session.commit()
    return {"repositories_registered": registered}


def list_repositories(request: Request) -> list[dict[str, str | None]]:
    """List every registered DAG repository."""
    factory = _factory(request)
    with factory() as session:
        return repository_service.list_repositories(session)


def register_routes(app: FastAPI) -> None:
    """Register repository and workspace endpoints in compatibility order."""
    app.post(API_PREFIX + "/repos", dependencies=[Depends(require_admin)])(register_repository)
    app.post(API_PREFIX + "/workspace/load", dependencies=[Depends(require_admin)])(load_workspace_file)
    app.get(API_PREFIX + "/repos")(list_repositories)
