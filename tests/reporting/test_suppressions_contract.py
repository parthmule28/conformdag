"""Baseline characterization tests for suppression application and diagnostics."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from conformdag.models import Finding, Suppression
from conformdag.reporting import apply_suppressions

from .fixtures import fixed_report


def _suppression(finding: Finding, *, expires_at: datetime, reason: str = "fixture suppression") -> Suppression:
    return Suppression(
        fingerprint=finding.fingerprint,
        policy_id=finding.policy_id,
        reason=reason,
        owner="fixture-owner",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        expires_at=expires_at,
    )


def test_active_suppressions_support_multiple_findings_duplicate_diagnostics_and_input_immutability() -> None:
    current = datetime(2026, 6, 1, tzinfo=UTC)
    finding = next(item for item in fixed_report().findings if item.fingerprint == "fp-b-tie")
    findings = [finding, finding.model_copy()]
    suppressions = [
        _suppression(finding, expires_at=current + timedelta(days=1), reason="first"),
        _suppression(finding, expires_at=current + timedelta(days=2), reason="second"),
    ]
    original_findings = [item.model_dump(mode="json") for item in findings]

    result, issues = apply_suppressions(findings, suppressions, current)

    assert [item.suppressed for item in result] == [True, True]
    assert [item.suppression.reason if item.suppression else None for item in result] == ["second", "second"]
    assert [issue.code for issue in issues] == ["SUPPRESSION_DUPLICATE"]
    assert [item.model_dump(mode="json") for item in findings] == original_findings


def test_expired_and_unmatched_suppressions_are_diagnostic_at_the_exact_expiry_time() -> None:
    current = datetime(2026, 6, 1, tzinfo=UTC)
    finding = next(item for item in fixed_report().findings if item.fingerprint == "fp-m-fail")
    expired = _suppression(finding, expires_at=current)
    unmatched = expired.model_copy(update={"fingerprint": "missing-fingerprint"})

    result, issues = apply_suppressions([finding], [expired, unmatched], current)

    assert result[0].suppressed is False
    assert [issue.code for issue in issues] == ["SUPPRESSION_EXPIRED", "SUPPRESSION_UNMATCHED"]
    assert "reopened" in issues[0].message


def test_preserve_existing_provenance_keeps_local_suppression_and_expiry_warning() -> None:
    current = datetime(2026, 6, 1, tzinfo=UTC)
    finding = next(item for item in fixed_report().findings if item.fingerprint == "fp-b-tie")
    local = _suppression(finding, expires_at=current + timedelta(days=1), reason="local")
    operational = _suppression(finding, expires_at=current + timedelta(days=2), reason="operational")
    locally_suppressed = finding.model_copy(update={"suppressed": True, "suppression": local})

    preserved, active_issues = apply_suppressions(
        [locally_suppressed], [operational], current, preserve_existing_provenance=True
    )
    still_preserved, expired_issues = apply_suppressions(
        [locally_suppressed],
        [operational.model_copy(update={"expires_at": current})],
        current,
        preserve_existing_provenance=True,
    )

    assert preserved[0].suppression is local
    assert active_issues == []
    assert still_preserved[0].suppression is local
    assert [issue.code for issue in expired_issues] == ["SUPPRESSION_EXPIRED"]
    assert "already-suppressed" in expired_issues[0].message


def test_suppression_without_explicit_now_uses_utc_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    current = datetime(2026, 6, 1, tzinfo=UTC)
    finding = next(item for item in fixed_report().findings if item.fingerprint == "fp-m-fail")

    def fixed_now(_timezone: object) -> datetime:
        return current

    fixed_clock = SimpleNamespace(now=fixed_now)
    monkeypatch.setattr("conformdag.reporting.suppressions.datetime", fixed_clock)

    result, issues = apply_suppressions([finding], [_suppression(finding, expires_at=current + timedelta(seconds=1))])

    assert result[0].suppressed is True
    assert issues == []
