"""Agent command adapters."""

from pathlib import Path

import typer

from conformdag.policy import PolicyValidationError, resolve_policy_pack_path

from .common import AGENT_FORMAT_OPTION, AGENT_PACK_ID_OPTION, AGENT_REPORTS_ARGUMENT
from .common import fail as _fail


def agent_run(
    path: Path = Path("."),
    policy_pack: Path | None = None,
    open_pr: bool = typer.Option(False, "--open-pr", help="Push a fix branch and open a PR under the agent identity."),
    no_verifier: bool = typer.Option(
        False, "--no-verifier", help="Skip the LLM semantic verifier (deterministic gates only)."
    ),
) -> None:
    """Fix findings deterministically, verify semantically, and optionally open a PR."""
    from conformdag.agent import AgentSettings, PrClient, Verifier, VerifierRequest, run_agent_pipeline

    try:
        settings = AgentSettings.from_environment(require_verifier=not no_verifier, require_github=open_pr)
        root = path.resolve()
        selected_pack = resolve_policy_pack_path(policy_pack) if policy_pack is not None else None
        verifier = None
        if not no_verifier:
            verifier = Verifier(
                settings.base_url,
                settings.api_key,
                VerifierRequest(model=settings.model),
                cache_path=root / ".conformdag" / "agent-verdict-cache.json",
            )
        pull_requests = None
        if open_pr:
            pull_requests = PrClient(
                token=settings.github_token,
                repo=settings.github_repo,
                base=settings.base_branch,
            )
        outcome = run_agent_pipeline(root, selected_pack, verifier=verifier, pull_requests=pull_requests)
    except (PolicyValidationError, ValueError, OSError, RuntimeError) as exc:
        _fail(exc)
    for line in outcome.fixed_findings:
        typer.echo(f"fixed: {line}", err=True)
    for line in outcome.manual_findings:
        typer.echo(f"manual: {line}", err=True)
    if outcome.verdict is not None:
        typer.echo(
            f"verifier: {outcome.verdict.verdict} ({outcome.verdict.reason_code})",
            err=True,
        )
    if outcome.pull_request_url:
        typer.echo(f"pull request: {outcome.pull_request_url}", err=True)
    elif outcome.blocked:
        typer.echo("pull request blocked by verifier verdict", err=True)
        raise typer.Exit(code=1)
    if not outcome.changed:
        typer.echo("agent run: nothing to fix", err=True)


def agent_policy_review(
    reports: list[Path] = AGENT_REPORTS_ARGUMENT,
    pack_id: str = AGENT_PACK_ID_OPTION,
    output: Path | None = None,
    format: str = AGENT_FORMAT_OPTION,
) -> None:
    """Aggregate reports on disk and draft a policy-pack change proposal."""
    from conformdag.agent import aggregate_reports, draft_proposal, load_reports, proposal_json

    if format not in {"markdown", "json"}:
        _fail(ValueError("format must be markdown or json"))
    try:
        loaded = load_reports(list(reports))
    except (OSError, ValueError) as exc:
        _fail(exc)
    aggregate = aggregate_reports(loaded)
    rendered = proposal_json(aggregate) if format == "json" else draft_proposal(aggregate, pack_id)
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    else:
        typer.echo(rendered, nl=False)
