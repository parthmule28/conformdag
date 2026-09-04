"""platform baseline: repos, scans, findings, suppressions

Revision ID: 0001
Revises:
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON_VARIANT = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("policy_pack", sa.String(1024), nullable=True),
        sa.Column("airflow_profile", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "scans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(64),
            sa.ForeignKey("repos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.String(32), nullable=False, server_default="dashboard"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_fingerprint", sa.String(64), nullable=True),
        sa.Column("complete", sa.Boolean, nullable=True),
        sa.Column("report_json", _JSON_VARIANT, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "scan_id",
            sa.String(64),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.String(64),
            sa.ForeignKey("repos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=True),
        sa.Column("start_line", sa.Integer, nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("remediation", sa.Text, nullable=True),
        sa.Column("fix_json", _JSON_VARIANT, nullable=True),
        sa.Column("suppressed", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_findings_repo_policy", "findings", ["repository_id", "policy_id"])
    op.create_index("ix_scans_repo_created", "scans", ["repository_id", "created_at"])
    op.create_table(
        "suppressions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="platform"),
    )


def downgrade() -> None:
    op.drop_table("suppressions")
    op.drop_index("ix_scans_repo_created", table_name="scans")
    op.drop_index("ix_findings_repo_policy", table_name="findings")
    op.drop_table("findings")
    op.drop_table("scans")
    op.drop_table("repos")
