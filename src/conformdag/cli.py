"""Command-line entry point for policy-pack and scan workflows."""

import json
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from conformdag import __version__
from conformdag.models import Policy, PolicyPack
from conformdag.policy import PolicyValidationError, select_policy_pack
from conformdag.reference import (
    EXIT_CODE_REFERENCE,
    OUTCOME_REFERENCE,
    REPORT_REFERENCE,
    RUNTIME_REFERENCE,
    ReferenceEntry,
)
from conformdag.reporting import has_blocking_failures, render_html, render_sarif
from conformdag.scan import preview_model_context as build_model_context_preview
from conformdag.scan import scan_repository

app = typer.Typer(add_completion=False, no_args_is_help=True)
policy_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(policy_app, name="policy")
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


def _load_selected_pack(path: Path | None) -> PolicyPack:
    try:
        return select_policy_pack(path, Path.cwd())
    except PolicyValidationError as exc:
        _fail(exc)


def _load_policy(policy_id: str, path: Path | None) -> tuple[PolicyPack, Policy]:
    pack = _load_selected_pack(path)
    matches = [policy for policy in pack.policies if policy.id == policy_id]
    if len(matches) != 1:
        _fail(ValueError(f"expected one policy with ID {policy_id}, found {len(matches)}"))
    return pack, matches[0]


def _policy_summary(policy: Policy) -> str:
    return "\n".join(
        [
            f"ID: {policy.id}",
            f"Title: {policy.title}",
            f"Version: {policy.version}",
            f"Status: {policy.status.value}",
            f"Severity: {policy.severity.value}",
            f"Enforcement: {policy.enforcement.type.value}",
            f"Owner: {policy.ownership.owner}",
            f"Airflow profiles: {', '.join(policy.airflow_profiles) or 'source-only'}",
            f"Scope: {', '.join(policy.scope.files)}",
        ]
    )


@policy_app.command("show")
def policy_show(policy_id: str, path: Path | None = None) -> None:
    """Show a concise human-readable summary of one policy."""
    _, policy = _load_policy(policy_id, path)
    typer.echo(_policy_summary(policy))


@policy_app.command("review")
def policy_review(policy_id: str, path: Path | None = None) -> None:
    """Review one policy's contract, provenance, enforcement, and exceptions."""
    pack, policy = _load_policy(policy_id, path)
    typer.echo(f"Policy review: {policy.id}\n")
    typer.echo(_policy_summary(policy))
    typer.echo("\nInvariant:\n" + policy.invariant)
    typer.echo(f"\nSafe path:\n{policy.safe_path or 'Not specified'}")
    typer.echo("\nSource:")
    typer.echo(f"  document: {policy.source.document}")
    typer.echo(f"  section: {policy.source.section}")
    typer.echo(f"  version: {policy.source.version or 'Not specified'}")
    typer.echo(f"  content hash: {policy.source.content_hash}")
    typer.echo("\nEnforcement configuration:")
    typer.echo(json.dumps(policy.enforcement.model_dump(mode="json"), indent=2, sort_keys=True))
    typer.echo("\nPolicy configuration:")
    typer.echo(json.dumps(policy.configuration.model_dump(mode="json"), indent=2, sort_keys=True))
    typer.echo("\nExceptions:")
    typer.echo(json.dumps(policy.exceptions.model_dump(mode="json"), indent=2, sort_keys=True))
    typer.echo(f"\nPack: {pack.id} {pack.version}")


@policy_app.command("explain")
def policy_explain(policy_id: str, path: Path | None = None) -> None:
    """Emit the complete machine-readable JSON policy contract."""
    _, policy = _load_policy(policy_id, path)
    typer.echo(policy.model_dump_json(indent=2))


@app.command("explain", hidden=True)
def explain(policy_id: str, path: Path | None = None) -> None:
    """Backward-compatible alias for the machine-readable policy contract."""
    policy_explain(policy_id, path)


