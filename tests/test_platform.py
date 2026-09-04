"""Platform tier tests: workspace model, HTTP API contract, and worker durability."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copyfile
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from conformdag.models import RunMetadata, ScanReport
from conformdag.platform.app import PlatformSettings, create_app
from conformdag.platform.db import (
    FindingRow,
    RepositoryRow,
    ScanRow,
    claim_queued_scan,
    create_session_factory,
    prune_scan_artifact,
    retention_target_scan_ids,
    stale_running_cutoff,
)
from conformdag.platform.worker import WorkerSettings, run_worker_once


def _as_httpx(client: TestClient) -> httpx.Client:
    """View the TestClient through its typed httpx.Client base."""
    return cast("httpx.Client", client)


def _post(client: TestClient, url: str, **kwargs: Any) -> httpx.Response:
    """Call a platform endpoint and return a typed response."""
    return _as_httpx(client).post(url, **kwargs)


def _get(client: TestClient, url: str) -> httpx.Response:
    """Call a platform endpoint and return a typed response."""
    return _as_httpx(client).get(url)


def _patch(client: TestClient, url: str, **kwargs: Any) -> httpx.Response:
    """Call a platform endpoint and return a typed response."""
    return _as_httpx(client).patch(url, **kwargs)


def _platform_state(client: TestClient) -> tuple[sessionmaker[Session], PlatformSettings]:
    """Return the app's session factory and settings with concrete types."""
    app = cast("FastAPI", client.app)
    factory = cast("sessionmaker[Session]", app.state.session_factory)
    settings = cast("PlatformSettings", app.state.settings)
    return factory, settings


@pytest.fixture(name="platform_env")
def platform_env_fixture(tmp_path: Path) -> str:
    """Create the repository fixture, a SQLite DSN, and return the DSN."""
    (tmp_path / "repo/dags").mkdir(parents=True)
    (tmp_path / "pack.yaml").write_text("schema_version: '1'\nid: x\nversion: '1'\npolicies: []\n", encoding="utf-8")
    return f"sqlite:///{tmp_path / 'platform.db'}"


@pytest.fixture(name="client")
def client_fixture(platform_env: str) -> TestClient:
    factory = create_session_factory(platform_env)
    settings = PlatformSettings(dsn=platform_env, admin_token="secret-token")
    return TestClient(create_app(factory, settings))


