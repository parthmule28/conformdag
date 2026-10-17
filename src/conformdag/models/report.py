"""Report model values."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .common import AirflowProfile, ConformModel
from .findings import Finding
from .gates import GateResult
from .runtime import RuntimeObservation
from .semantic import SemanticRunMetadata


def _empty_paths() -> list[Path]:
    return []


def _empty_findings() -> list[Finding]:
    return []


def _empty_issues() -> list[RunIssue]:
    return []


def _empty_runtime_observations() -> list[RuntimeObservation]:
    return []


def _empty_semantic_runs() -> list[SemanticRunMetadata]:
    return []


class RunIssue(ConformModel):
    code: str
    message: str
    path: Path | None = None
    phase: str
    fatal: bool = False


class RunMetadata(ConformModel):
    tool_version: str
    repository_revision: str | None = None
    input_hashes: dict[str, str] = Field(default_factory=dict)
    policy_pack_id: str
    policy_pack_version: str
    runtime_profile: AirflowProfile | None = None
    runtime_image_digest: str | None = None
    semantic_provider: str | None = None
    semantic_model: str | None = None
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    semantic_runs: list[SemanticRunMetadata] = Field(default_factory=_empty_semantic_runs)
    resolved_configuration: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime


class ScanReport(ConformModel):
    report_version: Literal["1", "2"] = "2"
    complete: bool
    result_fingerprint: str
    files_scanned: list[Path] = Field(default_factory=_empty_paths)
    policies_evaluated: list[str] = Field(default_factory=list)
    policies_skipped: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=_empty_findings)
    runtime_observations: list[RuntimeObservation] = Field(default_factory=_empty_runtime_observations)
    issues: list[RunIssue] = Field(default_factory=_empty_issues)
    gate_result: GateResult | None = None
    run: RunMetadata
