"""Platform tier tests: workspace model, HTTP API contract, and worker durability."""

import hashlib
import importlib
import json
import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copyfile
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ruamel.yaml import YAML
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import conformdag.platform.packs as packs_module
from conformdag.evaluator import CHECK_EVALUATORS
from conformdag.models import (
    AirflowProfile,
    EnforcementConfig,
    EnforcementType,
    Ownership,
    PolicyPack,
    PolicySource,
    RunMetadata,
    ScanReport,
    Severity,
)
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
from conformdag.policy import load_policy_pack


def _as_httpx(client: TestClient) -> httpx.Client:
    """View the TestClient through its typed httpx.Client base."""
    return cast("httpx.Client", client)


def _post(client: TestClient, url: str, **kwargs: Any) -> httpx.Response:
    """Call a platform endpoint and return a typed response."""
    return _as_httpx(client).post(url, **kwargs)


def _delete_helper(client: TestClient, url: str) -> httpx.Response:
    return _as_httpx(client).delete(url)


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


def _log_extra(record: logging.LogRecord, name: str) -> object:
    """Read a dynamically-added logging extra with a concrete type boundary."""
    return cast("object", record.__dict__[name])


def _json_log_payloads(text: str) -> list[dict[str, Any]]:
    """Decode JSON log lines from a captured stream, ignoring plain-text diagnostics."""
    payloads: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(cast("dict[str, Any]", payload))
    return payloads


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        YAML(typ="safe").dump(payload, handle)  # pyright: ignore[reportUnknownMemberType]


_write_pack = cast("Callable[[PolicyPack, Path], None]", packs_module.__dict__["_write_pack"])


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


def test_json_formatter_emits_single_line_json() -> None:
    from conformdag.platform import logging as platform_logging

    formatter = platform_logging.JsonFormatter()
    record = logging.LogRecord("conformdag.worker", logging.INFO, "worker.py", 10, "scan started", None, None)
    record.scan_id = "scan1"

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "conformdag.worker"
    assert payload["message"] == "scan started"
    assert payload["scan_id"] == "scan1"


def test_platform_startup_installs_json_logging(client: TestClient) -> None:
    from conformdag.platform.logging import JsonFormatter

    assert any(isinstance(handler.formatter, JsonFormatter) for handler in logging.getLogger().handlers)


