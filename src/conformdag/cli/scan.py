"""Scan command and CLI-specific execution adapters."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import typer

from conformdag.application import (
    BaselineInput,
    ExecutionOutcome,
    RuntimeExecutionError,
    RuntimeExecutor,
    ScanInputError,
    ScanOptions,
    ScanOverrides,
    classify_report,
    execute_scan,
    resolve_effective_configuration,
)
from conformdag.config import semantic_api_key
from conformdag.models import AirflowProfile, ProjectRuntimeConfig, RuntimeObservation, ScanReport
from conformdag.policy import PolicyValidationError
from conformdag.reporting import render_html, render_sarif
from conformdag.runtime import RuntimePhaseError, build_runtime_manifest, execute_runtime
from conformdag.scan import preview_model_context as build_model_context_preview
from conformdag.semantic import CachedSemanticProvider, OpenAICompatibleProvider, SemanticCache

from .common import (
    BASELINE_OPTION,
    NO_EVIDENCE_OPTION,
    PREVIEW_MODEL_CONTEXT_OPTION,
    RUNTIME_IMAGE_OPTION,
    RUNTIME_OPTION,
    SEMANTIC_BASE_URL_OPTION,
    SEMANTIC_MODEL_OPTION,
    SEMANTIC_OPTION,
    SEMANTIC_STRUCTURED_OUTPUT_OPTION,
)
from .common import fail as _fail


class _CliRuntimeExecutor:
    """Adapt the CLI's existing runtime boundary to the application protocol."""

    def validate(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        include: list[str],
        exclude: list[str],
    ) -> None:
        try:
            build_runtime_manifest(root, config, [], include, exclude)
        except RuntimePhaseError as exc:
            raise ScanInputError(str(exc)) from exc

    def execute(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        policy_ids: list[str],
        include: list[str],
        exclude: list[str],
    ) -> tuple[list[RuntimeObservation], str]:
        try:
            return execute_runtime(root, config, policy_ids, include, exclude)
        except RuntimePhaseError as exc:
            raise RuntimeExecutionError(str(exc)) from exc


def _validate_semantic_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("semantic base URL must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("semantic base URL must use HTTPS except for a loopback endpoint")
    return value


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
    baseline: Path | None = BASELINE_OPTION,
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
    try:
        effective = resolve_effective_configuration(
            root,
            invocation_overrides=ScanOverrides(
                policy_pack=policy_pack,
                airflow_profile=runtime,
                runtime_image=runtime_image,
                semantic_enabled=semantic,
                semantic_base_url=semantic_base_url or None,
                semantic_model=semantic_model or None,
                semantic_structured_output=semantic_structured_output,
            ),
            invocation_working_directory=Path.cwd(),
        )
        if preview_model_context:
            preview = build_model_context_preview(root, effective.resolved_policy_pack)
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
        config = effective.project
        semantic_config = effective.semantic
        runtime_config = effective.runtime
        provider = None
        provider_name = None
        if semantic_config.enabled:
            selected_base_url = semantic_config.base_url
            if not selected_base_url:
                raise ValueError("semantic evaluation requires semantic.base_url or --semantic-base-url")
            selected_base_url = _validate_semantic_base_url(selected_base_url)
            if not semantic_config.model:
                raise ValueError("semantic evaluation requires semantic.model or --semantic-model")
            api_key = semantic_api_key(config)
            if not api_key:
                raise ValueError(f"semantic evaluation requires environment variable {config.semantic.api_key_env}")
            direct_provider = OpenAICompatibleProvider(
                selected_base_url,
                semantic_config.model,
                api_key,
                native_structured_output=semantic_config.native_structured_output,
            )
            cache_path = semantic_config.cache_path
            if not cache_path.is_absolute():
                cache_path = root / cache_path
            provider = CachedSemanticProvider(
                direct_provider,
                SemanticCache(cache_path),
                semantic_config.model,
                {
                    "temperature": semantic_config.temperature,
                    "max_output_tokens": semantic_config.max_output_tokens,
                    "native_structured_output": semantic_config.native_structured_output,
                },
            )
            provider_name = urlsplit(selected_base_url).netloc or selected_base_url

        baseline_input = None
        if baseline is not None:
            try:
                baseline_report = ScanReport.model_validate(json.loads(baseline.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                _fail(ValueError(f"cannot load baseline report {baseline}: {exc}"))
            if baseline_report.complete is not True:
                _fail(ValueError(f"baseline report {baseline} is incomplete and cannot be used"))
            baseline_input = BaselineInput(report=baseline_report)

        runtime_executor: RuntimeExecutor | None = _CliRuntimeExecutor() if runtime_config.enabled else None
        execution = execute_scan(
            ScanOptions(repository_root=root),
            effective,
            semantic_provider=provider,
            semantic_provider_name=provider_name if semantic_config.enabled else None,
            runtime_executor=runtime_executor,
            baseline=baseline_input,
        )
        report = execution.report
    except (PolicyValidationError, RuntimePhaseError, ValueError) as exc:
        _fail(exc)

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
    outcome = classify_report(report)
    if outcome is ExecutionOutcome.INCOMPLETE:
        raise typer.Exit(code=3)
    if outcome is ExecutionOutcome.POLICY_FAILURE:
        raise typer.Exit(code=1)
