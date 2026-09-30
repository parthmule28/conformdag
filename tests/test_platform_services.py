"""Real-session tests for transport-independent platform services."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from conformdag.models import FindingStatus, RemediationAction, RemediationPayload, RemediationTarget, Severity
from conformdag.platform.db import FindingRow, RepositoryRow, ScanRow, initialize_session_factory
from conformdag.platform.domain import ScanStatus
from conformdag.platform.services import ConflictError, InvalidOperationError, NotFoundError
from conformdag.platform.services.baselines import BaselineAssignment, set_baseline
from conformdag.platform.services.repositories import (
    RepositoryRecord,
    RepositoryRegistration,
    list_repositories,
    register_repository,
    register_workspace_repositories,
    repository_trends,
)
from conformdag.platform.services.scans import (
    FindingFilters,
    FindingRecord,
    ScanStatusRecord,
    ScanSummaryRecord,
    ScanTransition,
    cancel_scan,
    load_report,
    queue_scan,
    scan_findings,
    scan_history,
    scan_status,
)
from conformdag.platform.services.suppressions import (
    SuppressionRecord,
    create_suppression,
    list_suppressions,
    update_suppression,
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
        repositories = list_repositories(session)
        assert all(isinstance(row, RepositoryRecord) for row in repositories)
        assert [row.name for row in repositories] == ["alpha", "zeta"]
        assert repositories[0].path == str(root.resolve())
        with pytest.raises(NotFoundError, match="repository not registered"):
            repository_trends(session, repository_id="missing", now=datetime.now(UTC), days=7)


def test_repository_unique_flush_conflict_recovers_after_caller_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with factory() as session:
        session.add(RepositoryRow(id="existing", name="same", path=str(tmp_path)))
        session.commit()
        # Model a concurrent insert after the service's duplicate precheck; the
        # actual uniqueness failure still comes from the real SQLite index.
        real_scalar = session.scalar

        def _stale_duplicate_check(*_args: object, **_kwargs: object) -> None:
            return None

        monkeypatch.setattr(session, "scalar", _stale_duplicate_check)
        with pytest.raises(ConflictError, match="repository name already registered"):
            register_repository(session, name="same", path=str(tmp_path), policy_pack=None, airflow_profile=None)
        monkeypatch.setattr(session, "scalar", real_scalar)
        session.rollback()
        registered = register_repository(
            session, name="good", path=str(tmp_path), policy_pack=None, airflow_profile=None
        )
        session.commit()
        assert isinstance(registered, RepositoryRegistration)
        assert registered.name == "good"


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
        assert isinstance(queued, ScanTransition)
        assert queued.status is ScanStatus.QUEUED
        row = session.get(ScanRow, queued.scan_id)
        assert row is not None and row.trigger == "dashboard"
        session.commit()
        status = scan_status(session, queued.scan_id)
        assert isinstance(status, ScanStatusRecord)
        assert status.status is ScanStatus.QUEUED
        with pytest.raises(NotFoundError, match="scan not found"):
            cancel_scan(session, "missing")
        cancelled = cancel_scan(session, queued.scan_id)
        assert isinstance(cancelled, ScanTransition)
        assert cancelled.status is ScanStatus.CANCELLED
        with pytest.raises(ConflictError, match="scan already cancelled"):
            cancel_scan(session, queued.scan_id)


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
        assert isinstance(history.items[0], ScanSummaryRecord)
        assert history.items[0].status is ScanStatus.QUEUED
        findings = scan_findings(session, "older", filters=FindingFilters(status="fail"), limit=10, offset=0)
        assert (findings.total, [item.fingerprint for item in findings.items]) == (1, ["f1"])
        assert isinstance(findings.items[0], FindingRecord)
        assert findings.items[0].status is FindingStatus.FAIL
        assert findings.items[0].severity is Severity.HIGH
        assert findings.items[0].baseline_status is None
        assert (
            scan_findings(
                session, "older", filters=FindingFilters(baseline_status="existing"), limit=10, offset=0
            ).total
            == 0
        )
        with pytest.raises(InvalidOperationError, match="invalid baseline status"):
            scan_findings(session, "older", filters=FindingFilters(baseline_status="typo"), limit=10, offset=0)
        for scan_id in ("missing", "older"):
            with pytest.raises(NotFoundError, match="scan report not available"):
                load_report(session, scan_id)


def test_scan_finding_service_validates_stored_remediation_payload(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    fix = RemediationPayload(
        fix_kind="set-kwarg",
        action=RemediationAction.SET_KWARG,
        kwarg="owner",
        target=RemediationTarget(line=3),
        value="platform",
    )
    with factory() as session:
        session.add(RepositoryRow(id="repo", name="repo", path=str(tmp_path)))
        session.add(ScanRow(id="scan", repository_id="repo", status="succeeded"))
        session.add(
            FindingRow(
                scan_id="scan",
                repository_id="repo",
                policy_id="valid-fix",
                policy_version="1",
                status="FAIL",
                severity="high",
                fingerprint="valid",
                suppressed=False,
                fix_json=fix.model_dump(mode="json"),
            )
        )
        session.commit()

        valid = scan_findings(session, "scan", filters=FindingFilters(policy_id="valid-fix"), limit=10, offset=0).items[
            0
        ]
        assert isinstance(valid.fix, RemediationPayload)
        assert valid.fix == fix

        session.add(
            FindingRow(
                scan_id="scan",
                repository_id="repo",
                policy_id="invalid-fix",
                policy_version="1",
                status="FAIL",
                severity="high",
                fingerprint="invalid",
                suppressed=False,
                fix_json={"fix_kind": "set-kwarg", "action": "not-a-remediation-action"},
            )
        )
        session.commit()
        with pytest.raises(ValidationError):
            scan_findings(session, "scan", filters=FindingFilters(policy_id="invalid-fix"), limit=10, offset=0)


def test_baseline_requires_same_repository_succeeded_complete_scan(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with factory() as session:
        session.add_all(
            [
                RepositoryRow(id="first", name="first", path=str(tmp_path)),
                RepositoryRow(id="second", name="second", path=str(tmp_path)),
            ]
        )
        session.add_all(
            [
                ScanRow(id="eligible", repository_id="first", status="succeeded", complete=True),
                ScanRow(id="incomplete", repository_id="first", status="succeeded", complete=False),
                ScanRow(id="queued", repository_id="first", status="queued", complete=None),
                ScanRow(id="foreign", repository_id="second", status="succeeded", complete=True),
            ]
        )
        session.commit()
        with pytest.raises(NotFoundError, match="repository not registered"):
            set_baseline(session, "missing", "eligible")
        for scan_id in ("missing", "foreign"):
            with pytest.raises(NotFoundError, match="scan not found for this repository"):
                set_baseline(session, "first", scan_id)
        for scan_id in ("incomplete", "queued"):
            with pytest.raises(ConflictError, match="scan is not eligible as a baseline"):
                set_baseline(session, "first", scan_id)
        assignment = set_baseline(session, "first", "eligible")
        assert isinstance(assignment, BaselineAssignment)
        assert (assignment.repository_id, assignment.baseline_scan_id) == ("first", "eligible")
        session.rollback()
        rolled_back = session.get(RepositoryRow, "first")
        assert rolled_back is not None and rolled_back.baseline_scan_id is None
        set_baseline(session, "first", "eligible")
        session.commit()
    with factory() as session:
        row = session.get(RepositoryRow, "first")
        assert row is not None and row.baseline_scan_id == "eligible"


def test_suppression_create_unique_update_and_rollback(tmp_path: Path) -> None:
    factory = initialize_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    expiry = datetime.now(UTC) + timedelta(days=1)
    with factory() as session:
        first = create_suppression(
            session, policy_id="p", fingerprint="f", reason="reason", owner="owner", expires_at=expiry
        )
        assert isinstance(first, SuppressionRecord)
        assert first.source == "platform"
        assert first.created_at is not None
        assert first.expires_at == expiry
        session.commit()
        with pytest.raises(ConflictError, match="suppression already exists for this policy finding"):
            create_suppression(
                session, policy_id="p", fingerprint="f", reason="again", owner="owner", expires_at=expiry
            )
        session.rollback()
        other = create_suppression(
            session, policy_id="p", fingerprint="other", reason="second", owner="owner", expires_at=expiry
        )
        session.commit()
        suppressions = list_suppressions(session)
        assert all(isinstance(row, SuppressionRecord) for row in suppressions)
        assert [row.id for row in suppressions] == [first.id, other.id]
        with pytest.raises(NotFoundError, match="suppression not found"):
            update_suppression(session, "missing", reason=None, owner=None, expires_at=None)
        unchanged = update_suppression(session, first.id, reason=None, owner=None, expires_at=None)
        assert (unchanged.reason, unchanged.owner) == ("reason", "owner")
        updated = update_suppression(session, first.id, reason="changed", owner="new", expires_at=None)
        assert (updated.reason, updated.owner) == ("changed", "new")
