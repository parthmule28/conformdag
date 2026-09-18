"""Reusable, production-faithful data for the disposable demo platform.

Every demo row is produced the same way production produces rows: the schema
exists exclusively through ``initialize_session_factory()`` (Alembic
migrations), every scan is queued and completed through the normal worker and
runner against ``scan_repository()``, and suppressions are real durable rows
whose fingerprints are read from a persisted scan report — never synthetic
report, finding, or suppression inserts. ``seed_demo_scenario()`` completes
its baseline, probe, and current scans synchronously through
``run_worker_once()``; ``start_demo_worker()`` then starts the ordinary
asynchronous worker loop so interactive journeys behave like production.
All files are rooted beneath the caller-provided root so the demo stays
confined to throwaway state.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from conformdag.models import FindingStatus, ScanReport
from conformdag.platform.db import (
    RepositoryRow,
    ScanRow,
    SuppressionRow,
    create_session_factory,
    initialize_session_factory,
    new_id,
    new_suppression_id,
    utcnow,
)
from conformdag.platform.worker import WorkerSettings, run_worker, run_worker_once

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


STANDARDS_DOCUMENT = """# DAG Authoring Standards

## Ownership and metadata

Every DAG declares an approved owner and required metadata so operational responsibility is
discoverable without executing the DAG.

## Execution safety

Tasks use bounded timeouts and retries, avoid module-scope I/O, and use approved operators and
imports for the selected Airflow runtime profile.
"""

CONFORMING_DAG = '''"""A conforming demo DAG used as the repository baseline."""

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from pendulum import datetime

with DAG(
    dag_id="demo_governed_dag",
    owner="platform",
    tags=["domain:data", "owner:platform"],
    start_date=datetime(2026, 1, 1, tz="UTC"),
) as dag:
    EmptyOperator(task_id="start")
'''

VIOLATING_DAG = '''"""A deliberately non-conforming demo DAG with two deterministic findings."""

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from pendulum import datetime

with DAG(
    dag_id="demo_governed_dag",
    tags=["domain:data"],
    start_date=datetime(2026, 1, 1, tz="UTC"),
) as dag:
    EmptyOperator(task_id="start")
'''

BROKEN_DAG = '''"""A broken fixture retained for the platform e2e journey."""

def broken(:
    this is not valid python
'''

DEMO_REPOSITORY_NAME = "e2e-healthy"
BROKEN_REPOSITORY_NAME = "e2e-broken"
DEMO_DAG_PATH = Path(DEMO_REPOSITORY_NAME) / "dags" / "demo_dag.py"
TERMINAL_SCAN_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
SEED_DEADLINE_SECONDS = 120.0
SEED_WORKER_SETTINGS = WorkerSettings(
    poll_seconds=0.1,
    idle_seconds=600,
    timeout_seconds=120,
    max_attempts=2,
    retention_keep=50,
)


@dataclass(frozen=True)
class DemoWorkspace:
    """Paths for one disposable demo workspace and its platform database."""

    root: Path
    workspace_path: Path
    pack_path: Path
    dsn: str


@dataclass(frozen=True)
class DemoScenario:
    """Opaque identifiers for durable rows created by the demo seed."""

    ids: Mapping[str, str]


def _provenance(section: str, source_hash: str) -> str:
    return f'{{document: standards/dag-authoring.md, section: "{section}", version: "1", content_hash: {source_hash}}}'


def _write_pack(root: Path) -> Path:
    """Write the local policy pack with provenance tied to the local standard."""
    source_hash = hashlib.sha256(STANDARDS_DOCUMENT.encode("utf-8")).hexdigest()
    pack_yaml = f"""schema_version: "1"
id: conformdag-e2e-pack
version: 1.0.0
policies:
  - id: AIR-DET-001
    title: Every DAG has an approved owner
    version: 1.0.0
    status: ACTIVE
    severity: high
    ownership: {{owner: platform}}
    source: {_provenance("Ownership and metadata", source_hash)}
    invariant: Every DAG declares an approved owner.
    safe_path: An owner is present and belongs to the configured allow-list.
    enforcement: {{type: deterministic, deterministic_checks: [effective-owner], blocking: true}}
    configuration: {{kind: required-owner, allowed_values: [platform]}}
  - id: AIR-DET-002
    title: DAG tags use approved keys and values
    version: 1.0.0
    status: ACTIVE
    severity: medium
    ownership: {{owner: platform}}
    source: {_provenance("Ownership and metadata", source_hash)}
    invariant: DAG tags use the policy-defined key and value vocabulary.
    safe_path: Required metadata tags are present.
    enforcement: {{type: deterministic, deterministic_checks: [tags], blocking: true}}
    configuration: {{kind: required-tags, required_keys: [domain, owner], allowed_values: {{domain: [data, analytics, platform]}}}}
quality_gates:
  - id: baseline-gate
    rules:
      - type: max-findings
        count: 0
