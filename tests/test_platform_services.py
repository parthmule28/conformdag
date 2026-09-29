"""Real-session tests for transport-independent platform services."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conformdag.platform.db import FindingRow, RepositoryRow, ScanRow, initialize_session_factory
from conformdag.platform.services import ConflictError, InvalidOperationError, NotFoundError
from conformdag.platform.services.repositories import (
    list_repositories,
    register_repository,
    register_workspace_repositories,
    repository_trends,
)
from conformdag.platform.services.scans import (
    FindingFilters,
    cancel_scan,
    load_report,
    queue_scan,
    scan_findings,
    scan_history,
    scan_status,
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


def test_scan_queue_cancel_uses_atomic_transition_and_conflict_detail(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with factory() as session:
        with pytest.raises(NotFoundError, match="repository not registered"):
            queue_scan(session, "missing")
        session.add(RepositoryRow(id="repo", name="repo", path=str(tmp_path)))
        session.commit()
        queued = queue_scan(session, "repo")
        assert queued["status"] == "queued"
        row = session.get(ScanRow, queued["scan_id"])
        assert row is not None and row.trigger == "dashboard"
        session.commit()
        assert scan_status(session, queued["scan_id"])["status"] == "queued"
        with pytest.raises(NotFoundError, match="scan not found"):
            cancel_scan(session, "missing")
        assert cancel_scan(session, queued["scan_id"])["status"] == "cancelled"
        with pytest.raises(ConflictError, match="scan already cancelled"):
            cancel_scan(session, queued["scan_id"])


def test_scan_history_findings_filters_and_missing_report(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    now = datetime.now(UTC)
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="repo", path=str(tmp_path)))
        session.add_all(
            [
                ScanRow(id="older", repository_id="repo", status="succeeded", created_at=now - timedelta(days=1)),
                ScanRow(id="newer", repository_id="repo", status="queued", created_at=now),
            ]
        )
        session.add_all(
            [
                FindingRow(
                    scan_id="older",
                    repository_id="repo",
                    policy_id="a",
                    policy_version="1",
                    status="FAIL",
                    severity="high",
                    fingerprint="f1",
                    suppressed=False,
                ),
                FindingRow(
                    scan_id="older",
                    repository_id="repo",
                    policy_id="b",
                    policy_version="1",
                    status="PASS",
                    severity="low",
                    fingerprint="f2",
                    suppressed=True,
                ),
            ]
        )
        session.commit()
        history = scan_history(session, "repo", limit=1, offset=0)
        assert (history.total, [item.scan_id for item in history.items]) == (2, ["newer"])
        findings = scan_findings(session, "older", filters=FindingFilters(status="fail"), limit=10, offset=0)
        assert (findings.total, [item.fingerprint for item in findings.items]) == (1, ["f1"])
        assert findings.items[0].baseline_status is None
        assert (
            scan_findings(
                session, "older", filters=FindingFilters(baseline_status="existing"), limit=10, offset=0
            ).total
            == 0
        )
        for scan_id in ("missing", "older"):
            with pytest.raises(NotFoundError, match="scan report not available"):
                load_report(session, scan_id)