def _register(client: TestClient, tmp_path: Path) -> str:
    response = _post(
        client,
        "/api/v1/repos",
        json={"name": "core-dags", "path": str(tmp_path / "repo"), "policy_pack": None},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_workspace_loader_resolves_relative_paths(tmp_path: Path) -> None:
    from conformdag.platform.workspace import load_workspace

    (tmp_path / "dags").mkdir()
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies/pack.yaml").write_text("id: x\n", encoding="utf-8")
    (tmp_path / "conformdag-workspace.yaml").write_text(
        "schema_version: '1'\nrepositories:\n  - name: core\n    path: dags\n    policy_pack: policies/pack.yaml\n",
        encoding="utf-8",
    )

    workspace, resolved = load_workspace(tmp_path / "conformdag-workspace.yaml")

    assert resolved == (tmp_path / "conformdag-workspace.yaml").resolve()
    assert workspace.repositories[0].path == (tmp_path / "dags").resolve()
    assert workspace.repositories[0].policy_pack == (tmp_path / "policies/pack.yaml").resolve()


def test_workspace_rejects_missing_paths_and_duplicates(tmp_path: Path) -> None:
    from conformdag.platform.workspace import WorkspaceError, load_workspace

    (tmp_path / "conformdag-workspace.yaml").write_text(
        "repositories:\n  - name: core\n    path: missing-dir\n", encoding="utf-8"
    )
    with pytest.raises(WorkspaceError, match="does not exist"):
        load_workspace(tmp_path / "conformdag-workspace.yaml")

    (tmp_path / "dags-a").mkdir()
    (tmp_path / "dags-b").mkdir()
    (tmp_path / "dupe.yaml").write_text(
        "repositories:\n  - name: core\n    path: dags-a\n  - name: core\n    path: dags-b\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceError, match="unique"):
        load_workspace(tmp_path / "dupe.yaml")


def test_health_is_open_and_reads_need_no_token(client: TestClient) -> None:
    assert _get(client, "/api/v1/health").status_code == 200
    assert _get(client, "/api/v1/repos").status_code == 200


def test_mutations_require_admin_token(client: TestClient, platform_env: str) -> None:
    _ = platform_env
    denied = _post(client, "/api/v1/repos", json={"name": "x", "path": "."})
    assert denied.status_code == 401

    wrong = _post(
        client,
        "/api/v1/repos",
        json={"name": "x", "path": "."},
        headers={"Authorization": "Bearer nope"},
    )
    assert wrong.status_code == 401


def test_register_and_trigger_scan_lifecycle(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)

    triggered = _post(
        client,
        f"/api/v1/repos/{repository_id}/scans",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert triggered.status_code == 200
    scan_id = triggered.json()["scan_id"]

    factory, _ = _platform_state(client)
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        assert scan is not None and scan.status == "queued"

    history = _get(client, f"/api/v1/repos/{repository_id}/scans")
    assert [row["scan_id"] for row in history.json()] == [scan_id]

    cancelled = _post(
        client,
        f"/api/v1/scans/{scan_id}/cancel",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert cancelled.status_code == 200
    assert _get(client, f"/api/v1/scans/{scan_id}").json()["status"] == "cancelled"


def test_workspace_load_registers_repositories(client: TestClient, platform_env: str, tmp_path: Path) -> None:
    _ = platform_env
    workspace_path = tmp_path / "ws"
    (workspace_path / "dags").mkdir(parents=True)
    (workspace_path / "conformdag-workspace.yaml").write_text(
        "repositories:\n  - name: ws-repo\n    path: dags\n", encoding="utf-8"
    )
    response = _post(
        client,
        "/api/v1/workspace/load",
        json={"path": str(workspace_path / "conformdag-workspace.yaml")},
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["repositories_registered"] == 1
    names = [row["name"] for row in _get(client, "/api/v1/repos").json()]
    assert "ws-repo" in names


def test_abandoned_running_scan_is_reclaimed_within_attempt_budget(platform_env: str) -> None:
    factory = create_session_factory(platform_env)
    with factory() as session:
        repository = RepositoryRow(id="repo1", name="r", path=".")
        session.add(repository)
        session.add(
            ScanRow(
                id="scan1",
                repository_id="repo1",
                status="running",
                claimed_at=datetime.now(UTC) - timedelta(hours=2),
                attempts=1,
            )
        )
        session.commit()

        claimed = claim_queued_scan(session, stale_running_cutoff(600), max_attempts=3)

        assert claimed is not None
        assert claimed.id == "scan1"
        assert claimed.attempts == 2


def test_abandoned_scan_fails_after_attempt_budget(platform_env: str) -> None:
    factory = create_session_factory(platform_env)
    with factory() as session:
        repository = RepositoryRow(id="repo1", name="r", path=".")
        session.add(repository)
        session.add(
            ScanRow(
                id="scan1",
                repository_id="repo1",
                status="running",
                claimed_at=datetime.now(UTC) - timedelta(hours=2),
                attempts=3,
            )
        )
        session.commit()

        claimed = claim_queued_scan(session, stale_running_cutoff(600), max_attempts=3)

        assert claimed is None
        scan = session.get(ScanRow, "scan1")
        assert scan is not None
        assert scan.status == "failed"
        assert scan.error is not None and "abandoned" in scan.error


def test_worker_executes_queued_scan_end_to_end(
    platform_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "standards").mkdir()
    copyfile("standards/dag-authoring.md", tmp_path / "standards/dag-authoring.md")
    (tmp_path / "dags").mkdir()
    (tmp_path / "dags/dag.py").write_text("from airflow import DAG\ndag = DAG(dag_id='x')\n", encoding="utf-8")
    copyfile("policies/pack.yaml", tmp_path / "pack.yaml")
    (tmp_path / "conformdag.yaml").write_text(
        'config_version: "1"\nscan:\n  include: ["dags/**/*.py"]\n', encoding="utf-8"
    )

    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path=str(tmp_path), policy_pack=str(tmp_path / "pack.yaml")))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="queued"))
        session.commit()

    settings = WorkerSettings(retention_keep=50)
    handled = run_worker_once(factory, platform_env, settings)

    assert handled == "scan1"
    with factory() as session:
        scan = session.get(ScanRow, "scan1")
        assert scan is not None and scan.status == "succeeded"
        assert scan.report_json is not None
        assert scan.result_fingerprint is not None


def test_suppression_lifecycle_is_audited(client: TestClient) -> None:
    created = _post(
        client,
        "/api/v1/suppressions",
        json={
            "policy_id": "AIR-DET-001",
            "fingerprint": "a" * 64,
            "reason": "legacy DAG, remediation scheduled",
            "owner": "platform",
            "expires_at": "2027-01-01T00:00:00Z",
        },
        headers={"Authorization": "Bearer secret-token"},
    )
    assert created.status_code == 200
    suppression = created.json()
    assert suppression["source"] == "platform"

    updated = _patch(
        client,
        f"/api/v1/suppressions/{suppression['id']}",
        json={"reason": "remediation moved to Q4"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert updated.status_code == 200
    assert updated.json()["reason"] == "remediation moved to Q4"

    listed = _get(client, "/api/v1/suppressions")
    assert [row["id"] for row in listed.json()] == [suppression["id"]]


def test_findings_endpoint_filters_by_status(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    scan_id = _post(
        client,
        f"/api/v1/repos/{repository_id}/scans",
        headers={"Authorization": "Bearer secret-token"},
    ).json()["scan_id"]
    factory, _ = _platform_state(client)
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        assert scan is not None
        scan.report_json = {"report_version": "2", "complete": True, "result_fingerprint": "0" * 64}
        session.add(
            FindingRow(
                scan_id=scan_id,
                repository_id=repository_id,
                policy_id="AIR-DET-001",
                policy_version="1.0.0",
                status="FAIL",
                severity="high",
                file_path="dags/x.py",
                start_line=3,
                fingerprint="b" * 64,
            )
        )
        session.commit()

    failing = _get(client, f"/api/v1/scans/{scan_id}/findings?status=fail")
    assert [row["policy_id"] for row in failing.json()] == ["AIR-DET-001"]
    passing = _get(client, f"/api/v1/scans/{scan_id}/findings?status=pass")
    assert passing.json() == []


def test_export_json_is_byte_compatible_with_stored_report(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    scan_id = _post(
        client,
        f"/api/v1/repos/{repository_id}/scans",
        headers={"Authorization": "Bearer secret-token"},
    ).json()["scan_id"]
    factory, _ = _platform_state(client)
    stored = ScanReport(
        complete=True,
        result_fingerprint="c" * 64,
        run=RunMetadata(
            tool_version="test",
            policy_pack_id="test-pack",
            policy_pack_version="1.0.0",
            timestamp=datetime.now(UTC),
        ),
    )
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        assert scan is not None
        scan.report_json = stored.model_dump(mode="json")
        scan.result_fingerprint = stored.result_fingerprint
        scan.complete = True
        scan.status = "succeeded"
        session.commit()

    exported = _get(client, f"/api/v1/scans/{scan_id}/export/json")
    assert exported.status_code == 200
    assert json.loads(exported.text)["result_fingerprint"] == "c" * 64
    sarif = _get(client, f"/api/v1/scans/{scan_id}/export/sarif")
    assert sarif.status_code == 200
    assert json.loads(sarif.text)["version"] == "2.1.0"


def test_worker_skips_cancelled_scan(platform_env: str) -> None:
    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path="."))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="cancelled"))
        session.commit()

    handled = run_worker_once(factory, platform_env, WorkerSettings(retention_keep=50))

    assert handled is None


def test_worker_settings_resolve_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:

    monkeypatch.setenv("CONFORMDAG_WORKER_POLL_SECONDS", "0.5")
    monkeypatch.setenv("CONFORMDAG_WORKER_MAX_ATTEMPTS", "7")
    settings = WorkerSettings.from_environment()

    assert settings.poll_seconds == 0.5
    assert settings.max_attempts == 7


def test_worker_loop_sleeps_when_idle(platform_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform import worker as worker_module

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker_module.time, "sleep", fake_sleep)
    factory = create_session_factory(platform_env)

    worker_module.run_worker(factory, platform_env, WorkerSettings(poll_seconds=1.0))

    assert sleeps == [1.0]


def test_register_repository_rejects_missing_paths(client: TestClient) -> None:
    response = _post(
        client,
        "/api/v1/repos",
        json={"name": "ghost", "path": "/nonexistent/path"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 422


def test_trigger_scan_unknown_repository_returns_404(client: TestClient) -> None:
    response = _post(
        client,
        "/api/v1/repos/nope/scans",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 404


def test_cancel_terminal_scan_conflicts(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    scan_id = _post(
        client,
        f"/api/v1/repos/{repository_id}/scans",
        headers={"Authorization": "Bearer secret-token"},
    ).json()["scan_id"]
    factory, _ = _platform_state(client)
    with factory() as session:
        scan = session.get(ScanRow, scan_id)
        assert scan is not None
        scan.status = "succeeded"
        session.commit()

    response = _post(
        client,
        f"/api/v1/scans/{scan_id}/cancel",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 409


def test_load_settings_requires_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform.app import load_settings

    monkeypatch.delenv("CONFORMDAG_PLATFORM_DSN", raising=False)
    with pytest.raises(RuntimeError, match="CONFORMDAG_PLATFORM_DSN"):
        load_settings()


def test_runner_persists_scan_failure(platform_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform.runner import execute_scan

    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path=str(tmp_path)))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="running"))
        session.commit()

    monkeypatch.chdir(tmp_path)
    code = execute_scan("scan1", platform_env)

    assert code == 1
    with factory() as session:
        scan = session.get(ScanRow, "scan1")
        assert scan is not None and scan.status == "failed"
        assert scan.error is not None and "cannot read" in scan.error


def test_runner_rejects_non_running_scan(platform_env: str) -> None:
    from conformdag.platform.runner import execute_scan

    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path="."))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="queued"))
        session.commit()

    assert execute_scan("scan1", platform_env) == 2
    assert execute_scan("missing", platform_env) == 2


