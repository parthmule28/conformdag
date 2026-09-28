"""Typed scan lifecycle and trigger values for the platform."""

from enum import StrEnum


class ScanStatus(StrEnum):
    """Lifecycle status persisted for a platform scan."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanTrigger(StrEnum):
    """Existing source that requested a platform scan."""

    DASHBOARD = "dashboard"
    DEMO = "demo"


ACTIVE_SCAN_STATUSES: frozenset[ScanStatus] = frozenset({ScanStatus.QUEUED, ScanStatus.RUNNING})
TERMINAL_SCAN_STATUSES: frozenset[ScanStatus] = frozenset(
    {ScanStatus.SUCCEEDED, ScanStatus.FAILED, ScanStatus.CANCELLED}
)
