"""Command-line entry point for policy-pack and scan workflows."""

import json
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.table import Table

from conformdag import __version__
from conformdag.benchmark import (
    BenchmarkValidationError,
    render_benchmark_report,
    run_deterministic_benchmark,
)
from conformdag.config import load_project_config, semantic_api_key
from conformdag.fixing import run_fix
from conformdag.models import (
    AirflowProfile,
    FindingStatus,
    Policy,
    PolicyPack,
    RunIssue,
)
from conformdag.policy import PolicyValidationError, resolve_policy_pack_path, select_policy_pack
from conformdag.reference import (
    EXIT_CODE_REFERENCE,
    OUTCOME_REFERENCE,
    REPORT_REFERENCE,
    RUNTIME_REFERENCE,
    ReferenceEntry,
)
from conformdag.reporting import has_blocking_failures, normalize_report, render_html, render_sarif
from conformdag.runtime import RuntimePhaseError, build_runtime_manifest, execute_runtime
from conformdag.scan import preview_model_context as build_model_context_preview
from conformdag.scan import scan_repository
from conformdag.semantic import CachedSemanticProvider, OpenAICompatibleProvider, SemanticCache

app = typer.Typer(add_completion=False, no_args_is_help=True)
policy_app = typer.Typer(add_completion=False, no_args_is_help=True)
agent_app = typer.Typer(add_completion=False, no_args_is_help=True)
pack_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(policy_app, name="policy")
app.add_typer(agent_app, name="agent")
app.add_typer(pack_app, name="pack")
console = Console()
RUNTIME_OPTION = typer.Option(
    None,
    "--runtime",
    help="Enable the maintained published runtime profile (3.3.0).",
)
RUNTIME_IMAGE_OPTION = typer.Option(
    None,
    "--runtime-image",
    help="Enable an explicitly pinned custom runtime image.",
)
NO_EVIDENCE_OPTION = typer.Option(
    False,
    "--no-evidence",
    help="Remove source evidence from rendered findings.",
)
PREVIEW_MODEL_CONTEXT_OPTION = typer.Option(
    False,
    "--preview-model-context",
    help="Print the redacted semantic context without calling a provider.",
)
SEMANTIC_OPTION = typer.Option(
    None,
    "--semantic/--no-semantic",
    help="Enable or disable BYOK semantic evaluation (defaults to project configuration).",
)
SEMANTIC_BASE_URL_OPTION = typer.Option(
    None,
    "--semantic-base-url",
    help="Override the configured OpenAI-compatible API base URL.",
)
SEMANTIC_MODEL_OPTION = typer.Option(
    None,
    "--semantic-model",
    help="Override the exact configured semantic model ID.",
)
SEMANTIC_STRUCTURED_OUTPUT_OPTION = typer.Option(
    None,
    "--semantic-structured-output/--no-semantic-structured-output",
    help="Enable or disable provider-native strict JSON Schema output.",
)
BENCHMARK_PATH_ARGUMENT = typer.Argument(Path("benchmarks/synthetic"))
BENCHMARK_POLICY_PACK_OPTION = typer.Option(Path("policies/pack.yaml"), "--policy-pack")
BENCHMARK_OUTPUT_OPTION = typer.Option(None, "--output", help="Write the JSON report to this path.")
BENCHMARK_MARKDOWN_OPTION = typer.Option(
    None, "--technical-report", help="Write the human-readable Markdown report to this path."
)
AGENT_REPORTS_ARGUMENT = typer.Argument(help="Canonical report JSON paths to aggregate.")
AGENT_PACK_ID_OPTION = typer.Option("org-pack", "--pack-id", help="Pack label for the proposal.")
AGENT_FORMAT_OPTION = typer.Option("markdown", "--format", help="Proposal format: markdown or json.")
PACK_NAME_OPTION = typer.Option(None, "--name", help="Local cache name for the pulled pack.")
PACK_CACHE_ROOT_OPTION = typer.Option(None, "--cache-root", help="Cache root; defaults to .conformdag/packs.")


def _fail(error: Exception) -> NoReturn:
    typer.echo(f"error: {error}", err=True)
    raise typer.Exit(code=2)