def test_load_settings_reads_token_and_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform.app import load_settings

    monkeypatch.setenv("CONFORMDAG_PLATFORM_DSN", "postgresql://db")
    monkeypatch.setenv("CONFORMDAG_PLATFORM_TOKEN", "t")
    monkeypatch.setenv("CONFORMDAG_PLATFORM_RETENTION_KEEP", "7")

    settings = load_settings()

    assert settings.admin_token == "t"
    assert settings.retention_keep == 7


def test_register_repository_rejects_duplicate_names(client: TestClient, tmp_path: Path) -> None:
    _register(client, tmp_path)
    duplicate = _post(
        client,
        "/api/v1/repos",
        json={"name": "core-dags", "path": str(tmp_path / "repo")},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert duplicate.status_code == 409


def test_workspace_rejects_duplicate_pack_names_and_non_mapping(tmp_path: Path) -> None:
    from conformdag.platform.workspace import WorkspaceError, load_workspace

    (tmp_path / "packs").mkdir()
    (tmp_path / "packs/a.yaml").write_text("id: a\n", encoding="utf-8")
    (tmp_path / "packs/b.yaml").write_text("id: b\n", encoding="utf-8")
    (tmp_path / "dupe-packs.yaml").write_text(
        "policy_packs:\n  - name: p\n    path: packs/a.yaml\n  - name: p\n    path: packs/b.yaml\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceError, match="unique"):
        load_workspace(tmp_path / "dupe-packs.yaml")

    (tmp_path / "list.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="YAML mapping"):
        load_workspace(tmp_path / "list.yaml")


def test_worker_reports_runner_failure_outcome(platform_env: str, tmp_path: Path) -> None:
    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path=str(tmp_path)))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="queued"))
        session.commit()

    handled = run_worker_once(factory, platform_env, WorkerSettings(retention_keep=50))

    assert handled == "scan1"
    with factory() as session:
        scan = session.get(ScanRow, "scan1")
        assert scan is not None and scan.status == "failed"
        assert scan.error is not None and "cannot read" in scan.error


