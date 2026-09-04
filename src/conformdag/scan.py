"""Source scan orchestration with an explicit optional semantic boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from conformdag import __version__
from conformdag.analysis import ParseCache, SourceModel, analyze_source, discover_python_files
from conformdag.config import load_project_config
from conformdag.evaluator import EvaluationPhaseError, evaluate_deterministic
from conformdag.models import (
    AirflowProfile,
    EnforcementType,
    Finding,
    PolicyPack,
    ProjectConfig,
    RunIssue,
    RunMetadata,
    ScanReport,
    SemanticRequest,
    SemanticResponse,
    SemanticRunMetadata,
)
from conformdag.policy import load_suppressions, resolve_configured_policy_pack, select_policy_pack
from conformdag.reporting import apply_suppressions, normalize_report
from conformdag.semantic import SemanticContext, SemanticProviderError, build_context
from conformdag.semantic_evaluator import build_semantic_request, semantic_finding


class SemanticProvider(Protocol):
    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]: ...


def _load_pack_for_scan(
    repository_root: Path,
    policy_pack: Path | None,
) -> tuple[ProjectConfig, PolicyPack]:
    config = load_project_config(repository_root / "conformdag.yaml")
    explicit_pack = policy_pack is not None
    configured_pack = policy_pack or config.scan.policy_pack
    resolved_pack = resolve_configured_policy_pack(
        configured_pack,
        scan_root=repository_root,
        from_cli=explicit_pack,
    )
    pack = select_policy_pack(resolved_pack, repository_root)
    return config, pack


def scan_repository(
    repository_root: Path,
    policy_pack: Path | None = None,
    *,
    semantic_provider: SemanticProvider | None = None,
    semantic_provider_name: str | None = None,
    semantic_model: str | None = None,
    semantic_native_structured_output: bool | None = None,
    airflow_profile: AirflowProfile | None = None,
    parse_cache: ParseCache | None = None,
) -> ScanReport:
    """Run source analysis and any explicitly supplied semantic provider."""
    root = repository_root.resolve()
    config, pack = _load_pack_for_scan(root, policy_pack)
    files, discovery_issues = discover_python_files(
        root,
        config.scan.include,
        config.scan.exclude,
        config.scan.follow_internal_symlinks,
    )
    findings: list[Finding] = []
    issues = [
        RunIssue(
            code="DISCOVERY",
            message=issue.message,
            path=Path(issue.path),
            phase="discovery",
            fatal=issue.message != "symlink excluded",
        )
        for issue in discovery_issues
    ]
    models: list[SourceModel] = []
    for source in files:
        model, parse_issue = analyze_source(source, parse_cache)
        if parse_issue:
            issues.append(
                RunIssue(
                    code="PARSE_ERROR",
                    message=parse_issue.message,
                    path=Path(parse_issue.path),
                    phase="analysis",
                    fatal=True,
                )
            )
        elif model:
            models.append(model)

    try:
        findings, evaluated, skipped = evaluate_deterministic(
            pack.policies,
            models,
            airflow_profile or config.runtime.airflow_version,
        )
    except EvaluationPhaseError as exc:
        issues.append(RunIssue(code="EVALUATOR_ERROR", message=str(exc), phase="evaluation", fatal=True))
        evaluated = []
        skipped = [policy.id for policy in pack.policies]

    prompt_hashes: dict[str, str] = {}
    semantic_runs: list[SemanticRunMetadata] = []
    if semantic_provider is not None:
        if semantic_model is None:
            raise ValueError("semantic_model is required when a semantic provider is supplied")
        semantic_policies = [
            policy
            for policy in sorted(pack.policies, key=lambda item: item.id)
            if policy.status.value == "ACTIVE"
            and policy.enforcement.type in (EnforcementType.SEMANTIC, EnforcementType.HYBRID)
        ]
        policy_text = "\n\n".join(
            f"{policy.id}: {policy.invariant}\nRemediation: {policy.safe_path or 'none'}"
            for policy in semantic_policies
        )
        context = build_context(
            policy_text,
            {source.relative_path: source.content for source in files},
            max_input_tokens=config.semantic.max_input_tokens,
        )
        if context.omitted_files:
            issues.append(
                RunIssue(
                    code="SEMANTIC_CONTEXT_OMITTED",
                    message="semantic context budget omitted: " + ", ".join(context.omitted_files),
                    phase="semantic-context",
                )
            )
        requests = [
            build_semantic_request(policy, context).model_copy(
                update={
                    "temperature": config.semantic.temperature,
                    "max_output_tokens": config.semantic.max_output_tokens,
                }
            )
            for policy in semantic_policies
        ]
        try:
            responses = semantic_provider.evaluate_many(
                requests,
                max_concurrency=config.semantic.max_concurrency,
            )
            if len(responses) != len(requests):
                raise SemanticProviderError("provider returned an unexpected response count")
            for policy, request, response in zip(semantic_policies, requests, responses, strict=True):
                findings.append(semantic_finding(policy, response, context))
                prompt_hash = hashlib.sha256(request.system_prompt.encode("utf-8")).hexdigest()
                prompt_hashes[policy.id] = prompt_hash
                semantic_runs.append(
                    SemanticRunMetadata(
                        policy_id=policy.id,
                        requested_model=semantic_model,
                        served_model=response.served_model,
                        context_hash=request.context_hash,
                        prompt_hash=prompt_hash,
                        usage=response.usage,
                        retries=response.retries,
                        latency_ms=response.latency_ms,
                        cache_hit=response.cache_hit,
                        repeatability=response.repeatability,
                        pricing_provenance=response.pricing_provenance,
                    )
                )
                if policy.id not in evaluated:
                    evaluated.append(policy.id)
                if policy.id in skipped:
                    skipped.remove(policy.id)
        except SemanticProviderError as exc:
            issues.append(
                RunIssue(
                    code="SEMANTIC_PROVIDER_ERROR",
                    message=str(exc),
                    phase="semantic-evaluation",
                    fatal=True,
                )
            )

    suppression_path = config.scan.suppressions
    if not suppression_path.is_absolute():
        suppression_path = root / suppression_path
    suppressions = load_suppressions(suppression_path)
    findings, suppression_issues = apply_suppressions(findings, suppressions)
    issues.extend(suppression_issues)
    report = ScanReport(
        complete=not any(issue.fatal for issue in issues),
        result_fingerprint="",
        files_scanned=[source.path.relative_to(root) for source in files],
        policies_evaluated=evaluated,
        policies_skipped=skipped,
        findings=findings,
        issues=issues,
        run=RunMetadata(
            tool_version=__version__,
            input_hashes={source.relative_path: source.content_hash for source in files},
            policy_pack_id=pack.id,
            policy_pack_version=pack.version,
            semantic_provider=semantic_provider_name if semantic_provider is not None else None,
            semantic_model=semantic_model if semantic_provider is not None else None,
            prompt_hashes=prompt_hashes,
            semantic_runs=semantic_runs,
            resolved_configuration={
                "scan": {
                    "include": config.scan.include,
                    "exclude": config.scan.exclude,
                    "follow_internal_symlinks": config.scan.follow_internal_symlinks,
                },
                "semantic": {
                    "enabled": semantic_provider is not None,
                    "temperature": config.semantic.temperature,
                    "max_input_tokens": config.semantic.max_input_tokens,
                    "max_output_tokens": config.semantic.max_output_tokens,
                    "max_concurrency": config.semantic.max_concurrency,
                    "native_structured_output": (
                        config.semantic.native_structured_output
                        if semantic_native_structured_output is None
                        else semantic_native_structured_output
                    ),
                },
            },
            timestamp=datetime.now(UTC),
        ),
    )
    return normalize_report(report)


def preview_model_context(repository_root: Path, policy_pack: Path | None = None) -> SemanticContext:
    """Build the redacted semantic context preview without contacting a provider."""
    root = repository_root.resolve()
    config, pack = _load_pack_for_scan(root, policy_pack)
    files, _ = discover_python_files(
        root,
        config.scan.include,
        config.scan.exclude,
        config.scan.follow_internal_symlinks,
    )
    policy_text = "\n\n".join(
        f"{policy.id}: {policy.invariant}\nRemediation: {policy.safe_path or 'none'}"
        for policy in pack.policies
        if policy.enforcement.type.value in {"semantic", "hybrid"} and policy.status.value == "ACTIVE"
    )
    return build_context(
        policy_text,
        {source.relative_path: source.content for source in files},
        max_input_tokens=config.semantic.max_input_tokens,
    )
