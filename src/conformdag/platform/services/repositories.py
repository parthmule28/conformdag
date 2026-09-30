"""Repository registration, lookup, and aggregate read coordination."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conformdag.application import coerce_platform_airflow_profile
from conformdag.platform.aggregates import (
    OverviewData,
    RepositoryTrendsData,
    build_overview,
    build_repository_trends,
)
from conformdag.platform.db import RepositoryRow, new_id
from conformdag.platform.services import ConflictError, InvalidOperationError, NotFoundError
from conformdag.platform.workspace import WorkspaceRepository

_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class RepositoryRegistration:
    """Detached identity of a repository registration."""

    id: str
    name: str


@dataclass(frozen=True)
class RepositoryRecord:
    """Detached repository data for internal service consumers."""

    id: str
    name: str
    path: str
    policy_pack: str | None
    airflow_profile: str | None
    baseline_scan_id: str | None


def _validate_name_profile(name: str, airflow_profile: str | None) -> None:
    if _NAME.fullmatch(name) is None:
        raise InvalidOperationError("invalid repository name")
    try:
        coerce_platform_airflow_profile(airflow_profile)
    except ValueError as exc:
        raise InvalidOperationError(str(exc)) from exc


def register_repository(
    session: Session, *, name: str, path: str, policy_pack: str | None, airflow_profile: str | None
) -> RepositoryRegistration:
    """Register a direct caller's repository with strict path-kind checks."""
    _validate_name_profile(name, airflow_profile)
    root = Path(path).resolve()
    if not root.is_dir():
        raise InvalidOperationError(f"repository path does not exist: {root}")
    pack = Path(policy_pack).resolve() if policy_pack else None
    if pack is not None and not pack.is_file():
        raise InvalidOperationError(f"policy pack path does not exist: {pack}")
    if session.scalar(select(RepositoryRow.id).where(RepositoryRow.name == name)) is not None:
        raise ConflictError("repository name already registered")
    row = RepositoryRow(
        id=new_id(), name=name, path=str(root), policy_pack=str(pack) if pack else None, airflow_profile=airflow_profile
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        if "repos.name" in str(exc.orig) or "repos_name_key" in str(exc.orig):
            raise ConflictError("repository name already registered") from exc
        raise
    return RepositoryRegistration(id=row.id, name=row.name)


def register_workspace_repositories(session: Session, repositories: Sequence[WorkspaceRepository]) -> int:
    """Persist workspace-validated entries without changing their path-kind contract."""
    existing = set(session.scalars(select(RepositoryRow.name)).all())
    registered = 0
    for repository in repositories:
        _validate_name_profile(repository.name, repository.airflow_profile)
        if repository.name in existing:
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
        existing.add(repository.name)
        registered += 1
    return registered


def list_repositories(session: Session) -> list[RepositoryRecord]:
    """Return repositories in name order with detached values."""
    rows = session.scalars(select(RepositoryRow).order_by(RepositoryRow.name)).all()
    return [
        RepositoryRecord(
            id=row.id,
            name=row.name,
            path=row.path,
            policy_pack=row.policy_pack,
            airflow_profile=row.airflow_profile,
            baseline_scan_id=row.baseline_scan_id,
        )
        for row in rows
    ]


def require_repository(session: Session, repository_id: str) -> RepositoryRow:
    """Require one registered repository."""
    row = session.get(RepositoryRow, repository_id)
    if row is None:
        raise NotFoundError("repository not registered")
    return row


def overview(session: Session, *, now: datetime, days: int) -> OverviewData:
    """Delegate existing overview aggregation without exposing it to HTTP routes."""
    return build_overview(session, now, days)


def repository_trends(session: Session, *, repository_id: str, now: datetime, days: int) -> RepositoryTrendsData:
    """Check repository existence before delegating existing trend aggregation."""
    require_repository(session, repository_id)
    return build_repository_trends(session, repository_id, now, days)
