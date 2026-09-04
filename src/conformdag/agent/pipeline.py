"""Agent pipeline: deterministic fix, LLM verification, and human-merged PRs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from conformdag.agent.pr import PrClient
from conformdag.agent.triage import summary_lines, triage_report
from conformdag.agent.verifier import Verdict, Verifier
from conformdag.fixing import run_fix
from conformdag.models import ScanReport

BRANCH_PREFIX = "conformdag/fix"


def _empty_files() -> list[str]:
    return []


def _empty_lines() -> list[str]:
    return []


@dataclass
class AgentOutcome:
    """The full pipeline result with its interpretability evidence."""

    changed: bool
    diff: str
    applied_files: list[str] = field(default_factory=_empty_files)
    verdict: Verdict | None = None
    blocked: bool = False
    pull_request_url: str | None = None
    fixed_findings: list[str] = field(default_factory=_empty_lines)
    manual_findings: list[str] = field(default_factory=_empty_lines)

    def pr_body(self, repo_label: str) -> str:
        """Render the evidence-rich PR body from this outcome."""
        lines = ["Automated policy conformance fixes by ConformDAG.", "", "## Findings fixed"]
        lines.extend(f"- {line}" for line in self.fixed_findings)
        lines.extend(["", "## Verification", "- Deterministic re-scan: clean for all fixed findings"])
        if self.verdict is not None:
            lines.append(
                f"- LLM-verifier verdict: **{self.verdict.verdict}** "
                f"({self.verdict.reason_code}, confidence {self.verdict.confidence})"
            )
            if self.verdict.concerns:
                lines.append(f"- Verifier concerns: {'; '.join(self.verdict.concerns)}")
        lines.extend(["", "## Files changed"])
        lines.extend(f"- `{path}`" for path in self.applied_files)
        lines.extend(
            [
                "",
                f"Source repository: {repo_label}. Merging is a human action; the agent holds no merge capability.",
            ]
        )
        return "\n".join(lines)


def run_agent_pipeline(
    root: Path,
    policy_pack: Path | None,
    *,
    verifier: Verifier | None = None,
    pull_requests: PrClient | None = None,
    branch_prefix: str = BRANCH_PREFIX,
) -> AgentOutcome:
    """Run the deterministic fix loop and, when confident, open a PR.

    Args:
        root: DAG repository root.
        policy_pack: Explicit pack path or bundled alias.
        verifier: Optional LLM semantic verifier; approve is required for a PR.
        pull_requests: Optional PR client; without it the outcome stays local.
        branch_prefix: Prefix for the created fix branch.

    Returns:
        The complete agent outcome including the verdict and PR URL.
    """
    outcome = run_fix(root, policy_pack, apply=True)
    triage = triage_report(outcome.initial_report)
    pipeline = AgentOutcome(
        changed=bool(outcome.patches),
        diff="".join(patch.diff for patch in outcome.patches),
        applied_files=list(outcome.applied_files),
        fixed_findings=summary_lines(triage.fixable),
        manual_findings=summary_lines(triage.manual),
    )
    if not outcome.patches:
        return pipeline
    after = outcome.verification_report or outcome.initial_report
    if verifier is not None:
        pipeline.verdict = verifier.verify(pipeline.diff, outcome.initial_report, after)
        if pipeline.verdict.verdict in {"reject", "escalate"}:
            pipeline.blocked = True
            return pipeline
    if pull_requests is not None:
        branch = f"{branch_prefix}{pipeline.applied_files[0].replace('/', '-')}"
        pipeline.pull_request_url = pull_requests.open_pull_request(
            root,
            branch,
            _title(outcome.initial_report),
            pipeline.pr_body(pull_requests.repo),
        )
    return pipeline


def _title(report: ScanReport) -> str:
    policies = sorted({finding.policy_id for finding in report.findings if finding.fix is not None})
    label = policies[0] if len(policies) == 1 else f"{len(policies)} policies"
    return f"conformdag: fix policy findings ({label})"
