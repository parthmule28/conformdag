"""Caller-owned transaction contract tests for platform mutation services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from conformdag.platform.app import PlatformSettings, create_app
from conformdag.platform.db import RepositoryRow, ScanRow, SuppressionRow, initialize_session_factory
from conformdag.platform.services.baselines import set_baseline
from conformdag.platform.services.repositories import (
    register_repository,
    register_workspace_repositories,
)
from conformdag.platform.services.scans import queue_scan
from conformdag.platform.services.suppressions import create_suppression, update_suppression
from conformdag.platform.workspace import WorkspaceRepository


class _InjectedFailure(RuntimeError):
    """Deterministic failure at the service/caller transaction boundary."""


class _CommitFailureFactory:
    """Attach a real SQLAlchemy commit event failure to route-created sessions."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self.commit_attempts = 0

    def __call__(self) -> Session:
        session = self._factory()
        event.listen(session, "before_commit", self._fail_before_commit)
        return session

    def _fail_before_commit(self, _session: Session) -> None:
        self.commit_attempts += 1
        raise _InjectedFailure("injected failure before database commit")


def _deny_service_commit() -> None:
    raise AssertionError("mutation service must not commit its caller's session")


def _httpx(client: TestClient) -> httpx.Client:
    """Narrow Starlette's untyped TestClient boundary for strict Pyright."""
    return cast("httpx.Client", client)


def test_service_mutations_stage_without_committing_and_rollback_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'platform.sqlite'}")
    expiration = datetime.now(UTC) + timedelta(days=1)
    with factory() as setup:
        setup.add_all(
            [
                RepositoryRow(id="repo", name="repo", path=str(tmp_path)),
                ScanRow(id="eligible", repository_id="repo", status="succeeded", complete=True),
                SuppressionRow(
                    id="existing-suppression",
                    policy_id="existing-policy",
                    fingerprint="existing-fingerprint",
                    reason="before",
                    owner="before-owner",
                    expires_at=expiration,
                    source="platform",
                ),
            ]
        )
        setup.commit()

    with factory() as session:
        monkeypatch.setattr(session, "commit", _deny_service_commit)
        with pytest.raises(_InjectedFailure, match="after all service mutations were flushed"):
            try:
                registered = register_repository(
                    session,
                    name="new-repository",
                    path=str(tmp_path),
                    policy_pack=None,
                    airflow_profile=None,
                )
                queued = queue_scan(session, "repo")
                assignment = set_baseline(session, "repo", "eligible")
                created = create_suppression(
                    session,
                    policy_id="new-policy",
                    fingerprint="new-fingerprint",
                    reason="temporary exception",
                    owner="platform",
                    expires_at=expiration,
                )
                updated = update_suppression(
                    session,
                    "existing-suppression",
                    reason="after",
                    owner="after-owner",
                    expires_at=None,
                )
                session.flush()

                assert session.get(RepositoryRow, registered.id) is not None
                queued_row = session.get(ScanRow, queued.scan_id)
                assert queued_row is not None and queued_row.status == "queued"
                assert assignment.baseline_scan_id == "eligible"
                assert session.get(RepositoryRow, "repo") is not None
                assert created.id != "existing-suppression"
                assert updated.reason == "after" and updated.owner == "after-owner"
                raise _InjectedFailure("after all service mutations were flushed")
            except _InjectedFailure:
                session.rollback()
                raise

    with factory() as reader:
        assert reader.scalar(select(RepositoryRow).where(RepositoryRow.name == "new-repository")) is None
        assert reader.scalar(select(ScanRow).where(ScanRow.repository_id == "repo", ScanRow.id != "eligible")) is None
        repository = reader.get(RepositoryRow, "repo")
        assert repository is not None and repository.baseline_scan_id is None
        assert reader.scalar(select(SuppressionRow).where(SuppressionRow.policy_id == "new-policy")) is None
        existing = reader.get(SuppressionRow, "existing-suppression")
        assert existing is not None
        assert (existing.reason, existing.owner) == ("before", "before-owner")


def test_workspace_batch_late_failure_after_first_flush_leaves_no_durable_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'platform.sqlite'}")
    repositories = [
        WorkspaceRepository(name="first", path=tmp_path / "first"),
        WorkspaceRepository(name="second", path=tmp_path / "second"),
    ]
    with factory() as session:
        monkeypatch.setattr(session, "commit", _deny_service_commit)
        real_add = session.add
        first_row_flushed: list[str] = []

        def add_with_late_failure(instance: object) -> None:
            real_add(instance)
            if isinstance(instance, RepositoryRow) and instance.name == "first":
                session.flush()
                first_row_flushed.append(instance.name)
            elif isinstance(instance, RepositoryRow) and instance.name == "second":
                raise _InjectedFailure("injected after first repository row was flushed")

        monkeypatch.setattr(session, "add", add_with_late_failure)
        with pytest.raises(_InjectedFailure, match="after first repository row was flushed"):
            try:
                register_workspace_repositories(session, repositories)
            except _InjectedFailure:
                session.rollback()
                raise

        assert first_row_flushed == ["first"]

    with factory() as reader:
        rows = reader.scalars(select(RepositoryRow).where(RepositoryRow.name.in_(["first", "second"]))).all()
        assert rows == []


def test_repository_route_commit_failure_is_discarded_when_session_context_closes(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'platform.sqlite'}"
    factory = initialize_session_factory(database_url)
    app = create_app(factory, PlatformSettings(dsn=database_url, admin_token="secret-token"))
    commit_failure_factory = _CommitFailureFactory(factory)
    app.state.session_factory = commit_failure_factory
    repository_path = tmp_path / "repository"
    repository_path.mkdir()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = _httpx(client).post(
            "/api/v1/repos",
            json={"name": "route-commit-failure", "path": str(repository_path), "policy_pack": None},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 500
    assert commit_failure_factory.commit_attempts == 1
    with factory() as reader:
        assert reader.scalar(select(RepositoryRow).where(RepositoryRow.name == "route-commit-failure")) is None