"""
    pack_path = root / "packs" / "conformdag-e2e-pack.yaml"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(pack_yaml, encoding="utf-8")
    return pack_path


def _build_workspace_files(root: Path) -> DemoWorkspace:
    """Create standards, policy, source repositories, and workspace manifest."""
    standards_path = root / "standards" / "dag-authoring.md"
    standards_path.parent.mkdir(parents=True, exist_ok=True)
    standards_path.write_text(STANDARDS_DOCUMENT, encoding="utf-8")
    pack_path = _write_pack(root)

    demo_repository = root / DEMO_REPOSITORY_NAME
    demo_dags = demo_repository / "dags"
    demo_dags.mkdir(parents=True, exist_ok=True)
    (demo_dags / "demo_dag.py").write_text(CONFORMING_DAG, encoding="utf-8")

    broken_repository = root / BROKEN_REPOSITORY_NAME
    broken_dags = broken_repository / "dags"
    broken_dags.mkdir(parents=True, exist_ok=True)
    (broken_dags / "broken_dag.py").write_text(BROKEN_DAG, encoding="utf-8")

    workspace_path = root / "conformdag-workspace.yaml"
    workspace_path.write_text(
        f"""schema_version: "1"
repositories:
  - name: {DEMO_REPOSITORY_NAME}
    path: {demo_repository}
    policy_pack: {pack_path}
  - name: {BROKEN_REPOSITORY_NAME}
    path: {broken_repository}
    policy_pack: {pack_path}
policy_packs:
  - name: conformdag-e2e-pack
    path: {pack_path}
""",
        encoding="utf-8",
    )
    return DemoWorkspace(
        root=root,
        workspace_path=workspace_path,
        pack_path=pack_path,
        dsn=f"sqlite:///{root / 'platform.db'}",
    )


def build_demo_workspace(root: Path) -> DemoWorkspace:
    """Build all disposable demo files beneath ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    return _build_workspace_files(root)


def _queue_scan(session: Session, repository_id: str) -> str:
    scan = ScanRow(id=new_id(), repository_id=repository_id, status="queued", trigger="demo")
    session.add(scan)
    session.commit()
    return scan.id


def _queue_repositories(session_factory: sessionmaker[Session], workspace: DemoWorkspace) -> dict[str, str]:
    """Create durable repository rows and the initial baseline job."""
    with session_factory() as session:
        repository = RepositoryRow(
            id=new_id(),
            name=DEMO_REPOSITORY_NAME,
            path=str(workspace.root / DEMO_REPOSITORY_NAME),
            policy_pack=str(workspace.pack_path),
        )
        broken_repository = RepositoryRow(
            id=new_id(),
            name=BROKEN_REPOSITORY_NAME,
            path=str(workspace.root / BROKEN_REPOSITORY_NAME),
            policy_pack=str(workspace.pack_path),
        )
        session.add_all([repository, broken_repository])
        baseline_scan_id = _queue_scan(session, repository.id)
        return {
            "repository": repository.id,
            "broken_repository": broken_repository.id,
            "baseline_scan": baseline_scan_id,
        }


def _scan_state(session_factory: sessionmaker[Session], scan_id: str) -> tuple[str, bool | None, str | None] | None:
    with session_factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None:
            return None
        return scan.status, scan.complete, scan.error


def _complete_scan(
    session_factory: sessionmaker[Session],
    dsn: str,
    scan_id: str,
    *,
    expected_status: str,
    expected_complete: bool,
) -> None:
    """Drive one queued job through the normal worker until its terminal state."""
    deadline = time.monotonic() + SEED_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        state = _scan_state(session_factory, scan_id)
        if state is None:
            raise RuntimeError(f"seed scan {scan_id} disappeared; observed state missing")
        status, complete, error = state
        if status in TERMINAL_SCAN_STATUSES:
            if status != expected_status or complete is not expected_complete:
                raise RuntimeError(
                    f"seed scan {scan_id} finished with unexpected state "
                    f"status={status!r}, complete={complete!r}, error={error!r}"
                )
            return
        handled = run_worker_once(session_factory, dsn, SEED_WORKER_SETTINGS)
        if handled not in {None, scan_id}:
            raise RuntimeError(f"seed scan {scan_id} observed worker handling unexpected scan {handled!r}")
        if handled is None:
            time.sleep(0.1)

    state = _scan_state(session_factory, scan_id)
    observed = "missing" if state is None else f"status={state[0]!r}, complete={state[1]!r}, error={state[2]!r}"
    raise RuntimeError(f"seed scan {scan_id} deadline expired; observed state {observed}")


def _set_baseline(session_factory: sessionmaker[Session], repository_id: str, scan_id: str) -> None:
    with session_factory() as session:
        repository = session.get(RepositoryRow, repository_id)
        if repository is None:
            raise RuntimeError(f"seed repository for baseline scan {scan_id} disappeared")
        repository.baseline_scan_id = scan_id
        session.commit()


def _alter_demo_dag(workspace: DemoWorkspace) -> None:
    (workspace.root / DEMO_DAG_PATH).write_text(VIOLATING_DAG, encoding="utf-8")


