"""Command-line entry point for policy-pack and scan workflows."""

from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from conformdag import __version__
from conformdag.policy import PolicyValidationError, select_policy_pack
from conformdag.scan import scan_repository

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _fail(error: Exception) -> NoReturn:
    typer.echo(f"error: {error}", err=True)
    raise typer.Exit(code=2)


@app.command("init")
def init(path: Path = Path("."), force: bool = False) -> None:
    """Create a safe starter configuration and policy-pack scaffold."""
    root = path.resolve()
    files = {
        root / "conformdag.yaml": 'config_version: "1"\n',
        root / "policies" / "pack.yaml": (
            'schema_version: "1"\nid: default\nversion: 0.1.0\npolicies: []\n'
        ),
        root / "standards" / "dag-authoring.md": "# DAG Authoring Standards\n",
        root / ".conformdag" / "suppressions.yaml": "suppressions: []\n",
    }
    for target, content in files.items():
        if target.exists() and not force:
            typer.echo(f"skipped {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        typer.echo(f"created {target}")


@app.command("validate-policies")
def validate_policies(path: Path | None = None) -> None:
    """Validate one policy pack and its local provenance sources."""
    try:
        pack = select_policy_pack(path, Path.cwd())
    except PolicyValidationError as exc:
        _fail(exc)
    typer.echo(f"valid policy pack: {pack.id} {pack.version} ({len(pack.policies)} policies)")


@app.command("list-policies")
def list_policies(path: Path | None = None) -> None:
    """List policies in one validated policy pack."""
    try:
        pack = select_policy_pack(path, Path.cwd())
    except PolicyValidationError as exc:
        _fail(exc)
    table = Table("ID", "Version", "Status", "Severity", "Enforcement")
    for policy in pack.policies:
        table.add_row(
            policy.id,
            policy.version,
            policy.status.value,
            policy.severity.value,
            policy.enforcement.type.value,
        )
    console.print(table)


@app.command("explain")
def explain(policy_id: str, path: Path | None = None) -> None:
    """Print the complete public contract for one policy."""
    try:
        pack = select_policy_pack(path, Path.cwd())
    except PolicyValidationError as exc:
        _fail(exc)
    matches = [policy for policy in pack.policies if policy.id == policy_id]
    if len(matches) != 1:
        _fail(ValueError(f"expected one policy with ID {policy_id}, found {len(matches)}"))
    typer.echo(matches[0].model_dump_json(indent=2))


@app.command()
def scan(
    path: Path = Path("."),
    policy_pack: Path | None = None,
    output: Path | None = None,
) -> None:
    """Analyze configured Python sources without importing or executing them."""
    root = path.resolve()
    selected_pack = (
        (root / policy_pack) if policy_pack and not policy_pack.is_absolute() else policy_pack
    )
    try:
        report = scan_repository(root, selected_pack)
    except PolicyValidationError as exc:
        _fail(exc)
    serialized = report.model_dump_json(indent=2)
    if output:
        output.write_text(serialized + "\n", encoding="utf-8")
    else:
        typer.echo(serialized)
    if report.issues:
        raise typer.Exit(code=3)
    if any(finding.status.value == "FAIL" for finding in report.findings):
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Show the installed ConformDAG version."""
    typer.echo(__version__)
