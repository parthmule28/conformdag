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

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from conformdag.platform.db import (
    ScanRow,
    claim_queued_scan,
    prune_scan_artifact,
    retention_target_scan_ids,
    stale_running_cutoff,
    transition_running_scan,
)
from conformdag.platform.logging import install_json_logging

DEFAULT_POLL_SECONDS = 2.0
DEFAULT_IDLE_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETENTION_KEEP = 50

_CANCEL_GRACE_SECONDS = 5.0
_LOST_RUNNER_ERROR = "worker lost the runner before completion"

_shutdown_requested = threading.Event()


def install_signal_handlers() -> None:
    """Request a graceful shutdown on SIGTERM/SIGINT (main thread only)."""
    signal.signal(signal.SIGTERM, lambda signum, frame: _shutdown_requested.set())
    signal.signal(signal.SIGINT, lambda signum, frame: _shutdown_requested.set())


def request_shutdown() -> None:
    """Ask the worker loop to stop after the in-flight scan completes."""
    _shutdown_requested.set()


@dataclass(frozen=True)
class RunnerOutcome:
    """Terminal result of one runner subprocess execution."""

    error: str = ""
    retryable: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class WorkerSettings:
    """Operator-tunable worker loop parameters."""

    poll_seconds: float = DEFAULT_POLL_SECONDS
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retention_keep: int = DEFAULT_RETENTION_KEEP

    @classmethod
    def from_environment(cls) -> WorkerSettings:
        """Resolve worker settings from environment variables with defaults."""
        settings = cls(
            poll_seconds=float(os.environ.get("CONFORMDAG_WORKER_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))),
            idle_seconds=int(os.environ.get("CONFORMDAG_WORKER_IDLE_SECONDS", str(DEFAULT_IDLE_SECONDS))),
            timeout_seconds=int(os.environ.get("CONFORMDAG_WORKER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
            max_attempts=int(os.environ.get("CONFORMDAG_WORKER_MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS))),
            retention_keep=int(os.environ.get("CONFORMDAG_PLATFORM_RETENTION_KEEP", str(DEFAULT_RETENTION_KEEP))),
        )
        if settings.retention_keep < 1:
            raise ValueError("CONFORMDAG_PLATFORM_RETENTION_KEEP must keep at least one scan artifact")
        return settings


def _scan_cancelled(session_factory: sessionmaker[Session], scan_id: str) -> bool:
    """Return whether the scan was cancelled, read from a fresh session."""
    with session_factory() as session:
        return session.scalar(select(ScanRow.status).where(ScanRow.id == scan_id)) == "cancelled"


def _terminate_child(process: subprocess.Popen[str]) -> None:
    """Terminate the runner child, escalating to kill after a short grace period."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_CANCEL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
    process.wait()


def _relay_stderr(stderr: str) -> None:
    """Relay captured runner stderr to the worker's stderr."""
    if stderr:
        sys.stderr.write(stderr)
        sys.stderr.flush()


def execute_claimed_scan(
    session_factory: sessionmaker[Session], dsn: str, scan_id: str, settings: WorkerSettings
) -> RunnerOutcome:
    """Execute one claimed scan in an isolated subprocess and return its outcome.

    The configured worker timeout remains the hard upper bound. Between bounded
    waits the scan status is queried with a fresh session; a cancelled scan
    terminates the child (killing it after a grace period) so a later runner
    result can never overwrite the cancellation.
    """
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "conformdag.platform.runner", "--scan-id", scan_id, "--dsn", dsn],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return RunnerOutcome(error=f"worker failed to launch the runner: {exc}", retryable=True)
    deadline = time.monotonic() + settings.timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_child(process)
            stderr = process.communicate()[1]
            _relay_stderr(stderr)
            return RunnerOutcome(error=f"scan exceeded the {settings.timeout_seconds}s worker timeout", retryable=True)
        try:
            stderr = process.communicate(timeout=min(settings.poll_seconds, remaining))[1]
        except subprocess.TimeoutExpired:
            if _scan_cancelled(session_factory, scan_id):
                _terminate_child(process)
                stderr = process.communicate()[1]
                _relay_stderr(stderr)
                return RunnerOutcome(cancelled=True)
            continue
        break
    _relay_stderr(stderr)
    if process.returncode != 0:
        return RunnerOutcome(
            error=f"runner exited with code {process.returncode}: {stderr.strip()}",
            retryable=process.returncode < 0,
        )
    return RunnerOutcome()


def run_worker_once(session_factory: sessionmaker[Session], dsn: str, settings: WorkerSettings) -> str | None:
    """Claim and execute at most one scan; return the handled scan id or None."""
    logger = logging.getLogger("conformdag.worker")
    with session_factory() as session:
        scan = claim_queued_scan(session, stale_running_cutoff(settings.idle_seconds), settings.max_attempts)
        if scan is None:
            session.commit()
            return None
        scan_id = scan.id
        session.commit()
    logger.info("scan_claimed", extra={"scan_id": scan_id})

    outcome = execute_claimed_scan(session_factory, dsn, scan_id, settings)

    with session_factory() as session:
        final = session.get(ScanRow, scan_id)
        if final is not None:
            if final.status == "running" and not outcome.cancelled:
                if outcome.retryable and final.attempts < settings.max_attempts:
                    transition_running_scan(session, scan_id, "queued", outcome.error, requeue=True)
                else:
                    transition_running_scan(session, scan_id, "failed", outcome.error or _LOST_RUNNER_ERROR)
                    _apply_retention(session, final.repository_id, settings)
            else:
                _apply_retention(session, final.repository_id, settings)
    finished_extra: dict[str, object] = {"scan_id": scan_id}
    if outcome.error:
        finished_extra["error"] = outcome.error
    if outcome.cancelled:
        finished_extra["cancelled"] = True
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
