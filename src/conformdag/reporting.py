"""Suppression application and deterministic canonical report normalization."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from jinja2 import Environment, select_autoescape

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
            issues.append(
                RunIssue(
                    code="SUPPRESSION_EXPIRED",
                    message=(
                        f"expired suppression reopened finding: {suppression.policy_id}:{suppression.fingerprint}"
                    ),
                    phase="suppression",
                )
            )
            continue
        for position in candidate_indexes:
            result[position] = result[position].model_copy(update={"suppressed": True, "suppression": suppression})
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
    runtime_observations = sorted(
        report.runtime_observations,
        key=lambda observation: (
            observation.policy_id,
            observation.status.value,
            observation.message or "",
        ),
    )
    payload = {
        "complete": report.complete,
        "files_scanned": [str(path) for path in files],
        "policies_evaluated": sorted(report.policies_evaluated),
        "policies_skipped": sorted(report.policies_skipped),
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "runtime_observations": [observation.model_dump(mode="json") for observation in runtime_observations],
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "input_hashes": dict(sorted(report.run.input_hashes.items())),
        "policy_pack_id": report.run.policy_pack_id,
        "policy_pack_version": report.run.policy_pack_version,
        "runtime_profile": report.run.runtime_profile,
        "runtime_image_digest": report.run.runtime_image_digest,
        "semantic_provider": report.run.semantic_provider,
        "semantic_model": report.run.semantic_model,
        "prompt_hashes": dict(sorted(report.run.prompt_hashes.items())),
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return report.model_copy(
        update={
            "files_scanned": files,
            "findings": findings,
            "runtime_observations": runtime_observations,
            "issues": issues,
            "result_fingerprint": fingerprint,
        }
    )


def has_blocking_failures(report: ScanReport) -> bool:
    """Return whether an unsuppressed blocking failure should exit 1."""
    return any(
        finding.status is FindingStatus.FAIL
        and not finding.suppressed
        and (finding.enforcement.value == "deterministic" or finding.blocking)
        for finding in report.findings
    )


def render_sarif(report: ScanReport) -> dict[str, object]:
    """Render canonical findings into a SARIF 2.1.0 document."""
    rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []
    level_by_severity = {"critical": "error", "high": "error", "medium": "warning"}
    for finding in report.findings:
        rules.setdefault(
            finding.policy_id,
            {
                "id": finding.policy_id,
                "shortDescription": {"text": finding.policy_id},
                "help": {"text": finding.remediation or "Review the policy guidance."},
            },
        )
        if finding.status is FindingStatus.PASS:
            continue
        result: dict[str, object] = {
            "ruleId": finding.policy_id,
            "level": level_by_severity.get(finding.severity.value, "note"),
            "message": {"text": finding.explanation or finding.status.value},
            "properties": {
                "status": finding.status.value,
                "suppressed": finding.suppressed,
                "fingerprint": finding.fingerprint,
            },
        }
        if finding.location.file:
            region: dict[str, object] = {}
            if finding.location.start_line:
                region["startLine"] = finding.location.start_line
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": str(finding.location.file)},
                        "region": region,
                    }
                }
            ]
        if finding.suppressed:
            result["suppressions"] = [{"kind": "external", "justification": "external suppression"}]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ConformDAG",
                        "version": report.run.tool_version,
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "automationDetails": {"id": report.result_fingerprint},
            }
        ],
    }


def render_html(report: ScanReport, include_evidence: bool = True) -> str:
    """Render a self-contained offline HTML report with accessible table markup."""
    template = Environment(
        autoescape=select_autoescape(default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    ).from_string(
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ConformDAG report</title><style>
body{font-family:system-ui,sans-serif;margin:2rem;color:#202124}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #bbb;padding:.5rem;text-align:left;vertical-align:top}
th{background:#eee}.evidence{font-family:monospace;margin-top:.4rem;white-space:pre-wrap}
.PASS{color:#176b2c}.FAIL{color:#a20d0d}.NEEDS_REVIEW{color:#7a4b00}
</style></head><body>
<h1>ConformDAG report</h1>
<p>Complete: {{ report.complete }}; Result fingerprint:
<code>{{ report.result_fingerprint }}</code></p>
<table><caption>Policy findings</caption><thead><tr>
<th scope="col">Policy</th><th scope="col">Status</th><th scope="col">Severity</th>
<th scope="col">Location</th><th scope="col">Explanation</th>
</tr></thead><tbody>
{% for finding in report.findings %}<tr>
<td>{{ finding.policy_id }}</td>
<td class="{{ finding.status.value }}">{{ finding.status.value }}</td>
<td>{{ finding.severity.value }}</td><td>{{ finding.location.file or "" }}</td>
<td>{{ finding.explanation or "" }}{% if include_evidence and finding.evidence %}
<div class="evidence">{{ finding.evidence.text }}</div>{% endif %}</td>
</tr>{% endfor %}
</tbody></table></body></html>
"""
    )
    return template.render(report=report, include_evidence=include_evidence)
