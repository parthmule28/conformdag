"""Platform persistence: repository, scan, finding, suppression, and job rows."""

from __future__ import annotations

import fcntl
import hashlib
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from sqlalchemy import (
    JSON,
    CursorResult,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    create_engine,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

JSONVariant = JSON().with_variant(JSONB(), "postgresql")
_MIGRATION_THREAD_LOCK = threading.Lock()


class Base(DeclarativeBase):
    """Declarative base for every platform table."""


def utcnow() -> datetime:
    """Return the current UTC timestamp for database defaults."""
    return datetime.now(UTC)


def new_id() -> str:
    """Return a new opaque database row identifier."""
    return uuid.uuid4().hex


def stale_running_cutoff(idle_seconds: int) -> datetime:
    """Return the cutoff before which a running scan is considered abandoned."""
    return datetime.now(UTC) - timedelta(seconds=idle_seconds)


class RepositoryRow(Base):
    """One registered DAG repository on local disk."""

    __tablename__ = "repos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    path: Mapped[str] = mapped_column(String(1024))
    policy_pack: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    airflow_profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    baseline_scan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanRow(Base):
    """One scan execution and its canonical report artifact."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    trigger: Mapped[str] = mapped_column(String(32), default="dashboard")
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    complete: Mapped[bool | None] = mapped_column(nullable=True)
    report_json: Mapped[dict[str, object] | None] = mapped_column(JSONVariant, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class FindingRow(Base):
    """Normalized finding ingested from one scan's canonical report."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"))
    repository_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    policy_id: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    start_line: Mapped[int | None] = mapped_column(nullable=True)
    end_line: Mapped[int | None] = mapped_column(nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_json: Mapped[dict[str, object] | None] = mapped_column(JSONVariant, nullable=True)
    suppressed: Mapped[bool] = mapped_column(default=False)


Index("ix_findings_repo_policy", FindingRow.repository_id, FindingRow.policy_id)
Index("ix_scans_repo_created", ScanRow.repository_id, ScanRow.created_at)
Index("ix_scans_status_created", ScanRow.status, ScanRow.created_at)
Index("ix_scans_status_claimed", ScanRow.status, ScanRow.claimed_at)


class SuppressionRow(Base):
    """An operational, audited suppression layer owned by the platform."""

    __tablename__ = "suppressions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(16), default="platform")


Index(
    "uq_suppressions_policy_fingerprint",
    SuppressionRow.policy_id,
    SuppressionRow.fingerprint,
    unique=True,
)


class PlatformError(RuntimeError):
    """Raised when the platform persistence layer cannot be used."""


@contextmanager
def _migration_lock(url: str) -> Iterator[None]:
    """Serialize first-boot migration attempts across threads and processes."""
    lock_name = hashlib.sha256(url.encode("utf-8")).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"conformdag-migrations-{lock_name}.lock"
    with _MIGRATION_THREAD_LOCK, lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def run_migrations(url: str) -> None:
    """Bring the platform schema to the latest migration revision."""
    from alembic import command
    from alembic.config import Config

    ini_path = Path(__file__).resolve().parent / "alembic.ini"
    alembic_config = Config(ini_path)
    alembic_config.set_main_option("script_location", str(ini_path.parent / "migrations"))
    alembic_config.set_main_option("sqlalchemy.url", url)
    with _migration_lock(url):
        command.upgrade(alembic_config, "head")


def create_session_factory(url: str) -> sessionmaker[Session]:
    """Create a session factory bound to the platform database URL.

    Binding only: no schema work happens here. Runner subprocesses share this
    factory so they can never race the startup migration; migrations are a
    single startup responsibility owned by ``initialize_session_factory``.
    """
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def initialize_session_factory(url: str) -> sessionmaker[Session]:
    """Run pending migrations once at startup, then bind a session factory.

    Only long-lived platform processes (``serve``, ``worker``, and the CLI
    platform commands) call this; the schema is created exclusively through
    Alembic migrations, never through ``Base.metadata.create_all()``.
    """
    run_migrations(url)
    return create_session_factory(url)


def next_scan_id() -> str:
    """Return a new opaque scan identifier."""
    return new_id()


def new_suppression_id() -> str:
    """Return a new opaque suppression identifier."""
    return new_id()


def claim_queued_scan(session: Session, stale_cutoff: datetime, max_attempts: int) -> ScanRow | None:
    """Claim one queued scan, or re-claim an abandoned run within the attempt bound."""
    abandoned = (
        select(ScanRow)
        .where(
            ScanRow.status == "running",
            ScanRow.claimed_at.is_not(None),
            ScanRow.claimed_at < stale_cutoff,
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    abandoned_scan = session.scalars(abandoned).first()
    if abandoned_scan is not None:
        if abandoned_scan.attempts >= max_attempts:
            abandoned_scan.status = "failed"
            abandoned_scan.error = "abandoned by a previous worker; attempt budget exhausted"
            abandoned_scan.finished_at = utcnow()
            return None
        abandoned_scan.attempts += 1
        abandoned_scan.claimed_at = utcnow()
        return abandoned_scan
    queued = (
        select(ScanRow)
        .where(ScanRow.status == "queued")
        .order_by(ScanRow.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    queued_scan = session.scalars(queued).first()
    if queued_scan is None:
        return None
    queued_scan.status = "running"
    queued_scan.claimed_at = utcnow()
    queued_scan.attempts += 1
    return queued_scan


def transition_running_scan(
    session: Session, scan_id: str, status: str, error: str | None = None, *, requeue: bool = False
) -> bool:
    """Conditionally transition a running scan to ``status``.

    Returns True when the transition was applied. The conditional UPDATE makes
    cancellation win over any concurrent worker or runner outcome: a scan that
    was cancelled after the caller's last explicit status check is never
    overwritten, and the caller's pending changes are rolled back instead.
    Requeueing clears the claim timestamp so the scan re-enters the queue;
    terminal transitions stamp ``finished_at``.
    """
    statement = (
        update(ScanRow).where(ScanRow.id == scan_id, ScanRow.status == "running").values(status=status, error=error)
    )
    statement = (
        statement.values(claimed_at=None) if requeue else statement.values(claimed_at=None, finished_at=utcnow())
    )
    applied = cast("CursorResult[Any]", session.execute(statement))
    if applied.rowcount:
        session.commit()
        return True
    session.rollback()
    return False


def transition_scan_to_cancelled(session: Session, scan_id: str) -> bool:
    """Atomically cancel a queued or running scan, allowing one winner."""
    statement = (
        update(ScanRow)
        .where(ScanRow.id == scan_id, ScanRow.status.in_(("queued", "running")))
        .values(status="cancelled", claimed_at=None, finished_at=utcnow())
    )
    applied = cast("CursorResult[Any]", session.execute(statement))
    if applied.rowcount:
        session.commit()
        return True
    session.rollback()
    return False


def heartbeat_running_scan(session: Session, scan_id: str) -> bool:
    """Refresh a running scan claim only while its status remains running."""
    statement = update(ScanRow).where(ScanRow.id == scan_id, ScanRow.status == "running").values(claimed_at=utcnow())
    applied = cast("CursorResult[Any]", session.execute(statement))
    if applied.rowcount:
        session.commit()
        return True
    session.rollback()
    return False


def eligible_baseline(session: Session, repository_id: str, scan_id: str) -> ScanRow | None:
    """Return the scan row when it may serve as one repository's baseline.

    A baseline must belong to the same repository and be a succeeded, complete
    scan; queued, running, failed, cancelled, and incomplete scans are never
    eligible.
    """
    scan = session.get(ScanRow, scan_id)
    if scan is None or scan.repository_id != repository_id:
        return None
    if scan.status != "succeeded" or scan.complete is not True:
        return None
    return scan


def count_scans(session: Session, repository_id: str) -> int:
    """Return the number of scans recorded for one repository."""
    return int(
        session.scalar(select(func.count()).select_from(ScanRow).where(ScanRow.repository_id == repository_id)) or 0
    )


def retention_target_scan_ids(session: Session, repository_id: str, keep: int) -> list[str]:
    """Return scan ids beyond the newest ``keep`` for one repository.

    At least the single newest artifact is always protected, so a misconfigured
    ``keep`` below one can never prune the latest report.
    """
    newest = (
        select(ScanRow.id)
        .where(ScanRow.repository_id == repository_id)
        .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
        .limit(max(keep, 1))
        .subquery()
    )
    older = (
        select(ScanRow.id)
        .where(
            ScanRow.repository_id == repository_id,
            ScanRow.id.not_in(select(newest)),
        )
        .order_by(ScanRow.created_at.asc(), ScanRow.id.asc())
    )
    return list(session.scalars(older))


def prune_scan_artifact(session: Session, scan_id: str) -> None:
    """Clear the report artifact of one scan, keeping the row and its findings.

    Retention bounds artifact storage while normalized findings survive for
    trends, per design decision: findings forever, artifacts bounded.
    """
    scan = session.get(ScanRow, scan_id)
    if scan is not None:
        scan.report_json = None
