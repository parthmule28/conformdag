"""Durable platform worker: claims scans, executes runners, and prunes artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from conformdag.platform.db import (
    ScanRow,
    claim_queued_scan,
    prune_scan,
    retention_target_scan_ids,
    stale_running_cutoff,
    utcnow,
)

DEFAULT_POLL_SECONDS = 2.0
DEFAULT_IDLE_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class WorkerSettings:
    """Operator-tunable worker loop parameters."""

    poll_seconds: float = DEFAULT_POLL_SECONDS
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retention_keep: int = 50

    @classmethod
    def from_environment(cls) -> WorkerSettings:
        """Resolve worker settings from environment variables with defaults."""
        return cls(
            poll_seconds=float(os.environ.get("CONFORMDAG_WORKER_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))),
            idle_seconds=int(os.environ.get("CONFORMDAG_WORKER_IDLE_SECONDS", str(DEFAULT_IDLE_SECONDS))),
            timeout_seconds=int(os.environ.get("CONFORMDAG_WORKER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
            max_attempts=int(os.environ.get("CONFORMDAG_WORKER_MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS))),
            retention_keep=int(os.environ.get("CONFORMDAG_PLATFORM_RETENTION_KEEP", "50")),
        )


def execute_claimed_scan(dsn: str, scan_id: str, settings: WorkerSettings) -> str:
    """Execute one claimed scan in an isolated subprocess and return an error or ''."""
    try:
        process = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                "-m",
                "conformdag.platform.runner",
                "--scan-id",
                scan_id,
                "--dsn",
                dsn,
            ],
            capture_output=True,
            text=True,
            timeout=settings.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"scan exceeded the {settings.timeout_seconds}s worker timeout"
    if process.returncode != 0:
        return f"runner exited with code {process.returncode}: {process.stderr.strip()}"
    return ""


def run_worker_once(session_factory: sessionmaker[Session], dsn: str, settings: WorkerSettings) -> str | None:
    """Claim and execute at most one scan; return the handled scan id or None."""
    with session_factory() as session:
        scan = claim_queued_scan(session, stale_running_cutoff(settings.idle_seconds), settings.max_attempts)
        if scan is None:
            return None
        scan_id = scan.id
        session.commit()

    outcome_error = execute_claimed_scan(dsn, scan_id, settings)

    with session_factory() as session:
        final = session.get(ScanRow, scan_id)
        if final is not None and final.status == "running":
            final.status = "failed"
            final.error = outcome_error or "worker lost the runner before completion"
            final.finished_at = utcnow()
            session.commit()
            _apply_retention(session, final.repository_id, settings)
        elif final is not None:
            _apply_retention(session, final.repository_id, settings)
    return scan_id


def _apply_retention(session: Session, repository_id: str, settings: WorkerSettings) -> None:
    targets = retention_target_scan_ids(session, repository_id, settings.retention_keep)
    for scan_id in targets:
        prune_scan(session, scan_id)
    if targets:
        session.commit()


def run_worker(session_factory: sessionmaker[Session], dsn: str, settings: WorkerSettings) -> None:
    """Run the durable worker loop until interrupted."""
    while True:
        try:
            handled = run_worker_once(session_factory, dsn, settings)
            if handled is None:
                time.sleep(settings.poll_seconds)
        except KeyboardInterrupt:
            return
