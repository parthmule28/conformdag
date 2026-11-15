"""Policy validation, inspection, and scaffolding commands."""

import hashlib
import io
import json
from pathlib import Path

import typer
from rich.table import Table
from ruamel.yaml import YAML

from conformdag.checks.registry import CHECK_EVALUATORS, check_spec
from conformdag.models import Policy, PolicyPack
from conformdag.policy import (
    PolicyValidationError,
    resolve_policy_pack_path,
    select_policy_pack,
)
from conformdag.reference import (
    EXIT_CODE_REFERENCE,
    OUTCOME_REFERENCE,
    REPORT_REFERENCE,
    RUNTIME_REFERENCE,
    ReferenceEntry,
)

from .common import console
from .common import fail as _fail


def validate_policies(path: Path | None = None) -> None:
    """Validate one policy pack and its local provenance sources."""
    try:
        resolved = resolve_policy_pack_path(path) if path is not None else None
        pack = select_policy_pack(resolved, Path.cwd())
    except PolicyValidationError as exc:
        _fail(exc)
    typer.echo(f"valid policy pack: {pack.id} {pack.version} ({len(pack.policies)} policies)")


def list_policies(path: Path | None = None) -> None:
    """List policies in one validated policy pack."""
    try:
        resolved = resolve_policy_pack_path(path) if path is not None else None
        pack = select_policy_pack(resolved, Path.cwd())
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


def _policy_configuration(kind: str) -> dict[str, object]:
    try:
        spec = check_spec(kind)
    except KeyError as exc:
        raise ValueError(f"no policy scaffold is defined for check kind {kind!r}") from exc
    if spec.evaluator is None or spec.scaffold_factory is None:
        raise ValueError(f"no policy scaffold is defined for check kind {kind!r}")
    return spec.scaffold_factory()


def _source_section(document_text: str) -> str:
    subsection: str | None = None
    heading: str | None = None
    first_text: str | None = None
    for line in document_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        first_text = first_text or stripped
        if stripped.startswith("##") and not stripped.startswith("###"):
            subsection = stripped.lstrip("#").strip()
        elif stripped.startswith("#"):
            heading = heading or stripped.lstrip("#").strip()
    section = subsection or heading or first_text
    if not section:
        raise ValueError("standards document must contain a non-empty section")
    return section


def _load_selected_pack(path: Path | None) -> PolicyPack:
    try:
        resolved = resolve_policy_pack_path(path) if path is not None else None
        return select_policy_pack(resolved, Path.cwd())
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


def policy_show(policy_id: str, path: Path | None = None) -> None:
    """Show a concise human-readable summary of one policy."""
    _, policy = _load_policy(policy_id, path)
    typer.echo(_policy_summary(policy))


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


def policy_explain(policy_id: str, path: Path | None = None) -> None:
    """Emit the complete machine-readable JSON policy contract."""
    _, policy = _load_policy(policy_id, path)
    typer.echo(policy.model_dump_json(indent=2))


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
        name: [{"key": entry.key, "meaning": entry.meaning, "behavior": entry.behavior} for entry in entries]
        for name, entries in _reference_entries(topic).items()
    }


def policy_reference(
    topic: str = typer.Argument("all", help="Reference topic: all, outcomes, exit-codes, runtime, or reports."),
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


def policy_hash(document: str) -> None:
    """Print the SHA-256 provenance hash of a standards document."""
    path = Path(document)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(ValueError(f"cannot read document {document}: {exc}"))
    typer.echo(hashlib.sha256(text.encode("utf-8")).hexdigest())


def policy_new(
    policy_id: str,
    kind: str = typer.Option(..., "--kind", help="Check kind for the policy configuration."),
    document: str = typer.Option("standards/dag-authoring.md", "--document", help="Standards document for provenance."),
) -> None:
    """Print a valid policy block scaffold for a check kind."""
    if kind not in CHECK_EVALUATORS:
        _fail(ValueError(f"unknown check kind {kind!r}; known kinds: {', '.join(sorted(CHECK_EVALUATORS))}"))
    doc_path = Path(document)
    try:
        text = doc_path.read_text(encoding="utf-8")
        section = _source_section(text)
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except OSError as exc:
        _fail(ValueError(f"cannot read document {document}: {exc}"))
    except ValueError as exc:
        _fail(exc)
    block: dict[str, object] = {
        "id": policy_id,
        "title": "TBD - describe the invariant in one line",
        "version": "1.0.0",
        "status": "ACTIVE",
        "severity": "medium",
        "airflow_profiles": ["3.3.0"],
        "ownership": {"owner": "platform"},
        "source": {"document": document, "section": section, "version": "1", "content_hash": content_hash},
        "invariant": "TBD",
        "safe_path": "TBD",
        "enforcement": {"type": "deterministic", "deterministic_checks": [kind], "blocking": True},
        "configuration": _policy_configuration(kind),
    }
    try:
        Policy.model_validate(block)
    except ValueError as exc:
        _fail(ValueError(f"scaffolded policy is invalid for kind {kind!r}: {exc}"))
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    buffer = io.StringIO()
    yaml.dump(block, buffer)  # pyright: ignore[reportUnknownMemberType]
    typer.echo(buffer.getvalue(), nl=False)