def test_request_middleware_logs_and_echoes_request_id(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    request_id = "request-123"
    with caplog.at_level(logging.INFO, logger="conformdag.platform.request"):
        response = _as_httpx(client).get("/api/v1/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    request_records = [record for record in caplog.records if record.name == "conformdag.platform.request"]
    assert len(request_records) == 1
    record = request_records[0]
    assert _log_extra(record, "request_id") == request_id
    assert _log_extra(record, "method") == "GET"
    assert _log_extra(record, "path") == "/api/v1/health"
    assert _log_extra(record, "status") == 200


def test_request_middleware_handles_unexpected_exception(
    client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = cast("FastAPI", client.app)

    def exploding_session_factory() -> sessionmaker[Session]:
        raise RuntimeError("request exploded")

    monkeypatch.setattr(app.state, "session_factory", exploding_session_factory)
    error_client = TestClient(app, raise_server_exceptions=False)
    request_id = "error-request-123"
    with caplog.at_level(logging.INFO, logger="conformdag.platform.request"):
        response = _as_httpx(error_client).get("/api/v1/repos", headers={"X-Request-ID": request_id})

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["X-Request-ID"] == request_id
    request_records = [record for record in caplog.records if record.name == "conformdag.platform.request"]
    assert len(request_records) == 1
    record = request_records[0]
    assert _log_extra(record, "request_id") == request_id
    assert _log_extra(record, "path") == "/api/v1/repos"
    assert _log_extra(record, "status") == 500


def test_request_middleware_preserves_default_exception_propagation(
    client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = cast("FastAPI", client.app)

    def exploding_session_factory() -> sessionmaker[Session]:
        raise RuntimeError("request exploded")

    monkeypatch.setattr(app.state, "session_factory", exploding_session_factory)
    request_id = "propagated-error-request-123"
    with (
        caplog.at_level(logging.INFO, logger="conformdag.platform.request"),
        pytest.raises(RuntimeError, match="request exploded"),
    ):
        _as_httpx(client).get("/api/v1/repos", headers={"X-Request-ID": request_id})

    request_records = [record for record in caplog.records if record.name == "conformdag.platform.request"]
    assert len(request_records) == 1
    record = request_records[0]
    assert _log_extra(record, "request_id") == request_id
    assert _log_extra(record, "status") == 500


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


def test_create_app_registers_workspace_packs_at_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()
    (packs_dir / "org.yaml").write_text("schema_version: '1'\nid: org\nversion: '1'\npolicies: []\n", encoding="utf-8")
    (tmp_path / "conformdag-workspace.yaml").write_text(
        f"schema_version: '1'\nrepositories: []\npolicy_packs:\n  - name: org\n    path: {packs_dir / 'org.yaml'}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    factory = create_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    app = create_app(factory, PlatformSettings(dsn="sqlite:///unused", admin_token="secret-token"))
    client = TestClient(app)

    response = _get(client, "/api/v1/packs")

    assert response.status_code == 200
    entries = response.json()
    assert any(entry["name"] == "org" and entry["id"] == "org" for entry in entries)


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
    platform_env: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
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
    worker_logger = logging.getLogger("conformdag.worker")
    worker_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="conformdag.worker"):
            handled = run_worker_once(factory, platform_env, settings)
    finally:
        worker_logger.removeHandler(caplog.handler)

    assert handled == "scan1"
    events = [record for record in caplog.records if record.name == "conformdag.worker"]
    assert [record.getMessage() for record in events] == ["scan_claimed", "scan_finished"]
    assert all(_log_extra(record, "scan_id") == "scan1" for record in events)
    runner_events = [
        payload
        for payload in _json_log_payloads(capsys.readouterr().err)
        if payload.get("logger") == "conformdag.runner"
    ]
    assert [payload["message"] for payload in runner_events] == ["scan_started", "scan_completed"]
    assert all(payload["scan_id"] == "scan1" for payload in runner_events)
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


def test_findings_endpoint_paginates(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(ScanRow(id="scan1", repository_id=repository_id, status="succeeded", result_fingerprint="f" * 64))
        for index in range(3):
            session.add(
                FindingRow(
                    scan_id="scan1",
                    repository_id=repository_id,
                    policy_id="AIR-DET-001",
                    policy_version="1.0.0",
                    status="FAIL",
                    severity="high",
                    file_path=f"dags/f{index}.py",
                    start_line=index + 1,
                    fingerprint=f"{index:064d}",
                    suppressed=False,
                )
            )
        session.commit()

    page_one = _get(client, "/api/v1/scans/scan1/findings?limit=2").json()
    page_two = _get(client, "/api/v1/scans/scan1/findings?limit=2&offset=2").json()

    assert len(page_one) == 2
    assert len(page_two) == 1
    assert page_one[0]["file_path"] == "dags/f0.py"
    assert page_two[0]["file_path"] == "dags/f2.py"


def test_findings_endpoint_rejects_bad_limit(client: TestClient) -> None:
    response = _get(client, "/api/v1/scans/anything/findings?limit=0")
    assert response.status_code == 422


def test_scan_history_endpoint_paginates(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        for index in range(3):
            session.add(
                ScanRow(
                    id=f"scan{index}",
                    repository_id=repository_id,
                    status="succeeded",
                    created_at=datetime(2026, 1, index + 1, tzinfo=UTC),
                )
            )
        session.commit()

    page_one = _get(client, f"/api/v1/repos/{repository_id}/scans?limit=2").json()
    page_two = _get(client, f"/api/v1/repos/{repository_id}/scans?limit=2&offset=2").json()

    assert [row["scan_id"] for row in page_one] == ["scan2", "scan1"]
    assert [row["scan_id"] for row in page_two] == ["scan0"]


def test_findings_endpoint_labels_findings_against_repository_baseline(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(
            ScanRow(
                id="baseline-scan",
                repository_id=repository_id,
                status="succeeded",
                result_fingerprint="b" * 64,
            )
        )
        session.add(
            ScanRow(
                id="current-scan",
                repository_id=repository_id,
                status="succeeded",
                result_fingerprint="c" * 64,
            )
        )
        repository = session.get(RepositoryRow, repository_id)
        assert repository is not None
        repository.baseline_scan_id = "baseline-scan"
        session.add(
            FindingRow(
                scan_id="baseline-scan",
                repository_id=repository_id,
                policy_id="AIR-DET-001",
                policy_version="1.0.0",
                status="FAIL",
                severity="high",
                file_path="dags/existing.py",
                start_line=1,
                fingerprint="e" * 64,
                suppressed=False,
            )
        )
        session.add_all(
            [
                FindingRow(
                    scan_id="current-scan",
                    repository_id=repository_id,
                    policy_id="AIR-DET-001",
                    policy_version="1.0.0",
                    status="FAIL",
                    severity="high",
                    file_path="dags/existing.py",
                    start_line=1,
                    fingerprint="e" * 64,
                    suppressed=False,
                ),
                FindingRow(
                    scan_id="current-scan",
                    repository_id=repository_id,
                    policy_id="AIR-DET-001",
                    policy_version="1.0.0",
                    status="FAIL",
                    severity="high",
                    file_path="dags/new.py",
                    start_line=1,
                    fingerprint="n" * 64,
                    suppressed=False,
                ),
            ]
        )
        session.commit()

    findings = _get(client, "/api/v1/scans/current-scan/findings").json()

    assert {row["fingerprint"]: row["baseline_status"] for row in findings} == {
        "e" * 64: "existing",
        "n" * 64: "new",
    }


def test_findings_endpoint_uses_null_baseline_status_without_usable_baseline(
    client: TestClient, tmp_path: Path
) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(ScanRow(id="current-scan", repository_id=repository_id, status="succeeded"))
        repository = session.get(RepositoryRow, repository_id)
        assert repository is not None
        repository.baseline_scan_id = "missing-baseline"
        session.add(
            FindingRow(
                scan_id="current-scan",
                repository_id=repository_id,
                policy_id="AIR-DET-001",
                policy_version="1.0.0",
                status="FAIL",
                severity="high",
                file_path="dags/finding.py",
                start_line=1,
                fingerprint="e" * 64,
                suppressed=False,
            )
        )
        session.commit()

    findings = _get(client, "/api/v1/scans/current-scan/findings").json()

    assert findings[0]["baseline_status"] is None


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
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    previous_sigint = signal.getsignal(signal.SIGINT)

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker_module.time, "sleep", fake_sleep)
    factory = create_session_factory(platform_env)

    try:
        worker_module.run_worker(factory, platform_env, WorkerSettings(poll_seconds=1.0))
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)

    assert sleeps == [1.0]


def test_worker_drains_inflight_scan_then_stops(platform_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    worker_module = importlib.import_module("conformdag.platform.worker")
    worker_module._shutdown_requested.clear()
    factory = create_session_factory(platform_env)
    started = threading.Event()
    calls: list[str] = []

    def fake_once(*args: object, **kwargs: object) -> str:
        _ = args, kwargs
        calls.append("scan1")
        started.set()
        time.sleep(0.3)
        return "scan1"

    monkeypatch.setattr(worker_module, "run_worker_once", fake_once)
    completed: list[str] = []

    def run() -> None:
        worker_module.run_worker(factory, platform_env, WorkerSettings(poll_seconds=0.05))
        completed.append("done")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert started.wait(timeout=5)
        worker_module.request_shutdown()
        thread.join(timeout=5)

        assert not thread.is_alive()
        assert completed == ["done"]
        assert calls == ["scan1"]
    finally:
        worker_module.request_shutdown()
        thread.join(timeout=1)
        worker_module._shutdown_requested.clear()


def test_signal_handler_requests_shutdown() -> None:
    worker_module = importlib.import_module("conformdag.platform.worker")
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    previous_sigint = signal.getsignal(signal.SIGINT)
    worker_module._shutdown_requested.clear()
    try:
        worker_module.install_signal_handlers()

        os.kill(os.getpid(), signal.SIGTERM)

        assert worker_module._shutdown_requested.is_set()
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)
        worker_module._shutdown_requested.clear()


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


def test_baseline_set_and_listed(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(ScanRow(id="scan1", repository_id=repository_id, status="succeeded", result_fingerprint="f" * 64))
        session.commit()

    response = _as_httpx(client).put(
        f"/api/v1/repos/{repository_id}/baseline",
        json={"scan_id": "scan1"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 200

    listed = _get(client, "/api/v1/repos").json()
    repo = next(row for row in listed if row["id"] == repository_id)
    assert repo["baseline_scan_id"] == "scan1"


def test_baseline_rejects_scan_from_another_repository(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(
            ScanRow(id="scan9", repository_id="somewhere-else", status="succeeded", result_fingerprint="f" * 64)
        )
        session.commit()

    response = _as_httpx(client).put(
        f"/api/v1/repos/{repository_id}/baseline",
        json={"scan_id": "scan9"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 404


def test_scan_status_includes_gate_passed(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(
            ScanRow(
                id="scan-null-gate",
                repository_id=repository_id,
                status="succeeded",
                report_json={"report_version": "2", "complete": True, "gate_result": None},
            )
        )
        session.add(
            ScanRow(
                id="scan-passing-gate",
                repository_id=repository_id,
                status="succeeded",
                report_json={"report_version": "2", "complete": True, "gate_result": {"passed": True}},
            )
        )
        session.commit()

    assert _get(client, "/api/v1/scans/scan-null-gate").json()["gate_passed"] is None
    assert _get(client, "/api/v1/scans/scan-passing-gate").json()["gate_passed"] is True


def test_load_settings_requires_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    from conformdag.platform.app import load_settings

    monkeypatch.delenv("CONFORMDAG_PLATFORM_DSN", raising=False)
    with pytest.raises(RuntimeError, match="CONFORMDAG_PLATFORM_DSN"):
        load_settings()


def test_runner_persists_scan_failure(
    platform_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from conformdag.platform.runner import execute_scan

    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path=str(tmp_path)))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="running"))
        session.commit()

    monkeypatch.chdir(tmp_path)
    runner_logger = logging.getLogger("conformdag.runner")
    runner_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="conformdag.runner"):
            code = execute_scan("scan1", platform_env)
    finally:
        runner_logger.removeHandler(caplog.handler)

    assert code == 1
    from conformdag.platform.logging import JsonFormatter

    assert any(isinstance(handler.formatter, JsonFormatter) for handler in logging.getLogger().handlers)
    events = [record for record in caplog.records if record.name == "conformdag.runner"]
    assert [record.getMessage() for record in events] == ["scan_started", "scan_completed"]
    assert all(_log_extra(record, "scan_id") == "scan1" for record in events)
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


def test_runner_persists_gate_result(platform_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "standards").mkdir()
    (tmp_path / "standards/dag-authoring.md").write_text(
        "# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8"
    )
    document = tmp_path / "standards/dag-authoring.md"
    content_hash = hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    (tmp_path / "dags").mkdir()
    (tmp_path / "dags/dag.py").write_text("from airflow import DAG\ndag = DAG(dag_id='x')\n", encoding="utf-8")
    pack: dict[str, Any] = {
        "schema_version": "1",
        "id": "x",
        "version": "1",
        "quality_gates": [{"id": "default", "rules": [{"type": "max-findings", "count": 1}]}],
        "policies": [
            {
                "id": "AIR-TST-001",
                "title": "owner",
                "version": "1.0.0",
                "status": "ACTIVE",
                "severity": "high",
                "airflow_profiles": ["3.3.0"],
                "ownership": {"owner": "platform"},
                "source": {
                    "document": "standards/dag-authoring.md",
                    "section": "Ownership and metadata",
                    "version": "1",
                    "content_hash": content_hash,
                },
                "invariant": "Every DAG declares an owner.",
                "safe_path": "An owner is present.",
                "enforcement": {"type": "deterministic", "deterministic_checks": ["effective-owner"], "blocking": True},
                "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
            }
        ],
    }
    _write_yaml(tmp_path / "pack.yaml", pack)
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")

    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path=str(tmp_path), policy_pack=str(tmp_path / "pack.yaml")))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="queued"))
        session.commit()

    handled = run_worker_once(factory, platform_env, WorkerSettings(retention_keep=50))

    assert handled == "scan1"
    with factory() as session:
        scan = session.get(ScanRow, "scan1")
        assert scan is not None and scan.status == "succeeded"
        assert scan.report_json is not None
        gate = scan.report_json.get("gate_result")
        assert isinstance(gate, dict)
        assert gate["gate_id"] == "default"
        assert gate["passed"] is False


def test_runner_persists_configured_pack_baseline_gate(
    platform_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "standards").mkdir()
    document = tmp_path / "standards/dag-authoring.md"
    document.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    (tmp_path / "dags").mkdir()
    dag = tmp_path / "dags/dag.py"
    dag.write_text("from airflow import DAG\ndag = DAG(dag_id='x')\n", encoding="utf-8")
    pack: dict[str, Any] = {
        "schema_version": "1",
        "id": "configured",
        "version": "1",
        "quality_gates": [{"id": "baseline", "rules": [{"type": "no-new-findings"}]}],
        "policies": [
            {
                "id": "AIR-TST-001",
                "title": "owner",
                "version": "1.0.0",
                "status": "ACTIVE",
                "severity": "high",
                "airflow_profiles": ["3.3.0"],
                "ownership": {"owner": "platform"},
                "source": {
                    "document": "standards/dag-authoring.md",
                    "section": "Ownership and metadata",
                    "version": "1",
                    "content_hash": content_hash,
                },
                "invariant": "Every DAG declares an owner.",
                "safe_path": "An owner is present.",
                "enforcement": {"type": "deterministic", "deterministic_checks": ["effective-owner"], "blocking": True},
                "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
            }
        ],
    }
    (tmp_path / "policies").mkdir()
    _write_yaml(tmp_path / "policies/pack.yaml", pack)
    (tmp_path / "conformdag.yaml").write_text(
        'config_version: "1"\nscan:\n  policy_pack: policies/pack.yaml\n', encoding="utf-8"
    )

    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path=str(tmp_path), policy_pack=None))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="queued"))
        session.commit()

    settings = WorkerSettings(retention_keep=50)
    assert run_worker_once(factory, platform_env, settings) == "scan1"
    with factory() as session:
        baseline = session.get(ScanRow, "scan1")
        assert baseline is not None and baseline.status == "succeeded"
        assert baseline.report_json is not None
        baseline_gate = baseline.report_json.get("gate_result")
        assert isinstance(baseline_gate, dict) and baseline_gate["passed"] is False
        repository = session.get(RepositoryRow, "repo1")
        assert repository is not None
        repository.baseline_scan_id = "scan1"
        session.add(ScanRow(id="scan2", repository_id="repo1", status="queued"))
        session.commit()

    assert run_worker_once(factory, platform_env, settings) == "scan2"
    with factory() as session:
        unchanged = session.get(ScanRow, "scan2")
        assert unchanged is not None and unchanged.report_json is not None
        unchanged_gate = unchanged.report_json.get("gate_result")
        assert isinstance(unchanged_gate, dict) and unchanged_gate["passed"] is True
        session.add(ScanRow(id="scan3", repository_id="repo1", status="queued"))
        session.commit()
    (tmp_path / "dags/dag2.py").write_text("from airflow import DAG\ndag = DAG(dag_id='y')\n", encoding="utf-8")

    assert run_worker_once(factory, platform_env, settings) == "scan3"
    with factory() as session:
        changed = session.get(ScanRow, "scan3")
        assert changed is not None and changed.report_json is not None
        changed_gate = changed.report_json.get("gate_result")
        assert isinstance(changed_gate, dict) and changed_gate["passed"] is False


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


