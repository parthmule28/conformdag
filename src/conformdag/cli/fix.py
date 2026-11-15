"""Fix command adapter."""

from pathlib import Path

import typer

from conformdag.fixing import run_fix
from conformdag.policy import PolicyValidationError, resolve_policy_pack_path

from .common import fail as _fail


def fix(
    path: Path = Path("."),
    policy_pack: Path | None = None,
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Write verified patches to sources; without it nothing is written.",
    ),
    max_iterations: int = typer.Option(
        3,
        "--max-iterations",
        min=1,
        help="Bound on the patch-and-rescan verification loop.",
    ),
) -> None:
    """Propose deterministic fixes; print unified diffs and verify by re-scan."""
    root = path.resolve()
    selected_pack = resolve_policy_pack_path(policy_pack) if policy_pack is not None else None
    try:
        outcome = run_fix(root, selected_pack, apply=apply, max_iterations=max_iterations)
    except (PolicyValidationError, ValueError, OSError) as exc:
        _fail(exc)
    for patch in outcome.patches:
        typer.echo(patch.diff, nl=False)
    for move in outcome.proposed_moves:
        typer.echo(f"PROPOSED ONLY (never applied) {move.policy_id} {move.path}")
        typer.echo(move.diff, nl=False)
    for item in outcome.not_fixable:
        typer.echo(
            f"not fixable: {item.policy_id} {item.path} [{item.fix_kind}] {item.reason}",
            err=True,
        )
    for item in outcome.residuals:
        typer.echo(
            f"residual: {item.policy_id} {item.path} [{item.fix_kind}] unresolved after {item.iterations} iteration(s)",
            err=True,
        )
    if apply and outcome.applied_files:
        typer.echo("applied: " + ", ".join(outcome.applied_files), err=True)
    typer.echo(
        f"fix {'applied' if apply else 'dry-run'}: {len(outcome.patches)} verified patch(es), "
        f"{len(outcome.proposed_moves)} proposed-only, "
        f"{len(outcome.not_fixable)} not fixable, "
        f"{len(outcome.residuals)} residual",
        err=True,
    )
    if apply and outcome.residuals:
        raise typer.Exit(code=1)
