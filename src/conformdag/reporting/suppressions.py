"""Suppression application and diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime

from conformdag.models import Finding, RunIssue, Suppression


def apply_suppressions(
    findings: list[Finding],
    suppressions: list[Suppression],
    now: datetime | None = None,
    *,
    preserve_existing_provenance: bool = False,
) -> tuple[list[Finding], list[RunIssue]]:
    """Apply suppressions and report metadata, optionally retaining prior provenance."""
    current = now or datetime.now(UTC)
    issues: list[RunIssue] = []
    seen: set[tuple[str, str]] = set()
    result = list(findings)
    for suppression in suppressions:
        identity = (suppression.policy_id, suppression.fingerprint)
        if identity in seen:
            issues.append(
                RunIssue(
                    code="SUPPRESSION_DUPLICATE",
                    message=(f"duplicate suppression for {suppression.policy_id}:{suppression.fingerprint}"),
                    phase="suppression",
                )
            )
        seen.add(identity)
        candidate_indexes = [
            position
            for position, finding in enumerate(result)
            if finding.policy_id == suppression.policy_id and finding.fingerprint == suppression.fingerprint
        ]
        if not candidate_indexes:
            issues.append(
                RunIssue(
                    code="SUPPRESSION_UNMATCHED",
                    message=(
                        f"suppression does not match a finding: {suppression.policy_id}:{suppression.fingerprint}"
                    ),
                    phase="suppression",
                )
            )
            continue
        if suppression.expires_at <= current:
            already_suppressed = preserve_existing_provenance and any(
                result[position].suppressed for position in candidate_indexes
            )
            message = (
                f"expired suppression matched an already-suppressed finding and left it suppressed: "
                f"{suppression.policy_id}:{suppression.fingerprint}"
                if already_suppressed
                else f"expired suppression reopened finding: {suppression.policy_id}:{suppression.fingerprint}"
            )
            issues.append(
                RunIssue(
                    code="SUPPRESSION_EXPIRED",
                    message=message,
                    phase="suppression",
                )
            )
            continue
        for position in candidate_indexes:
            finding = result[position]
            if not preserve_existing_provenance or not finding.suppressed:
                result[position] = finding.model_copy(update={"suppressed": True, "suppression": suppression})
    return result, issues