def _validate_semantic_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("semantic base URL must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("semantic base URL must use HTTPS except for a loopback endpoint")
    return value


@app.command("init")
def init(path: Path = Path("."), force: bool = False) -> None:
    """Create a safe starter configuration and policy-pack scaffold."""
    root = path.resolve()
    files = {
        root / "conformdag.yaml": (
            'config_version: "1"\n'
            "scan:\n"
            "  policy_pack: policies/pack.yaml\n"
            "  include:\n"
            '    - "dags/**/*.py"\n'
            "  exclude:\n"
            '    - "**/.venv/**"\n'
            '    - "**/.git/**"\n'
            '    - "**/vendor/**"\n'
            '    - "**/generated/**"\n'
            "semantic:\n"
            "  enabled: false\n"
            "runtime:\n"
            "  enabled: false\n"
        ),
        root / "policies" / "pack.yaml": ('schema_version: "1"\nid: default\nversion: 0.1.0\npolicies: []\n'),
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
        resolved = resolve_policy_pack_path(path) if path is not None else None
        pack = select_policy_pack(resolved, Path.cwd())
    except PolicyValidationError as exc:
        _fail(exc)
    typer.echo(f"valid policy pack: {pack.id} {pack.version} ({len(pack.policies)} policies)")


@app.command("list-policies")
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
        name: [{"key": entry.key, "meaning": entry.meaning, "behavior": entry.behavior} for entry in entries]
        for name, entries in _reference_entries(topic).items()
    }


@policy_app.command("reference")
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


@app.command()
def scan(
    path: Path = Path("."),
    policy_pack: Path | None = None,
    output: Path | None = None,
    format: str = "json",
    no_evidence: bool = NO_EVIDENCE_OPTION,
    preview_model_context: bool = PREVIEW_MODEL_CONTEXT_OPTION,
    runtime: AirflowProfile | None = RUNTIME_OPTION,
    runtime_image: str | None = RUNTIME_IMAGE_OPTION,
    semantic: bool | None = SEMANTIC_OPTION,
    semantic_base_url: str | None = SEMANTIC_BASE_URL_OPTION,
    semantic_model: str | None = SEMANTIC_MODEL_OPTION,
    semantic_structured_output: bool | None = SEMANTIC_STRUCTURED_OUTPUT_OPTION,
) -> None:
    """Analyze sources and render JSON, SARIF, HTML, or terminal output."""
    if format not in {"json", "sarif", "html", "terminal"}:
        _fail(ValueError("format must be one of: json, sarif, html, terminal"))
    if format == "html" and output is None:
        _fail(ValueError("HTML output requires --output"))
    if format == "terminal" and output is not None:
        _fail(ValueError("terminal output cannot be written with --output"))
    if preview_model_context and (
        runtime is not None or runtime_image is not None or semantic is True or output is not None
    ):
        _fail(ValueError("--preview-model-context cannot be combined with runtime, semantic, or output"))
    root = path.resolve()
    selected_pack = resolve_policy_pack_path(policy_pack) if policy_pack is not None else None
    try:
        config = load_project_config(root / "conformdag.yaml")
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
        if runtime is not None and runtime_image is not None:
            raise RuntimePhaseError("--runtime and --runtime-image cannot be used together")
        runtime_config = config.runtime
        if runtime is not None or runtime_image is not None:
            runtime_config = runtime_config.model_copy(
                update={
                    "enabled": True,
                    "airflow_version": runtime,
                    "image": runtime_image,
                }
            )
        if runtime_config.enabled:
            build_runtime_manifest(
                root,
                runtime_config,
                [],
                config.scan.include,
                config.scan.exclude,
            )

        semantic_enabled = config.semantic.enabled if semantic is None else semantic
        provider = None
        provider_name = None
        selected_semantic_model = semantic_model or config.semantic.model
        native_structured_output = (
            config.semantic.native_structured_output
            if semantic_structured_output is None
            else semantic_structured_output
        )
        if semantic_enabled:
            selected_base_url = semantic_base_url or config.semantic.base_url
            if not selected_base_url:
                raise ValueError("semantic evaluation requires semantic.base_url or --semantic-base-url")
            selected_base_url = _validate_semantic_base_url(selected_base_url)
            if not selected_semantic_model:
                raise ValueError("semantic evaluation requires semantic.model or --semantic-model")
            api_key = semantic_api_key(config)
            if not api_key:
                raise ValueError(f"semantic evaluation requires environment variable {config.semantic.api_key_env}")
            direct_provider = OpenAICompatibleProvider(
                selected_base_url,
                selected_semantic_model,
                api_key,
                native_structured_output=native_structured_output,
            )
            cache_path = config.semantic.cache_path
            if not cache_path.is_absolute():
                cache_path = root / cache_path
            provider = CachedSemanticProvider(
                direct_provider,
                SemanticCache(cache_path),
                selected_semantic_model,
                {
                    "temperature": config.semantic.temperature,
                    "max_output_tokens": config.semantic.max_output_tokens,
                    "native_structured_output": native_structured_output,
                },
            )
            provider_name = urlsplit(selected_base_url).netloc or selected_base_url

        report = scan_repository(
            root,
            selected_pack,
            semantic_provider=provider,
            semantic_provider_name=provider_name,
            semantic_model=selected_semantic_model if semantic_enabled else None,
            semantic_native_structured_output=(native_structured_output if semantic_enabled else None),
            airflow_profile=runtime_config.airflow_version if runtime_config.enabled else None,
        )
    except (PolicyValidationError, RuntimePhaseError, ValueError) as exc:
        _fail(exc)

    if runtime_config.enabled:
        try:
            observations, image_digest = execute_runtime(
                root,
                runtime_config,
                sorted(set(report.policies_evaluated + report.policies_skipped)),
                config.scan.include,
                config.scan.exclude,
            )
            runtime_issues = [
                RunIssue(
                    code="RUNTIME_OBSERVATION_ERROR",
                    message=observation.message or "runtime analysis returned ERROR",
                    phase="runtime",
                    fatal=True,
                )
                for observation in observations
                if observation.status is FindingStatus.ERROR
            ]
            report = report.model_copy(
                update={
                    "complete": report.complete and not runtime_issues,
                    "runtime_observations": observations,
                    "issues": [*report.issues, *runtime_issues],
                    "run": report.run.model_copy(
                        update={
                            "runtime_profile": runtime_config.airflow_version,
                            "runtime_image_digest": image_digest,
                            "resolved_configuration": {
                                **report.run.resolved_configuration,
                                "runtime": {
                                    "enabled": True,
                                    "airflow_profile": (
                                        runtime_config.airflow_version.value
                                        if runtime_config.airflow_version is not None
                                        else None
                                    ),
                                    "supported_profile": (runtime_config.airflow_version is not None),
                                    "network_enabled": runtime_config.network_enabled,
                                    "timeout_seconds": runtime_config.timeout_seconds,
                                },
                            },
                        }
                    ),
                }
            )
        except RuntimePhaseError as exc:
            report = report.model_copy(
                update={
                    "complete": False,
                    "issues": [
                        *report.issues,
                        RunIssue(
                            code="RUNTIME_EXECUTION_ERROR",
                            message=str(exc),
                            phase="runtime",
                            fatal=True,
                        ),
                    ],
                }
            )
        report = normalize_report(report)
    output_report = report
    if no_evidence:
        output_report = report.model_copy(
            update={
                "findings": [
                    finding.model_copy(update={"evidence": None, "audit_evidence": []}) for finding in report.findings
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
    if any(issue.fatal for issue in report.issues):
        raise typer.Exit(code=3)
    if has_blocking_failures(report):
        raise typer.Exit(code=1)
    if any(observation.status is FindingStatus.FAIL for observation in report.runtime_observations):
        raise typer.Exit(code=1)


@app.command()
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


@app.command()
def version() -> None:
    """Show the installed ConformDAG version."""
    typer.echo(__version__)


@pack_app.command("pull")
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


@agent_app.command("run")
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
    if not outcome.changed:
        typer.echo("agent run: nothing to fix", err=True)


@agent_app.command("policy-review")
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


def _platform_session_factory():
    from conformdag.platform.app import load_settings
    from conformdag.platform.db import create_session_factory

    settings = load_settings()
    return settings, create_session_factory(settings.dsn)


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address for the dashboard API."),
    port: int = typer.Option(8642, "--port", help="Bind port for the dashboard API."),
) -> None:
    """Serve the platform dashboard API on /api/v1."""
    try:
        import uvicorn

        from conformdag.platform.app import create_app
    except ImportError as exc:  # pragma: no cover - guarded by the platform extra
        _fail(ValueError(f"platform extra is not installed: {exc}"))
    settings, session_factory = _platform_session_factory()
    platform_app = create_app(session_factory, settings)
    uvicorn.run(platform_app, host=host, port=port, log_level="info")


@app.command("worker")
def worker_command() -> None:
    """Run the durable platform worker that executes queued scans."""
    try:
        from conformdag.platform.worker import WorkerSettings, run_worker
    except ImportError as exc:  # pragma: no cover - guarded by the platform extra
        _fail(ValueError(f"platform extra is not installed: {exc}"))
    settings, session_factory = _platform_session_factory()
    typer.echo("platform worker started", err=True)
    run_worker(session_factory, settings.dsn, WorkerSettings.from_environment())


@app.command("benchmark")
def benchmark(
    path: Path = BENCHMARK_PATH_ARGUMENT,
    policy_pack: Path = BENCHMARK_POLICY_PACK_OPTION,
    output: Path | None = BENCHMARK_OUTPUT_OPTION,
    technical_report: Path | None = BENCHMARK_MARKDOWN_OPTION,
) -> None:
    """Verify and run the local deterministic benchmark without provider or network access."""
    root = Path.cwd().resolve()
    manifest_path = path / "manifest.yaml" if path.is_dir() else path
    selected_pack = resolve_policy_pack_path(policy_pack)
    try:
        result = run_deterministic_benchmark(manifest_path, selected_pack, root)
    except (BenchmarkValidationError, ValueError, OSError) as exc:
        _fail(exc)
    payload = json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(payload, encoding="utf-8")
    else:
        typer.echo(payload, nl=False)
    if technical_report is not None:
        technical_report.write_text(render_benchmark_report(result), encoding="utf-8")
    if not result.passed:
        raise typer.Exit(code=1)
