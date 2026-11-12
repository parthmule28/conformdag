"""Platform persistence ORM models and identifiers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Declarative base for every platform table."""


def utcnow() -> datetime:
    """Return the current UTC timestamp for database defaults."""
    return datetime.now(UTC)


def new_id() -> str:
    """Return a new opaque database row identifier."""
    return uuid.uuid4().hex


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


def next_scan_id() -> str:
    """Return a new opaque scan identifier."""
    return new_id()


def new_suppression_id() -> str:
    """Return a new opaque suppression identifier."""
    return new_id()
