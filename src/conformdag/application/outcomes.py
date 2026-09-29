"""Transport-neutral outcomes derived from canonical scan reports."""

from enum import StrEnum

from conformdag.gates import blocking_findings
from conformdag.models import FindingStatus, ScanReport


class ExecutionOutcome(StrEnum):
    SUCCESS = "success"
    POLICY_FAILURE = "policy_failure"
    INCOMPLETE = "incomplete"


def classify_report(report: ScanReport) -> ExecutionOutcome:
    """Interpret a report independently of its producing application execution."""
    if not report.complete or any(issue.fatal for issue in report.issues):
        return ExecutionOutcome.INCOMPLETE
    if report.gate_result is not None:
        if not report.gate_result.passed:
            return ExecutionOutcome.POLICY_FAILURE
    elif blocking_findings(report):
        return ExecutionOutcome.POLICY_FAILURE
    if any(observation.status is FindingStatus.FAIL for observation in report.runtime_observations):
        return ExecutionOutcome.POLICY_FAILURE
    return ExecutionOutcome.SUCCESS
