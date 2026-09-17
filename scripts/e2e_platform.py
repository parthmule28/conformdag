"""Disposable ConformDAG platform for the Playwright browser journeys.

Boots the production platform stack against throwaway state only:

- a temporary directory holds the workspace file, the local policy pack and
  standards document, two seeded repositories, and the SQLite database;
- the schema is created exclusively through ``initialize_session_factory()``
  (Alembic migrations — never ``Base.metadata.create_all()``);
- the existing worker loop runs in a daemon thread with bounded polling and
  executes the seeded scans through the production runner and scanner;
- ``create_app()`` serves the real ``/api/v1`` routes through Uvicorn; and
- Uvicorn only starts accepting connections after the seed has finished, so a
  healthy health check implies the journeys' data is present.

The process never touches files outside its temporary directory and cleans up
on shutdown.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

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

HEALTHY_DAG = '''"""One conforming DAG that misses only the owner tag."""

from datetime import timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from pendulum import datetime

with DAG(
    dag_id="e2e_healthy_dag",
    owner="platform",
    tags=["domain:data"],
    start_date=datetime(2026, 1, 1, tz="UTC"),
    default_args={
        "execution_timeout": timedelta(hours=1),
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
) as dag:
    EmptyOperator(task_id="start")
'''

BROKEN_DAG = '''"""One broken DAG file: it never parses, so its scan stays incomplete."""

def broken(:
    this is not valid python
'''

HEALTHY_REPOSITORY_NAME = "e2e-healthy"
BROKEN_REPOSITORY_NAME = "e2e-broken"
TERMINAL_SCAN_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
SEED_DEADLINE_SECONDS = 120.0


def _provenance(section: str, source_hash: str) -> str:
    return f'{{document: standards/dag-authoring.md, section: "{section}", version: "1", content_hash: {source_hash}}}'


def _write_pack(root: Path) -> Path:
    """Write the local policy pack, computing provenance from the standards document."""
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
    configuration: {{kind: required-owner, allowed_values: [platform, data-engineering, analytics]}}
  - id: AIR-DET-002
    title: DAG tags use approved keys and values
    version: 1.0.0
    status: ACTIVE
    severity: medium
    ownership: {{owner: platform}}
    source: {_provenance("Ownership and metadata", source_hash)}
    invariant: DAG tags use the policy-defined key and value vocabulary.
    enforcement: {{type: deterministic, deterministic_checks: [tags]}}
    configuration: {{kind: required-tags, required_keys: [domain, owner], allowed_values: {{domain: [data, analytics, platform]}}}}
quality_gates:
  - id: baseline-gate
    rules:
      - type: max-findings
        count: 25
"""
    pack_path = root / "packs" / "conformdag-e2e-pack.yaml"
    pack_path.parent.mkdir(parents=True)
    pack_path.write_text(pack_yaml, encoding="utf-8")
    return pack_path


def _build_workspace(root: Path) -> tuple[Path, Path]:
    """Create the workspace file, pack, standards document, and both repositories."""
    standards = root / "standards" / "dag-authoring.md"
    standards.parent.mkdir(parents=True)
    standards.write_text(STANDARDS_DOCUMENT, encoding="utf-8")

    pack_path = _write_pack(root)

    healthy = root / HEALTHY_REPOSITORY_NAME
    (healthy / "dags").mkdir(parents=True)
    (healthy / "dags" / "healthy_dag.py").write_text(HEALTHY_DAG, encoding="utf-8")

    broken = root / BROKEN_REPOSITORY_NAME
    (broken / "dags").mkdir(parents=True)
    (broken / "dags" / "broken_dag.py").write_text(BROKEN_DAG, encoding="utf-8")

    workspace_yaml = f"""schema_version: "1"
repositories:
  - name: {HEALTHY_REPOSITORY_NAME}
    path: {healthy}
    policy_pack: {pack_path}
  - name: {BROKEN_REPOSITORY_NAME}
    path: {broken}
    policy_pack: {pack_path}
policy_packs:
  - name: conformdag-e2e-pack
    path: {pack_path}
"""
    workspace_path = root / "conformdag-workspace.yaml"
    workspace_path.write_text(workspace_yaml, encoding="utf-8")
    return workspace_path, pack_path


