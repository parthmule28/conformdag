"""Complete application scan orchestration over the canonical scan engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from conformdag.analysis import ParseCache
from conformdag.application.errors import ScanInputError
from conformdag.models import (
    AirflowProfile,
    GateResult,
    ProjectRuntimeConfig,
    RuntimeObservation,
    ScanReport,
    Suppression,
)
from conformdag.scan import SemanticProvider, load_pack_for_scan, scan_repository


@dataclass(frozen=True)
class ScanOptions:
    repository_root: Path
    policy_pack: Path | None = None
    airflow_profile: AirflowProfile | None = None


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
    *,
    semantic_provider: SemanticProvider | None = None,
    semantic_provider_name: str | None = None,
    semantic_model: str | None = None,
    semantic_native_structured_output: bool | None = None,
    runtime_config: ProjectRuntimeConfig | None = None,
    runtime_executor: RuntimeExecutor | None = None,
    baseline: BaselineInput | None = None,
    operational_suppressions: Sequence[Suppression] = (),
    parse_cache: ParseCache | None = None,
) -> ScanExecutionResult:
    """Run one core scan with optional injected phase inputs."""
    root = options.repository_root.resolve()
    load_pack_for_scan(root, options.policy_pack)

    if baseline is not None:
        if baseline.report is not None and baseline.fingerprints is not None:
            raise ScanInputError("baseline cannot contain both report and fingerprints")
        if baseline.report is not None and not baseline.report.complete:
            raise ScanInputError("baseline report is incomplete and cannot be used")

    if semantic_provider is not None and not semantic_model:
        raise ScanInputError("semantic provider requires a model")

    report = scan_repository(
        root,
        options.policy_pack,
        semantic_provider=semantic_provider,
        semantic_provider_name=semantic_provider_name,
        semantic_model=semantic_model,
        semantic_native_structured_output=semantic_native_structured_output,
        airflow_profile=options.airflow_profile,
        parse_cache=parse_cache,
    )
    return ScanExecutionResult(report=report, gate_result=None)
