"""Quality-gate evaluation: turn findings into org-defined pass/fail decisions."""

from __future__ import annotations

from conformdag.models import (
    AlwaysBlockRule,
    FailureRateRule,
    Finding,
    FindingStatus,
    GateResult,
    GateRule,
    GateRuleResult,
    MaxFindingsRule,
    MaxSeverityRule,
    NoNewFindingsRule,
    PolicyPack,
    QualityGate,
    ScanReport,
    Severity,
)

SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def blocking_findings(report: ScanReport) -> list[Finding]:
    """Return unsuppressed failing findings the legacy exit code blocks on."""
    return [
        finding
        for finding in report.findings
        if finding.status is FindingStatus.FAIL
        and not finding.suppressed
        and (finding.enforcement.value == "deterministic" or finding.blocking)
    ]


def _evaluate_rule(rule: GateRule, report: ScanReport, baseline_report: ScanReport | None) -> GateRuleResult:
    if isinstance(rule, NoNewFindingsRule):
        baseline_fingerprints = (
            {finding.fingerprint for finding in baseline_report.findings} if baseline_report is not None else set[str]()
        )
        new = [finding for finding in blocking_findings(report) if finding.fingerprint not in baseline_fingerprints]
        return GateRuleResult(
            rule_type=rule.type,
            passed=not new,
            detail=f"{len(new)} new failing finding(s) since the baseline",
            matching_findings=len(new),
        )
    if isinstance(rule, MaxSeverityRule):
        threshold = SEVERITY_ORDER[rule.severity]
        over = [f for f in blocking_findings(report) if SEVERITY_ORDER[f.severity] >= threshold]
        return GateRuleResult(
            rule_type=rule.type,
            passed=not over,
            detail=f"{len(over)} failing finding(s) at or above severity {rule.severity.value}",
            matching_findings=len(over),
        )
    if isinstance(rule, MaxFindingsRule):
        failing = blocking_findings(report)
        return GateRuleResult(
            rule_type=rule.type,
            passed=not failing or len(failing) < rule.count,
            detail=f"{len(failing)} failing finding(s), limit is {rule.count}",
            matching_findings=len(failing),
        )
    if isinstance(rule, AlwaysBlockRule):
        blocked = [f for f in blocking_findings(report) if f.policy_id in rule.policy_ids]
        return GateRuleResult(
            rule_type=rule.type,
            passed=not blocked,
            detail=f"{len(blocked)} finding(s) for always-block policies {sorted(rule.policy_ids)}",
            matching_findings=len(blocked),
        )
    rate_rule: FailureRateRule = rule
    total = len(report.findings)
    failing = len(blocking_findings(report))
    percent = (failing / total * 100.0) if total else 0.0
    return GateRuleResult(
        rule_type=rate_rule.type,
        passed=percent < rate_rule.max_percent,
        detail=f"failure rate {percent:.1f}% (limit {rate_rule.max_percent}%)",
        matching_findings=failing,
    )


def evaluate_gate(gate: QualityGate, report: ScanReport, baseline_report: ScanReport | None) -> GateResult:
    """Evaluate one gate; the gate passes only when every rule passes."""
    results = [_evaluate_rule(rule, report, baseline_report) for rule in gate.rules]
    return GateResult(gate_id=gate.id, passed=all(result.passed for result in results), rules=results)


def evaluate_pack_gates(pack: PolicyPack, report: ScanReport, baseline_report: ScanReport | None) -> GateResult | None:
    """Evaluate all gates; return the first failing gate or the first gate overall.

    Returns None when the pack defines no gates (legacy behavior applies).
    """
    if not pack.quality_gates:
        return None
    results = [evaluate_gate(gate, report, baseline_report) for gate in pack.quality_gates]
    failing = next((result for result in results if not result.passed), None)
    return failing if failing is not None else results[0]


def validate_quality_gates(pack: PolicyPack) -> list[str]:
    """Return pack-level gate authoring errors (duplicate ids, unknown policies)."""
    issues: list[str] = []
    gate_ids = [gate.id for gate in pack.quality_gates]
    if len(gate_ids) != len(set(gate_ids)):
        issues.append("quality gate ids must be unique within a pack")
    policy_ids = {policy.id for policy in pack.policies}
    for gate in pack.quality_gates:
        for rule in gate.rules:
            if isinstance(rule, AlwaysBlockRule):
                missing = sorted(set(rule.policy_ids) - policy_ids)
                if missing:
                    issues.append(f"gate {gate.id!r} references unknown policy ids: {', '.join(missing)}")
    return issues
