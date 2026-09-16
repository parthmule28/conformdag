"""Durable platform worker: claims scans, executes runners, and prunes artifacts."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from conformdag.platform.db import (
    ScanRow,
    claim_queued_scan,
    prune_scan_artifact,
    retention_target_scan_ids,
    stale_running_cutoff,
    utcnow,
)
from conformdag.platform.logging import install_json_logging

DEFAULT_POLL_SECONDS = 2.0
DEFAULT_IDLE_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_MAX_ATTEMPTS = 3

_shutdown_requested = threading.Event()


def install_signal_handlers() -> None:
    """Request a graceful shutdown on SIGTERM/SIGINT (main thread only)."""
    signal.signal(signal.SIGTERM, lambda signum, frame: _shutdown_requested.set())
    signal.signal(signal.SIGINT, lambda signum, frame: _shutdown_requested.set())


def request_shutdown() -> None:
    """Ask the worker loop to stop after the in-flight scan completes."""
    _shutdown_requested.set()


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
    if process.stderr:
        sys.stderr.write(process.stderr)
        sys.stderr.flush()
    if process.returncode != 0:
        return f"runner exited with code {process.returncode}: {process.stderr.strip()}"
    return ""


def run_worker_once(session_factory: sessionmaker[Session], dsn: str, settings: WorkerSettings) -> str | None:
    """Claim and execute at most one scan; return the handled scan id or None."""
    logger = logging.getLogger("conformdag.worker")
    with session_factory() as session:
        scan = claim_queued_scan(session, stale_running_cutoff(settings.idle_seconds), settings.max_attempts)
        if scan is None:
            return None
        scan_id = scan.id
        session.commit()
    logger.info("scan_claimed", extra={"scan_id": scan_id})

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
    finished_extra: dict[str, object] = {"scan_id": scan_id}
    if outcome_error:
        finished_extra["error"] = outcome_error
    logger.info("scan_finished", extra=finished_extra)
    return scan_id


def _apply_retention(session: Session, repository_id: str, settings: WorkerSettings) -> None:
    for scan_id in retention_target_scan_ids(session, repository_id, settings.retention_keep):
        prune_scan_artifact(session, scan_id)
    session.commit()


def run_worker(session_factory: sessionmaker[Session], dsn: str, settings: WorkerSettings) -> None:
    """Run the durable worker loop until interrupted or shut down gracefully."""
    install_json_logging()
    logger = logging.getLogger("conformdag.worker")
    with suppress(ValueError):
        install_signal_handlers()
    while not _shutdown_requested.is_set():
        try:
            handled = run_worker_once(session_factory, dsn, settings)
            if handled is None and not _shutdown_requested.is_set():
                time.sleep(settings.poll_seconds)
        except KeyboardInterrupt:
            return
    logger.info("worker drained the in-flight scan and shut down", extra={"event": "worker_stopped"})