def test_unknown_api_paths_return_json_404(client: TestClient) -> None:
    response = _get(client, "/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"].startswith("unknown API path")


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "src/conformdag/platform/static/index.html").is_file(),
    reason="dashboard static assets are not built",
)
def test_dashboard_index_is_served(client: TestClient) -> None:
    response = _get(client, "/")
    assert response.status_code == 200
    assert "ConformDAG Platform" in response.text


def test_retention_clears_artifacts_and_keeps_findings(platform_env: str) -> None:
    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path="."))
        for index in range(4):
            session.add(
                ScanRow(
                    id=f"scan{index}",
                    repository_id="repo1",
                    status="succeeded",
                    report_json={"report_version": "2"},
                )
            )
        session.commit()

        targets = retention_target_scan_ids(session, "repo1", keep=2)
        for scan_id in targets:
            prune_scan_artifact(session, scan_id)
        session.commit()

        scans = {scan.id: scan for scan in session.scalars(select(ScanRow)).all()}
        assert targets == ["scan0", "scan1"]
        assert scans["scan0"].report_json is None
        assert scans["scan1"].report_json is None
        assert scans["scan2"].report_json is not None
        assert scans["scan3"].report_json is not None
        assert len(scans) == 4


def testworker_parse_cache_env_controls_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import conformdag.platform.runner as runner_module
    from conformdag.analysis import ParseCache

    monkeypatch.delenv("CONFORMDAG_WORKER_PARSE_CACHE_DIR", raising=False)
    assert runner_module.worker_parse_cache() is None

    monkeypatch.setenv("CONFORMDAG_WORKER_PARSE_CACHE_DIR", str(tmp_path / "pc"))
    cache = runner_module.worker_parse_cache()
    assert isinstance(cache, ParseCache)
    assert cache.directory == tmp_path / "pc"


