"""platform concurrency indexes and suppression identity

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_scans_status_created", "scans", ["status", "created_at"])
    op.create_index("ix_scans_status_claimed", "scans", ["status", "claimed_at"])
    connection = op.get_bind()
    # Keep this cleanup immediately before the unique-index creation.  It is
    # intentionally safe for retries from pre-0004 databases: the oldest row
    # for each identity survives, while a database already recorded at 0004
    # cannot contain duplicates under the index and will not rerun this code.
    rows = list(
        connection.execute(
            sa.text("SELECT id, policy_id, fingerprint FROM suppressions ORDER BY created_at ASC, id ASC")
        )
    )
    seen: set[tuple[str, str]] = set()
    for row in rows:
        identity = (str(row[1]), str(row[2]))
        if identity in seen:
            connection.execute(sa.text("DELETE FROM suppressions WHERE id = :id"), {"id": row[0]})
        else:
            seen.add(identity)
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
