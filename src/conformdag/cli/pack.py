"""Policy-pack download command adapter."""

from pathlib import Path

import typer

from conformdag.policy import PolicyValidationError

from .common import PACK_CACHE_ROOT_OPTION, PACK_NAME_OPTION
from .common import fail as _fail


def pack_pull(
    source: str = typer.Argument(help="Git URL of a repository containing a policy pack."),
    name: str | None = PACK_NAME_OPTION,
    cache_root: Path | None = PACK_CACHE_ROOT_OPTION,
) -> None:
    """Pull and validate a policy pack from git; record the resolved ref."""
    from conformdag.packpull import PackPullError, pull_pack

    try:
        pulled = pull_pack(source, cache_root=cache_root, name=name)
    except (PackPullError, PolicyValidationError, OSError) as exc:
        _fail(exc)
    typer.echo(f"pulled {pulled.name} at {pulled.resolved_ref} -> {pulled.path}")
    typer.echo("re-pull to update; committing and tagging the pack stays a git operation")
