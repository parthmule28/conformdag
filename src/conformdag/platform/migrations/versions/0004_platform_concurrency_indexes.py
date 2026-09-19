"""platform concurrency indexes and suppression identity

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_scans_status_created", "scans", ["status", "created_at"])
    op.create_index("ix_scans_status_claimed", "scans", ["status", "claimed_at"])
    op.create_index(
        "uq_suppressions_policy_fingerprint",
        "suppressions",
        ["policy_id", "fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_suppressions_policy_fingerprint", table_name="suppressions")
    op.drop_index("ix_scans_status_claimed", table_name="scans")
    op.drop_index("ix_scans_status_created", table_name="scans")
