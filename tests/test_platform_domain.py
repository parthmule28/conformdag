from conformdag.platform.domain import ACTIVE_SCAN_STATUSES, TERMINAL_SCAN_STATUSES, ScanStatus, ScanTrigger


def test_scan_status_values_are_the_persisted_spellings() -> None:
    assert [status.value for status in ScanStatus] == ["queued", "running", "succeeded", "failed", "cancelled"]


def test_scan_trigger_values_include_only_existing_sources() -> None:
    assert [trigger.value for trigger in ScanTrigger] == ["dashboard", "demo"]


def test_active_and_terminal_status_groups_are_typed() -> None:
    assert frozenset({ScanStatus.QUEUED, ScanStatus.RUNNING}) == ACTIVE_SCAN_STATUSES
    assert frozenset({ScanStatus.SUCCEEDED, ScanStatus.FAILED, ScanStatus.CANCELLED}) == TERMINAL_SCAN_STATUSES
