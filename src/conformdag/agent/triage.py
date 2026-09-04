"""Triage layer: classify findings into deterministic fixes and manual work."""

from __future__ import annotations

from dataclasses import dataclass, field

from conformdag.fixing.codemods import AUTOFIX_KINDS
from conformdag.models import ScanReport


def _empty_findings() -> list[FindingSummary]:
    return []


@dataclass(frozen=True)
class FindingSummary:
    """A minimal, self-contained finding description for the agent contract."""

    policy_id: str
    file_path: str
    start_line: int | None
    explanation: str
    fingerprint: str


@dataclass
class Triage:
    """The deterministic agent plan derived from one scan report."""

    fixable: list[FindingSummary] = field(default_factory=_empty_findings)
    manual: list[FindingSummary] = field(default_factory=_empty_findings)


def _summary(report: ScanReport, index: int) -> FindingSummary:
    finding = report.findings[index]
    return FindingSummary(
        policy_id=finding.policy_id,
        file_path=finding.location.file.as_posix() if finding.location.file else "",
        start_line=finding.location.start_line,
        explanation=finding.explanation or finding.status.value,
        fingerprint=finding.fingerprint,
    )


def triage_report(report: ScanReport) -> Triage:
    """Split unsuppressed deterministic failures by fixability.

    The LLM never participates in triage: classification is a pure rule over
    the remediation payload and the fixability matrix.
    """
    triage = Triage()
    for index, finding in enumerate(report.findings):
        if finding.status.value != "FAIL" or finding.suppressed or finding.enforcement.value != "deterministic":
            continue
        payload = finding.fix
        is_fixable = payload is not None and payload.action.value != "manual" and payload.fix_kind in AUTOFIX_KINDS
        if is_fixable:
            triage.fixable.append(_summary(report, index))
        else:
            triage.manual.append(_summary(report, index))
    return triage


def summary_lines(summaries: list[FindingSummary]) -> list[str]:
    """Render one-line evidence strings for PR bodies and logs."""
    lines: list[str] = []
    for summary in summaries:
        location = summary.file_path
        if summary.start_line is not None:
            location += f":{summary.start_line}"
        lines.append(f"{summary.policy_id} {location} — {summary.explanation}")
    return lines
