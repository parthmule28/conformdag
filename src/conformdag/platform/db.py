"""Compatibility facade for the C24 platform-persistence ownership boundary.

Implementations now live in ``conformdag.platform.persistence``. Keep these
legacy imports available for at least one compatibility cycle.
"""

from __future__ import annotations

__all__ = [
    "_migration_lock",
    "eligible_baseline",
    "PlatformError",
    "create_session_factory",
    "initialize_session_factory",
    "migration_lock_path",
    "run_migrations",
    "Base",
    "FindingRow",
    "JSONVariant",
    "RepositoryRow",
    "ScanRow",
    "SuppressionRow",
    "new_id",
    "new_suppression_id",
    "next_scan_id",
    "utcnow",
    "count_scans",
    "prune_scan_artifact",
    "retention_target_scan_ids",
    "claim_queued_scan",
    "heartbeat_running_scan",
    "stale_running_cutoff",
    "transition_running_scan",
    "transition_scan_to_cancelled",
]

from conformdag.platform.persistence.baselines import (
    eligible_baseline as eligible_baseline,
)
from conformdag.platform.persistence.migrations import (
    PlatformError as PlatformError,
)
from conformdag.platform.persistence.migrations import (
    create_session_factory as create_session_factory,
)
from conformdag.platform.persistence.migrations import (
    initialize_session_factory as initialize_session_factory,
)
from conformdag.platform.persistence.migrations import (
    migration_lock as _migration_lock,
)
from conformdag.platform.persistence.migrations import (
    migration_lock_path as migration_lock_path,
)
from conformdag.platform.persistence.migrations import (
    run_migrations as run_migrations,
)
from conformdag.platform.persistence.models import (
    Base as Base,
)
from conformdag.platform.persistence.models import (
    FindingRow as FindingRow,
)
from conformdag.platform.persistence.models import (
    JSONVariant as JSONVariant,
)
from conformdag.platform.persistence.models import (
    RepositoryRow as RepositoryRow,
)
from conformdag.platform.persistence.models import (
    ScanRow as ScanRow,
)
from conformdag.platform.persistence.models import (
    SuppressionRow as SuppressionRow,
)
from conformdag.platform.persistence.models import (
    new_id as new_id,
)
from conformdag.platform.persistence.models import (
    new_suppression_id as new_suppression_id,
)
from conformdag.platform.persistence.models import (
    next_scan_id as next_scan_id,
)
from conformdag.platform.persistence.models import (
    utcnow as utcnow,
)
from conformdag.platform.persistence.retention import (
    count_scans as count_scans,
)
from conformdag.platform.persistence.retention import (
    prune_scan_artifact as prune_scan_artifact,
)
from conformdag.platform.persistence.retention import (
    retention_target_scan_ids as retention_target_scan_ids,
)
from conformdag.platform.persistence.scans import (
    claim_queued_scan as claim_queued_scan,
)
from conformdag.platform.persistence.scans import (
    heartbeat_running_scan as heartbeat_running_scan,
)
from conformdag.platform.persistence.scans import (
    stale_running_cutoff as stale_running_cutoff,
)
from conformdag.platform.persistence.scans import (
    transition_running_scan as transition_running_scan,
)
from conformdag.platform.persistence.scans import (
    transition_scan_to_cancelled as transition_scan_to_cancelled,
)