def _reference_entries(topic: str) -> dict[str, tuple[ReferenceEntry, ...]]:
    references: dict[str, tuple[ReferenceEntry, ...]] = {
        "outcomes": OUTCOME_REFERENCE,
        "exit-codes": EXIT_CODE_REFERENCE,
        "runtime": RUNTIME_REFERENCE,
        "reports": REPORT_REFERENCE,
    }
    if topic == "all":
        selected = references
    elif topic in references:
        selected = {topic: references[topic]}
    else:
        valid = ", ".join(["all", *references])
        _fail(ValueError(f"reference topic must be one of: {valid}"))
    return selected


def _reference_payload(topic: str) -> dict[str, list[dict[str, str]]]:
    return {
        name: [
            {"key": entry.key, "meaning": entry.meaning, "behavior": entry.behavior}
            for entry in entries
        ]
        for name, entries in _reference_entries(topic).items()
    }


@policy_app.command("reference")
def policy_reference(
    topic: str = typer.Argument(
        "all", help="Reference topic: all, outcomes, exit-codes, runtime, or reports."
    ),
    format: str = "terminal",
) -> None:
    """Explain policy outcomes, exit codes, runtime, and report contracts."""
    if format not in {"terminal", "json"}:
        _fail(ValueError("format must be one of: terminal, json"))
    selected = _reference_entries(topic)
    if format == "json":
        typer.echo(json.dumps(_reference_payload(topic), indent=2, sort_keys=True))
        return
    for section, entries in selected.items():
        typer.echo(section.title())
        table = Table("Value", "Meaning", "Behavior")
        for entry in entries:
            table.add_row(entry.key, entry.meaning, entry.behavior)
        console.print(table)


@app.command()
def scan(
    path: Path = Path("."),
    policy_pack: Path | None = None,
    output: Path | None = None,
    format: str = "json",
    no_evidence: bool = False,
    preview_model_context: bool = False,
) -> None:
    """Analyze sources and render JSON, SARIF, HTML, or terminal output."""
    root = path.resolve()
    selected_pack = (
        (root / policy_pack) if policy_pack and not policy_pack.is_absolute() else policy_pack
    )
    try:
        if preview_model_context:
            preview = build_model_context_preview(root, selected_pack)
            typer.echo(
                json.dumps(
                    {
                        "context_hash": preview.context_hash,
                        "included_files": preview.included_files,
                        "omitted_files": preview.omitted_files,
                        "redacted_context": preview.text,
                    },
                    indent=2,
                )
            )
            return
        report = scan_repository(root, selected_pack)
    except PolicyValidationError as exc:
        _fail(exc)
    if format not in {"json", "sarif", "html", "terminal"}:
        _fail(ValueError("format must be one of: json, sarif, html, terminal"))
    if format == "html" and output is None:
        _fail(ValueError("HTML output requires --output"))
    if format == "terminal" and output is not None:
        _fail(ValueError("terminal output cannot be written with --output"))

    output_report = report
    if no_evidence:
        output_report = report.model_copy(
            update={
                "findings": [
                    finding.model_copy(update={"evidence": None}) for finding in report.findings
                ]
            }
        )
    if format == "json":
        rendered = output_report.model_dump_json(indent=2) + "\n"
    elif format == "sarif":
        rendered = json.dumps(render_sarif(output_report), indent=2, sort_keys=True) + "\n"
    elif format == "html":
        rendered = render_html(output_report, include_evidence=not no_evidence)
    else:
        rendered = (
            f"ConformDAG scan {'complete' if report.complete else 'incomplete'}\n"
            f"Files: {len(report.files_scanned)}\n"
            f"Findings: {len(report.findings)}\n"
            f"Result fingerprint: {report.result_fingerprint}\n"
        )
    if output:
        output.write_text(rendered, encoding="utf-8")
    else:
        typer.echo(rendered, nl=False)
    typer.echo(
        f"scan {'complete' if report.complete else 'incomplete'}: "
        f"{len(report.files_scanned)} files, {len(report.findings)} findings",
        err=True,
    )
    if report.issues:
        raise typer.Exit(code=3)
    if has_blocking_failures(report):
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Show the installed ConformDAG version."""
    typer.echo(__version__)
