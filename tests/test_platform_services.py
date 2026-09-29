"""Real-session tests for transport-independent platform services."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from conformdag.platform.db import RepositoryRow, initialize_session_factory
from conformdag.platform.services import ConflictError, InvalidOperationError, NotFoundError
from conformdag.platform.services.repositories import (
    list_repositories,
    register_repository,
    register_workspace_repositories,
    repository_trends,
)
from conformdag.platform.workspace import WorkspaceRepository


def test_direct_repository_rejects_invalid_names_paths_and_profile(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    root = tmp_path / "repo"
    root.mkdir()
    pack = tmp_path / "pack.yaml"
    pack.write_text("pack", encoding="utf-8")
    with factory() as session:
        for name in ("Bad Name", ""):
            with pytest.raises(InvalidOperationError):
                register_repository(session, name=name, path=str(root), policy_pack=None, airflow_profile=None)
        with pytest.raises(InvalidOperationError, match="repository path does not exist"):
            register_repository(session, name="file", path=str(pack), policy_pack=None, airflow_profile=None)
        with pytest.raises(InvalidOperationError, match="policy pack path does not exist"):
            register_repository(session, name="pack", path=str(root), policy_pack=str(root), airflow_profile=None)
        with pytest.raises(InvalidOperationError):
            register_repository(
                session, name="bad-profile", path=str(root), policy_pack=None, airflow_profile="invalid"
            )
        assert list_repositories(session) == []


def test_repository_duplicate_flush_rollback_and_sorted_reads(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    root = tmp_path / "repo"
    root.mkdir()
    with factory() as session:
        register_repository(
            session, name="zeta", path=str(root / ".." / "repo"), policy_pack=None, airflow_profile=None
        )
        assert len(list_repositories(session)) == 1
        session.rollback()
    with factory() as session:
        assert list_repositories(session) == []
        register_repository(session, name="zeta", path=str(root), policy_pack=None, airflow_profile=None)
        session.commit()
        with pytest.raises(ConflictError, match="repository name already registered"):
            register_repository(session, name="zeta", path=str(root), policy_pack=None, airflow_profile=None)
        session.rollback()
        register_repository(session, name="alpha", path=str(root), policy_pack=None, airflow_profile=None)
        session.commit()
        assert [row["name"] for row in list_repositories(session)] == ["alpha", "zeta"]
        assert list_repositories(session)[0]["path"] == str(root.resolve())
        with pytest.raises(NotFoundError, match="repository not registered"):
            repository_trends(session, repository_id="missing", now=datetime.now(UTC), days=7)


def test_workspace_repository_persists_existing_paths_without_kind_checks(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    repo_file = tmp_path / "repo.py"
    repo_file.write_text("pass", encoding="utf-8")
    pack_dir = tmp_path / "policies"
    pack_dir.mkdir()
    entry = WorkspaceRepository(name="workspace", path=repo_file, policy_pack=pack_dir)
    with factory() as session:
        assert register_workspace_repositories(session, [entry]) == 1
        assert register_workspace_repositories(session, [entry]) == 0
        session.commit()
        row = session.query(RepositoryRow).filter_by(name="workspace").one()
        assert (row.path, row.policy_pack) == (str(repo_file), str(pack_dir))
