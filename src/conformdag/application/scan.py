"""Complete application scan orchestration over the canonical scan engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from conformdag.analysis import ParseCache
from conformdag.application.configuration import EffectiveScanConfiguration
from conformdag.application.errors import RuntimeExecutionError, ScanInputError
from conformdag.gates import evaluate_pack_gates
from conformdag.models import (
    FindingStatus,
    GateResult,
    ProjectRuntimeConfig,
    RunIssue,
    RuntimeObservation,
    ScanReport,
    Suppression,
)
from conformdag.policy import select_policy_pack
from conformdag.reporting import apply_suppressions, normalize_report
from conformdag.scan import SemanticProvider, scan_repository


@dataclass(frozen=True)
class ScanOptions:
    repository_root: Path


@dataclass(frozen=True)
class BaselineInput:
    report: ScanReport | None = None
    fingerprints: frozenset[str] | None = None


@dataclass(frozen=True)
class ScanExecutionResult:
    report: ScanReport
    gate_result: GateResult | None


class RuntimeExecutor(Protocol):
    def validate(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        include: list[str],
        exclude: list[str],
    ) -> None: ...

    def execute(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        policy_ids: list[str],
        include: list[str],
        exclude: list[str],
    ) -> tuple[list[RuntimeObservation], str]: ...


def execute_scan(
    options: ScanOptions,
    configuration: EffectiveScanConfiguration,
    *,
    semantic_provider: SemanticProvider | None = None,
    semantic_provider_name: str | None = None,
    runtime_executor: RuntimeExecutor | None = None,
    baseline: BaselineInput | None = None,
    operational_suppressions: Sequence[Suppression] = (),
    parse_cache: ParseCache | None = None,
) -> ScanExecutionResult:
    """Run one core scan from resolved settings and explicitly supplied phase adapters."""
    root = options.repository_root.resolve()
    config = configuration.project
    pack = select_policy_pack(configuration.resolved_policy_pack, root)

    if baseline is not None:
        if baseline.report is not None and baseline.fingerprints is not None:
            raise ScanInputError("baseline cannot contain both report and fingerprints")
        if baseline.report is not None and not baseline.report.complete:
            raise ScanInputError("baseline report is incomplete and cannot be used")

    if semantic_provider is not None and not configuration.semantic.enabled:
        raise ScanInputError("semantic provider supplied while semantic evaluation is disabled")
    if semantic_provider is not None and not configuration.semantic.model:
        raise ScanInputError("semantic provider requires a model")

    if runtime_executor is not None and not configuration.runtime.enabled:
        raise ScanInputError("RuntimeExecutor supplied while runtime analysis is disabled")
    if runtime_executor is not None:
        runtime_executor.validate(root, configuration.runtime, config.scan.include, config.scan.exclude)

    report = scan_repository(
        root,
        configuration.resolved_policy_pack,
        semantic_provider=semantic_provider,
        semantic_provider_name=semantic_provider_name,
        semantic_model=configuration.semantic.model if semantic_provider is not None else None,
        semantic_native_structured_output=configuration.semantic.native_structured_output,
        airflow_profile=configuration.runtime.airflow_version,
        parse_cache=parse_cache,
    )

    if runtime_executor is not None:
        try:
            observations, image_digest = runtime_executor.execute(
                root,
                configuration.runtime,
                sorted(set(report.policies_evaluated + report.policies_skipped)),
                configuration.project.scan.include,
                configuration.project.scan.exclude,
            )
        except RuntimeExecutionError as exc:
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
        else:
            observations = sorted(
                observations,
                key=lambda item: (item.policy_id, item.status.value, item.message or ""),
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
                            "runtime_profile": configuration.runtime.airflow_version,
                            "runtime_image_digest": image_digest,
                            "resolved_configuration": {
                                **report.run.resolved_configuration,
                                "runtime": {
                                    "enabled": True,
                                    "airflow_profile": (
                                        configuration.runtime.airflow_version.value
                                        if configuration.runtime.airflow_version is not None
                                        else None
                                    ),
                                    "supported_profile": configuration.runtime.airflow_version is not None,
                                    "network_enabled": configuration.runtime.network_enabled,
                                    "timeout_seconds": configuration.runtime.timeout_seconds,
                                },
                            },
                        }
                    ),
                }
            )

    if operational_suppressions:
        had_unresolved_errors = any(
            finding.status is FindingStatus.ERROR and not finding.suppressed for finding in report.findings
        )
        findings, suppression_issues = apply_suppressions(
            report.findings,
            list(operational_suppressions),
            preserve_existing_provenance=True,
        )
        remaining_errors = [
            finding for finding in findings if finding.status is FindingStatus.ERROR and not finding.suppressed
        ]
        issues = list(report.issues)
        complete = report.complete
        if had_unresolved_errors and not remaining_errors:
            issues = [
                issue
                for issue in issues
                if not (issue.code == "EVALUATION_ERROR" and issue.phase == "evaluation" and issue.fatal)
            ]
            complete = not any(issue.fatal for issue in issues)
        report = report.model_copy(
            update={
                "findings": findings,
                "issues": [*issues, *suppression_issues],
                "complete": complete,
            }
        )

    final_report = normalize_report(report.model_copy(update={"gate_result": None}))
    gate_result = None
    if final_report.complete:
        gate_result = evaluate_pack_gates(
            pack,
            final_report,
            baseline.report if baseline is not None else None,
            baseline_fingerprints=(
                set(baseline.fingerprints) if baseline is not None and baseline.fingerprints is not None else None
            ),
        )
    if gate_result is not None:
        final_report = final_report.model_copy(update={"gate_result": gate_result})
    return ScanExecutionResult(report=final_report, gate_result=gate_result)