def _queue_suppressions(session_factory: sessionmaker[Session], probe_scan_id: str) -> tuple[str, str]:
    """Create suppressions from two fingerprints observed in the probe report."""
    with session_factory() as session:
        probe = session.get(ScanRow, probe_scan_id)
        if probe is None or probe.report_json is None:
            raise RuntimeError(f"probe scan {probe_scan_id} has no persisted report")
        report = ScanReport.model_validate(probe.report_json)
        failed = [finding for finding in report.findings if finding.status is FindingStatus.FAIL]
        active_finding = next((finding for finding in failed if finding.policy_id == "AIR-DET-001"), None)
        expired_finding = next((finding for finding in failed if finding.policy_id == "AIR-DET-002"), None)
        if active_finding is None or expired_finding is None:
            observed = [(finding.policy_id, finding.status.value) for finding in report.findings]
            raise RuntimeError(f"probe scan {probe_scan_id} did not produce both expected findings: {observed!r}")

        now = utcnow()
        active_id = new_suppression_id()
        expired_id = new_suppression_id()
        session.add_all(
            [
                SuppressionRow(
                    id=active_id,
                    policy_id=active_finding.policy_id,
                    fingerprint=active_finding.fingerprint,
                    reason="Owner remediation is scheduled for the demo DAG",
                    owner="demo-platform",
                    created_at=now,
                    expires_at=now + timedelta(days=30),
                    source="platform",
                ),
                SuppressionRow(
                    id=expired_id,
                    policy_id=expired_finding.policy_id,
                    fingerprint=expired_finding.fingerprint,
                    reason="Historic tag waiver retained for inventory state",
                    owner="demo-platform",
                    created_at=now - timedelta(days=60),
                    expires_at=now - timedelta(days=30),
                    source="platform",
                ),
            ]
        )
        session.commit()
        return active_id, expired_id


def _validate_current_scan(session_factory: sessionmaker[Session], scan_id: str) -> None:
    with session_factory() as session:
        scan = session.get(ScanRow, scan_id)
        if scan is None or scan.report_json is None:
            raise RuntimeError(f"current scan {scan_id} has no persisted report")
        report = ScanReport.model_validate(scan.report_json)
        gate = report.gate_result
        if gate is None or gate.passed:
            raise RuntimeError(f"current scan {scan_id} did not record a failed gate: {gate!r}")
        if not any(finding.suppressed for finding in report.findings):
            raise RuntimeError(f"current scan {scan_id} did not record a suppressed finding")
        if not any(finding.status is FindingStatus.FAIL and not finding.suppressed for finding in report.findings):
            raise RuntimeError(f"current scan {scan_id} did not retain an unsuppressed blocking finding")


def seed_demo_scenario(workspace: DemoWorkspace) -> DemoScenario:
    """Seed baseline, probe, suppression, and current reports through the worker."""
    session_factory = initialize_session_factory(workspace.dsn)
    ids = _queue_repositories(session_factory, workspace)

    _complete_scan(
        session_factory,
        workspace.dsn,
        ids["baseline_scan"],
        expected_status="succeeded",
        expected_complete=True,
    )
    _set_baseline(session_factory, ids["repository"], ids["baseline_scan"])

    _alter_demo_dag(workspace)
    with session_factory() as session:
        probe_scan_id = _queue_scan(session, ids["repository"])
    ids["probe_scan"] = probe_scan_id
    _complete_scan(
        session_factory,
        workspace.dsn,
        probe_scan_id,
        expected_status="succeeded",
        expected_complete=True,
    )

    active_suppression_id, expired_suppression_id = _queue_suppressions(session_factory, probe_scan_id)
    ids["active_suppression"] = active_suppression_id
    ids["expired_suppression"] = expired_suppression_id

    with session_factory() as session:
        current_scan_id = _queue_scan(session, ids["repository"])
    ids["current_scan"] = current_scan_id
    _complete_scan(
        session_factory,
        workspace.dsn,
        current_scan_id,
        expected_status="succeeded",
        expected_complete=True,
    )
    _validate_current_scan(session_factory, current_scan_id)

    with session_factory() as session:
        broken_scan_id = _queue_scan(session, ids["broken_repository"])
    ids["broken_scan"] = broken_scan_id
    _complete_scan(
        session_factory,
        workspace.dsn,
        broken_scan_id,
        expected_status="failed",
        expected_complete=False,
    )

    return DemoScenario(ids=MappingProxyType(dict(ids)))


def start_demo_worker(workspace: DemoWorkspace) -> threading.Thread:
    """Start the normal asynchronous worker for scans after seeding."""
    worker = threading.Thread(
        target=run_worker,
        args=(
            create_session_factory(workspace.dsn),
            workspace.dsn,
            WorkerSettings(
                poll_seconds=0.2,
                idle_seconds=600,
                timeout_seconds=120,
                max_attempts=2,
                retention_keep=50,
            ),
        ),
        name="conformdag-demo-worker",
        daemon=True,
    )
    worker.start()
    return worker