def _queue_seed_rows(session_factory: sessionmaker[Session], root: Path, pack_path: Path) -> dict[str, str]:
    """Insert the repository rows, two queued scans, and the expired waiver."""
    from conformdag.platform.db import RepositoryRow, ScanRow, SuppressionRow, new_id, utcnow

    healthy = RepositoryRow(
        id=new_id(),
        name=HEALTHY_REPOSITORY_NAME,
        path=str(root / HEALTHY_REPOSITORY_NAME),
        policy_pack=str(pack_path),
    )
    broken = RepositoryRow(
        id=new_id(),
        name=BROKEN_REPOSITORY_NAME,
        path=str(root / BROKEN_REPOSITORY_NAME),
        policy_pack=str(pack_path),
    )
    healthy_scan = ScanRow(id=new_id(), repository_id=healthy.id, status="queued")
    broken_scan = ScanRow(id=new_id(), repository_id=broken.id, status="queued")
    with session_factory() as session:
        session.add_all([healthy, broken, healthy_scan, broken_scan])
        session.add(
            SuppressionRow(
                id=new_id(),
                policy_id="AIR-DET-002",
                fingerprint="0" * 64,
                reason="Historic waiver kept for the expired-state journey",
                owner="e2e-seed",
                created_at=utcnow(),
                expires_at=utcnow() - timedelta(days=30),
                source="platform",
            )
        )
        session.commit()
    return {
        "healthy_repository": healthy.id,
        "broken_repository": broken.id,
        "healthy_scan": healthy_scan.id,
        "broken_scan": broken_scan.id,
    }


def _await_seed_scan(session_factory: sessionmaker[Session], scan_id: str, expect: str) -> bool:
    """Wait until one seeded scan is terminal; return whether it is complete."""
    from conformdag.platform.db import ScanRow

    deadline = time.monotonic() + SEED_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        with session_factory() as session:
            scan = session.get(ScanRow, scan_id)
            if scan is not None and scan.status in TERMINAL_SCAN_STATUSES:
                if scan.status != expect:
                    raise RuntimeError(f"seed scan {scan_id} finished {scan.status!r}, expected {expect!r}")
                return scan.complete is True
        time.sleep(0.2)
    raise RuntimeError(f"seed scan {scan_id} did not finish in time")


def _complete_seed(session_factory: sessionmaker[Session], ids: dict[str, str]) -> None:
    """Wait for both seeded scans and mark the eligible baseline."""
    from conformdag.platform.db import RepositoryRow

    healthy_complete = _await_seed_scan(session_factory, ids["healthy_scan"], "succeeded")
    if not healthy_complete:
        raise RuntimeError("seed baseline scan must be complete")
    broken_complete = _await_seed_scan(session_factory, ids["broken_scan"], "failed")
    if broken_complete:
        raise RuntimeError("seed broken scan must be incomplete")

    with session_factory() as session:
        repository = session.get(RepositoryRow, ids["healthy_repository"])
        if repository is None:
            raise RuntimeError("seed repository row disappeared")
        repository.baseline_scan_id = ids["healthy_scan"]
        session.commit()


def main() -> int:
    """Run the disposable platform until interrupted; never touch outside state."""
    parser = argparse.ArgumentParser(description="Disposable platform for browser e2e journeys")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8642)
    parser.add_argument("--token", default="secret-token")
    args = parser.parse_args()

    from conformdag.platform.app import PlatformSettings, create_app
    from conformdag.platform.db import create_session_factory, initialize_session_factory
    from conformdag.platform.worker import WorkerSettings, request_shutdown, run_worker

    with tempfile.TemporaryDirectory(prefix="conformdag-e2e-") as tmp:
        root = Path(tmp)
        workspace_path, pack_path = _build_workspace(root)
        dsn = f"sqlite:///{root / 'platform.db'}"

        # Schema ownership stays with Alembic via the production entry point.
        session_factory = initialize_session_factory(dsn)
        seed_ids = _queue_seed_rows(session_factory, root, pack_path)

        worker_settings = WorkerSettings(
            poll_seconds=0.2,
            idle_seconds=5,
            timeout_seconds=120,
            max_attempts=2,
            retention_keep=50,
        )
        worker = threading.Thread(
            target=run_worker,
            args=(create_session_factory(dsn), dsn, worker_settings),
            name="conformdag-e2e-worker",
            daemon=True,
        )
        worker.start()
        _complete_seed(session_factory, seed_ids)

        settings = PlatformSettings(dsn=dsn, admin_token=args.token, workspace=workspace_path)
        app = create_app(session_factory, settings, workspace_path=workspace_path)
        uvicorn_config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
        uvicorn_server = uvicorn.Server(uvicorn_config)
        try:
            uvicorn_server.run()
        except KeyboardInterrupt:
            pass
        finally:
            request_shutdown()
            worker.join(timeout=10.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