def test_parse_cache_round_trip_is_faithful(
    build_repository: Callable[[Path], Path], platform_env: str, tmp_path: Path
) -> None:
    _ = platform_env
    from conformdag.analysis import ParseCache, SourceFile, analyze_source
    from conformdag.scan import scan_repository

    build_repository(tmp_path)
    cache_dir = tmp_path / "parse-cache"
    cache = ParseCache(cache_dir)
    source = SourceFile(
        path=tmp_path / "dags" / "sample.py",
        relative_path="dags/sample.py",
        content="from airflow import DAG\n\ndag = DAG(dag_id='x')\n",
        content_hash="a" * 64,
    )

    fresh, fresh_issue = analyze_source(source)
    cached, cached_issue = analyze_source(source, cache)
    hit, hit_issue = analyze_source(source, cache)
    assert fresh is not None and cached is not None and hit is not None
    assert fresh_issue is None and cached_issue is None and hit_issue is None
    assert hit == cached, "cache hit must equal the freshly parsed model"
    assert hit.dags == fresh.dags
    assert hit.source is source
    assert len(list(cache_dir.glob("*.pkl"))) == 1

    scanned_cached = scan_repository(_scan_repo(tmp_path), parse_cache=cache)
    scanned_plain = scan_repository(_scan_repo(tmp_path), parse_cache=None)
    assert scanned_cached.result_fingerprint == scanned_plain.result_fingerprint
    _ = ScanReport


def _scan_repo(tmp_path: Path) -> Path:
    from shutil import copyfile

    root = tmp_path / "scan-repo"
    if not (root / "policies").is_dir():
        (root / "policies").mkdir(parents=True)
        (root / "standards").mkdir(parents=True)
        (root / "dags").mkdir(parents=True)
        copyfile("policies/pack.yaml", root / "policies" / "pack.yaml")
        copyfile("standards/dag-authoring.md", root / "standards" / "dag-authoring.md")
        (root / "conformdag.yaml").write_text(
            'config_version: "1"\nscan:\n  policy_pack: policies/pack.yaml\n',
            encoding="utf-8",
        )
        (root / "dags" / "dag.py").write_text(
            "from datetime import timedelta\n"
            "from airflow import DAG\n"
            "from airflow.providers.standard.operators.empty import EmptyOperator\n"
            "dag = DAG(dag_id='clean', owner='platform', tags=['domain:data', 'owner'])\n"
            "task = EmptyOperator(\n"
            "    task_id='t', retries=2,\n"
            "    execution_timeout=timedelta(seconds=300), retry_delay=timedelta(seconds=60)\n"
            ")\n",
            encoding="utf-8",
        )
    return root