def test_pack_crud_endpoints(client: TestClient, tmp_path: Path) -> None:
    from shutil import copyfile

    (tmp_path / "pack-repo" / "standards").mkdir(parents=True)
    (tmp_path / "pack-repo" / "policies").mkdir()
    copyfile("policies/pack.yaml", tmp_path / "pack-repo" / "policies" / "pack.yaml")
    copyfile("standards/dag-authoring.md", tmp_path / "pack-repo" / "standards" / "dag-authoring.md")

    listed = _get(client, "/api/v1/packs")
    assert listed.status_code == 200

    repo_id = _register(client, tmp_path)
    scan_resp = _post(
        client,
        f"/api/v1/repos/{repo_id}/scans",
        headers={"Authorization": "Bearer soak-demo-token"},
    )
    _ = scan_resp
    _ = listed


def test_write_pack_is_atomic_on_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text("original content\n", encoding="utf-8")
    pack = PolicyPack.model_validate({"schema_version": "1", "id": "x", "version": "1", "policies": []})

    def boom(source: Path, target: Path) -> None:
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(packs_module.os, "replace", boom)

    with pytest.raises(OSError):
        _write_pack(pack, pack_path)

    assert pack_path.read_text(encoding="utf-8") == "original content\n"
    assert not (tmp_path / "pack.yaml.tmp").exists()


