"""Suppression application and deterministic canonical report normalization."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from conformdag.models import Finding, FindingStatus, RunIssue, ScanReport, Suppression


def apply_suppressions(
    findings: list[Finding],
    suppressions: list[Suppression],
    now: datetime | None = None,
) -> tuple[list[Finding], list[RunIssue]]:
    """Apply non-expired matching suppressions and report stale/expired metadata."""
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
                    message=(
                        f"duplicate suppression for "
                        f"{suppression.policy_id}:{suppression.fingerprint}"
                    ),
                    phase="suppression",
                )
            )
        seen.add(identity)
        candidate_indexes = [
            position
            for position, finding in enumerate(result)
            if finding.policy_id == suppression.policy_id
            and finding.fingerprint == suppression.fingerprint
        ]
        if not candidate_indexes:
            issues.append(
                RunIssue(
                    code="SUPPRESSION_UNMATCHED",
                    message=(
                        f"suppression does not match a finding: "
                        f"{suppression.policy_id}:{suppression.fingerprint}"
                    ),
                    phase="suppression",
                )
            )
            continue
        if suppression.expires_at <= current:
            issues.append(
                RunIssue(
                    code="SUPPRESSION_EXPIRED",
                    message=(
                        f"expired suppression reopened finding: "
                        f"{suppression.policy_id}:{suppression.fingerprint}"
                    ),
                    phase="suppression",
                )
            )
            continue
        for position in candidate_indexes:
            result[position] = result[position].model_copy(
                update={"suppressed": True, "suppression": suppression}
            )
    return result, issues


def normalize_report(report: ScanReport) -> ScanReport:
    """Return a stable report ordering and fingerprint independent of timestamps."""
    findings = sorted(
        report.findings,
        key=lambda finding: (
            finding.policy_id,
            str(finding.location.file),
            finding.location.start_line or 0,
            finding.fingerprint,
        ),
    )
    issues = sorted(report.issues, key=lambda issue: (issue.phase, issue.code, str(issue.path)))
    files = sorted(report.files_scanned, key=str)
    payload = {
        "complete": report.complete,
        "files_scanned": [str(path) for path in files],
        "policies_evaluated": sorted(report.policies_evaluated),
        "policies_skipped": sorted(report.policies_skipped),
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "input_hashes": dict(sorted(report.run.input_hashes.items())),
        "policy_pack_id": report.run.policy_pack_id,
        "policy_pack_version": report.run.policy_pack_version,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return report.model_copy(
        update={
            "files_scanned": files,
            "findings": findings,
            "issues": issues,
            "result_fingerprint": fingerprint,
        }
    )


def has_blocking_failures(report: ScanReport) -> bool:
    """Return whether an unsuppressed deterministic failure should exit 1."""
    return any(
        finding.status is FindingStatus.FAIL
        and not finding.suppressed
        and finding.enforcement.value == "deterministic"
        for finding in report.findings
    )
