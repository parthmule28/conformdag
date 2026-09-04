"""Policy-review mode: draft governance proposals from report aggregates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from conformdag.models import ScanReport


def _empty_counts() -> dict[str, int]:
    return {}


@dataclass
class PolicyAggregate:
    """Governance aggregates computed from reports on disk."""

    fail_counts: dict[str, int] = field(default_factory=_empty_counts)
    suppression_counts: dict[str, int] = field(default_factory=_empty_counts)
    stale_suppression_codes: int = 0
    report_count: int = 0

    def suppression_rate(self, policy_id: str) -> float:
        """Return the ratio of suppressions to failures for one policy."""
        failures = self.fail_counts.get(policy_id, 0)
        if failures == 0:
            return 0.0
        return self.suppression_counts.get(policy_id, 0) / failures


def aggregate_reports(reports: list[ScanReport]) -> PolicyAggregate:
    """Compute fail and suppression counts plus stale-suppression diagnostics."""
    aggregate = PolicyAggregate(report_count=len(reports))
    for report in reports:
        for finding in report.findings:
            if finding.status.value == "FAIL" and not finding.suppressed:
                aggregate.fail_counts[finding.policy_id] = aggregate.fail_counts.get(finding.policy_id, 0) + 1
            if finding.suppressed:
                aggregate.suppression_counts[finding.policy_id] = (
                    aggregate.suppression_counts.get(finding.policy_id, 0) + 1
                )
        aggregate.stale_suppression_codes += sum(1 for issue in report.issues if issue.code.startswith("SUPPRESSION_"))
    return aggregate


def load_reports(paths: list[Path]) -> list[ScanReport]:
    """Load canonical report JSON files from disk."""
    reports: list[ScanReport] = []
    for path in paths:
        reports.append(ScanReport.model_validate_json(path.read_text(encoding="utf-8")))
    return reports


def draft_proposal(aggregate: PolicyAggregate, pack_id: str) -> str:
    """Render a policy-pack change proposal from the aggregates."""
    lines = [
        f"# Policy pack review proposal ({pack_id})",
        "",
        f"Aggregated over {aggregate.report_count} scan(s); "
        f"{aggregate.stale_suppression_codes} stale/unmatched/expired suppression code(s).",
        "",
        "## Heavy suppression",
        "",
    ]
    suppressed = sorted(
        ((policy_id, count) for policy_id, count in aggregate.suppression_counts.items() if count > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    if not suppressed:
        lines.append("- None; no suppressions recorded.")
    else:
        for policy_id, count in suppressed:
            rate = aggregate.suppression_rate(policy_id)
            lines.append(f"- `{policy_id}`: {count} suppression(s) ({rate:.0%} of unsuppressed failures)")
    lines.extend(["", "## Recurring failures", ""])
    failing = sorted(aggregate.fail_counts.items(), key=lambda item: item[1], reverse=True)
    if not failing:
        lines.append("- None; no unsuppressed failures found.")
    else:
        for policy_id, count in failing[:10]:
            lines.append(f"- `{policy_id}`: {count} failing finding(s)")
    lines.extend(
        [
            "",
            "Proposal: consider scoping, tightening, or relaxing the policies above "
            "in the next pack version. Committing and tagging the pack remains a "
            "human git operation.",
        ]
    )
    return "\n".join(lines)


def proposal_json(aggregate: PolicyAggregate) -> str:
    """Return the machine-readable aggregate payload."""
    return json.dumps(
        {
            "report_count": aggregate.report_count,
            "fail_counts": aggregate.fail_counts,
            "suppression_counts": aggregate.suppression_counts,
            "stale_suppression_codes": aggregate.stale_suppression_codes,
        },
        indent=2,
        sort_keys=True,
    )