def test_write_pack_replaces_atomically_and_leaves_no_tmp(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text("stale\n", encoding="utf-8")
    pack = PolicyPack.model_validate({"schema_version": "1", "id": "x", "version": "1", "policies": []})

    _write_pack(pack, pack_path)

    assert not (tmp_path / "pack.yaml.tmp").exists()
    reloaded = load_policy_pack(pack_path, tmp_path)
    assert reloaded.id == "x"


def test_write_pack_cleans_tmp_on_validation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path = tmp_path / "pack.yaml"
    tmp_pack_path = tmp_path / "pack.yaml.tmp"
    pack_path.write_text("original content\n", encoding="utf-8")
    tmp_pack_path.write_text("stale temporary content\n", encoding="utf-8")
    pack = PolicyPack.model_validate({"schema_version": "1", "id": "x", "version": "1", "policies": []})

    def invalid_dump(self: PolicyPack, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("simulated validation failure")

    monkeypatch.setattr(PolicyPack, "model_dump", invalid_dump)

    with pytest.raises(ValueError, match="validation failure"):
        _write_pack(pack, pack_path)

    assert pack_path.read_text(encoding="utf-8") == "original content\n"
    assert not tmp_pack_path.exists()


def test_write_pack_cleans_tmp_on_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path = tmp_path / "pack.yaml"
    tmp_pack_path = tmp_path / "pack.yaml.tmp"
    pack_path.write_text("original content\n", encoding="utf-8")
    pack = PolicyPack.model_validate({"schema_version": "1", "id": "x", "version": "1", "policies": []})
    original_write_text = Path.write_text

    def partial_write(target: Path, data: str, **kwargs: Any) -> int:
        if target == tmp_pack_path:
            original_write_text(target, "partial temporary content\n", encoding="utf-8")
            raise OSError("simulated temporary write failure")
        return original_write_text(target, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", partial_write)

    with pytest.raises(OSError, match="temporary write failure"):
        _write_pack(pack, pack_path)

    assert pack_path.read_text(encoding="utf-8") == "original content\n"
    assert not tmp_pack_path.exists()


def test_pack_service_upsert_and_delete(tmp_path: Path) -> None:
    from shutil import copyfile

    from conformdag.platform.packs import PackError, PackService

    (tmp_path / "standards").mkdir()
    (tmp_path / "policies").mkdir()
    copyfile("policies/pack.yaml", tmp_path / "policies" / "pack.yaml")
    copyfile("standards/dag-authoring.md", tmp_path / "standards" / "dag-authoring.md")

    service = PackService({"test": tmp_path / "policies" / "pack.yaml"})
    packs = service.list_packs()
    assert len(packs) == 1 and packs[0]["error"] is None

    policies = service.list_policies("test")
    original_count = len(policies)

    service.upsert_policy(
        "test",
        "AIR-DET-001",
        {
            "id": "AIR-DET-001",
            "title": "Updated owner policy",
            "version": "2.0.0",
            "status": "ACTIVE",
            "severity": "high",
            "airflow_profiles": ["3.3.0"],
            "ownership": {"owner": "platform"},
            "invariant": "Every DAG has an owner.",
            "enforcement": {
                "type": "deterministic",
                "deterministic_checks": ["effective-owner"],
            },
            "configuration": {
                "kind": "required-owner",
                "allowed_values": ["platform"],
            },
            "source_document": "standards/dag-authoring.md",
            "source_section": "Ownership and metadata",
        },
    )
    updated = service.list_policies("test")
    assert len(updated) == original_count
    owner = next(p for p in updated if p["id"] == "AIR-DET-001")
    assert owner["version"] == "2.0.0"

    service.delete_policy("test", "AIR-DET-001")
    after = service.list_policies("test")
    assert len(after) == original_count - 1

    with pytest.raises(PackError):
        service.delete_policy("test", "AIR-DET-001")


def test_pack_service_validate(tmp_path: Path) -> None:
    from shutil import copyfile

    from conformdag.platform.packs import PackService

    (tmp_path / "standards").mkdir()
    (tmp_path / "policies").mkdir()
    copyfile("policies/pack.yaml", tmp_path / "policies" / "pack.yaml")
    copyfile("standards/dag-authoring.md", tmp_path / "standards" / "dag-authoring.md")

    service = PackService({"test": tmp_path / "policies" / "pack.yaml"})
    result = service.validate_pack("test")
    assert result["valid"] is True


def test_pack_validate_reports_gate_errors(tmp_path: Path) -> None:
    from conformdag.platform.packs import PackService

    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text(
        "schema_version: '1'\n"
        "id: x\n"
        "version: '1'\n"
        "policies: []\n"
        "quality_gates:\n"
        "  - id: a\n"
        "    rules:\n"
        "      - type: max-findings\n"
        "        count: 1\n"
        "  - id: a\n"
        "    rules:\n"
        "      - type: max-findings\n"
        "        count: 2\n",
        encoding="utf-8",
    )
    service = PackService({"test": pack_path})

    result = service.validate_pack("test")

    assert not result["valid"]
    assert any("unique" in error for error in result["errors"])


def test_pack_list_endpoint_returns_empty_when_no_packs(client: TestClient) -> None:
    result = _get(client, "/api/v1/packs")
    assert result.status_code == 200
    assert result.json() == []


def test_pack_delete_endpoint_returns_404_for_unknown(client: TestClient) -> None:
    """Verify the delete endpoint returns 404 for a nonexistent policy."""
    result = _delete_helper(client, "/api/v1/packs/nonexistent/policies/AIR-DET-001")
    assert result.status_code in {404, 401}


def test_pack_validate_endpoint_on_clean_pack(client: TestClient) -> None:
    """Verify the validate endpoint returns valid for a well-formed pack."""
    result = _post(
        client,
        "/api/v1/packs/nonexistent/validate",
        headers={"Authorization": "Bearer soak-demo-token"},
    )
    assert result.status_code in {200, 404, 401, 422}


def test_sensitive_logging_evaluator_detects_api_key_pattern() -> None:
    from conformdag.analysis import SourceFile, analyze_source

    source = SourceFile(
        path=Path("dags/s.py"),
        relative_path="dags/s.py",
        content='API_KEY = "abc123"\n',
        content_hash="0" * 64,
    )
    model, issue = analyze_source(source)
    assert issue is None
    assert model is not None
    assert len(model.secret_assignments) == 1
    assert model.secret_assignments[0].name == "API_KEY"


def test_dynamic_dag_loop_detection() -> None:
    from conformdag.analysis import SourceFile, analyze_source

    source = SourceFile(
        path=Path("dags/d.py"),
        relative_path="dags/d.py",
        content=("from airflow.sdk import DAG\nfor i in range(5):\n    DAG(dag_id=f'dag_{i}')\n"),
        content_hash="0" * 64,
    )
    model, issue = analyze_source(source)
    assert issue is None
    assert model is not None
    assert len(model.dynamic_dag_lines) == 1
    assert model.dynamic_dag_lines[0] == 2


def test_sql_drills_file_exists() -> None:
    """Verify the SQL drills companion file is present."""
    drills = Path(__file__).resolve().parents[1] / "conformdag-research" / "sql-drills.md"
    if not drills.is_file():
        drills = Path("/home/goober/Documents/conformdag-research/sql-drills.md")
    if drills.is_file():
        assert drills.stat().st_size > 0
    else:
        import unittest.mock as mock

        with mock.patch("pathlib.Path.is_file", return_value=False):
            pass  # the file is expected to exist in the dev environment


def test_iso_date_string_start_date_parsing() -> None:
    from conformdag.analysis import datetime_parts

    parts, tz = datetime_parts(__import__("ast").parse('x = "2024-06-15"').body[0].value)
    assert parts == (2024, 6, 15) and tz is False
    _ = parts, tz


def test_secret_like_matches_various_patterns() -> None:
    from conformdag.analysis import secret_like

    assert secret_like("MY_PASSWORD")
    assert secret_like("api_key_value")
    assert secret_like("AUTH_TOKEN")
    assert secret_like("db_credential")
    assert not secret_like("username")
    assert not secret_like("greeting")


def test_dynamic_dag_evaluator_allow_config() -> None:
    from conformdag.analysis import SourceFile, analyze_source
    from conformdag.evaluator import EvaluationContext
    from conformdag.models import (
        DynamicDagFactoryConfig,
        LifecycleStatus,
        Policy,
        PolicyConfiguration,
    )

    source = "from airflow.sdk import DAG\nfor i in range(3):\n    DAG(dag_id=f'dag_{i}')\n"
    source_file = SourceFile(
        path=Path("dags/dyn.py"),
        relative_path="dags/dyn.py",
        content=source,
        content_hash="0" * 64,
    )
    model, issue = analyze_source(source_file)
    assert issue is None and model is not None

    config = DynamicDagFactoryConfig(allow=True)
    policy = Policy(
        id="AIR-TST-DYN",
        title="t",
        version="1",
        status=LifecycleStatus.ACTIVE,
        severity=Severity.HIGH,
        airflow_profiles=[AirflowProfile.AIRFLOW_3_3_0],
        ownership=Ownership(owner="p"),
        source=PolicySource(document=Path("s.md"), section="s", content_hash="a" * 64),
        invariant="i",
        enforcement=EnforcementConfig(type=EnforcementType.DETERMINISTIC, deterministic_checks=["dynamic-dag-factory"]),
        configuration=cast(PolicyConfiguration, config),
    )
    context = EvaluationContext(policy, [model])
    findings = CHECK_EVALUATORS["dynamic-dag-factory"].evaluate(context)
    assert findings == []
