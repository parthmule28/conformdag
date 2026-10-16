"""Compatibility tests for consumers of finding fingerprint identity."""

from datetime import UTC, datetime

import pytest

from conformdag.reporting import apply_suppressions
from reporting.fixtures import fixed_report, fixed_suppression


@pytest.mark.parametrize(
    "mismatch",
    [
        {"policy_id": "OTHER-POLICY"},
        {"fingerprint": "other-fingerprint"},
    ],
    ids=("policy-id", "fingerprint"),
)
def test_suppression_requires_exact_policy_and_fingerprint_without_redefining_identity(
    mismatch: dict[str, str],
) -> None:
    finding = next(item for item in fixed_report().findings if item.fingerprint == "fp-b-tie")
    suppression = fixed_suppression().model_copy(
        update={"policy_id": finding.policy_id, "fingerprint": finding.fingerprint, **mismatch}
    )

    findings, issues = apply_suppressions(
        [finding],
        [suppression],
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert findings[0].fingerprint == finding.fingerprint
    assert findings[0].suppressed is False
    assert [issue.code for issue in issues] == ["SUPPRESSION_UNMATCHED"]
