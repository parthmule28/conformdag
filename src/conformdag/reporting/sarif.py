"""Canonical SARIF projection for scan reports."""

from __future__ import annotations

from conformdag.models import FindingStatus, ScanReport
from conformdag.security.redaction import redact_credentials


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
                "help": {"text": redact_credentials(finding.remediation or "Review the policy guidance.")},
            },
        )
        if finding.status is FindingStatus.PASS:
            continue
        result: dict[str, object] = {
            "ruleId": finding.policy_id,
            "level": level_by_severity.get(finding.severity.value, "note"),
            "message": {"text": redact_credentials(finding.explanation or finding.status.value)},
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
