"""Versioned public models shared by policy, scan, runtime, and report layers."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, field_validator

from .common import AirflowProfile, Confidence, ConformModel, EnforcementType, FindingStatus, LifecycleStatus, Severity
from .gates import (
    AlwaysBlockRule,
    FailureRateRule,
    GateResult,
    GateRule,
    GateRuleResult,
    MaxFindingsRule,
    MaxSeverityRule,
    NoNewFindingsRule,
    QualityGate,
)
from .policy import (
    ApprovedAbstractionsConfig,
    CatchupPolicyConfig,
    DynamicDagFactoryConfig,
    EnforcementConfig,
    ExceptionPolicy,
    ExecutionTimeoutConfig,
    ForbiddenOperatorsConfig,
    IdempotenceConfig,
    ModuleScopeVariablesConfig,
    OperatorRule,
    OrchestrationBoundaryConfig,
    Ownership,
    Policy,
    PolicyConfiguration,
    PolicyPack,
    PolicyScope,
    PolicySource,
    RequiredOwnerConfig,
    RequiredTagsConfig,
    RetryBoundsConfig,
    RuffAirConfig,
    SensitiveLoggingConfig,
    StartDateFreshnessConfig,
    TopLevelIOConfig,
)


def _empty_paths() -> list[Path]:
    return []


def _empty_findings() -> list[Finding]:
    return []


def _empty_audit_evidence() -> list[SemanticAuditEvidence]:
    return []


def _empty_issues() -> list[RunIssue]:
    return []


def _empty_runtime_observations() -> list[RuntimeObservation]:
    return []


def _empty_semantic_runs() -> list[SemanticRunMetadata]:
    return []


class FindingEvidence(ConformModel):
    text: str
    start_line: PositiveInt | None = None
    end_line: PositiveInt | None = None
    code_hash: str | None = None


class FindingLocation(ConformModel):
    file: Path | None = None
    start_line: PositiveInt | None = None
    end_line: PositiveInt | None = None


class RemediationAction(StrEnum):
    ADD_KWARG = "add-kwarg"
    SET_KWARG = "set-kwarg"
    ADD_OWNER = "add-owner"
    ADD_TAGS = "add-tags"
    MOVE_STATEMENT = "move-statement"
    MANUAL = "manual"


class RemediationTarget(ConformModel):
    line: PositiveInt
    column: NonNegativeInt = 0
    enclosing: str | None = None
    node: Literal["dag-call", "task-call", "statement"] = "statement"


class RemediationPayload(ConformModel):
    fix_kind: str
    action: RemediationAction
    kwarg: str | None = None
    target: RemediationTarget | None = None
    value: str | None = None
    hint: str | None = None


class Suppression(ConformModel):
    fingerprint: str
    policy_id: str
    reason: str
    owner: str
    created_at: datetime
    expires_at: datetime


class SemanticAuditEvidence(ConformModel):
    criterion: str
    source_type: Literal["source", "runtime", "policy", "provider"]
    location: str | None = None
    excerpt: str = Field(max_length=240)
    unresolved: bool = False


class Finding(ConformModel):
    policy_id: str
    policy_version: str
    status: FindingStatus
    severity: Severity
    enforcement: EnforcementType
    location: FindingLocation = Field(default_factory=FindingLocation)
    evidence: FindingEvidence | None = None
    explanation: str | None = None
    remediation: str | None = None
    confidence: Confidence | None = None
    fix: RemediationPayload | None = None
    audit_evidence: list[SemanticAuditEvidence] = Field(default_factory=_empty_audit_evidence)
    fingerprint: str
    blocking: bool = False
    suppressed: bool = False
    suppression: Suppression | None = None


class RunIssue(ConformModel):
    code: str
    message: str
    path: Path | None = None
    phase: str
    fatal: bool = False


class RuntimeObservation(ConformModel):
    schema_version: Literal["1"] = "1"
    status: FindingStatus
    policy_id: str
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SemanticRunMetadata(ConformModel):
    policy_id: str
    requested_model: str
    served_model: str | None = None
    context_hash: str
    prompt_hash: str
    usage: dict[str, NonNegativeInt] = Field(default_factory=dict)
    retries: NonNegativeInt = 0
    latency_ms: NonNegativeInt = 0
    cache_hit: bool = False
    repeatability: Literal["not-measured", "repeatable", "varied"] = "not-measured"
    pricing_provenance: str | None = None


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


class RuntimeManifest(ConformModel):
    schema_version: Literal["1"] = "1"
    repository_root: Path
    include: list[str]
    exclude: list[str]
    policy_ids: list[str]
    airflow_profile: AirflowProfile | None = None
    image: str | None = None
    provider_versions: dict[str, str] = Field(default_factory=dict)
    supported_profile: bool = False
    network_enabled: bool = False
    timeout_seconds: PositiveInt = 300


class SemanticRequest(ConformModel):
    schema_version: Literal["1"] = "1"
    policy_id: str
    policy_version: str = "unknown"
    policy_contract_hash: str = ""
    enforcement_hash: str = ""
    prompt_version: str
    context_hash: str
    system_prompt: str
    evidence: str
    max_output_tokens: PositiveInt = 4000
    temperature: float = 0.0


class SemanticResponse(ConformModel):
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW", "NOT_APPLICABLE"]
    evidence: str
    explanation: str
    remediation: str | None = None
    confidence: Confidence
    audit_evidence: list[SemanticAuditEvidence] = Field(default_factory=_empty_audit_evidence)
    served_model: str | None = None
    usage: dict[str, NonNegativeInt] = Field(default_factory=dict)
    retries: NonNegativeInt = 0
    latency_ms: NonNegativeInt = 0
    cache_hit: bool = False
    repeatability: Literal["not-measured", "repeatable", "varied"] = "not-measured"
    pricing_provenance: str | None = None


class ProjectScanConfig(ConformModel):
    policy_pack: Path = Path("policies/pack.yaml")
    suppressions: Path = Path(".conformdag/suppressions.yaml")
    include: list[str] = Field(default_factory=lambda: ["dags/**/*.py"])
    exclude: list[str] = Field(default_factory=lambda: ["**/.venv/**", "**/.git/**", "**/vendor/**", "**/generated/**"])
    follow_internal_symlinks: bool = False


class ProjectSemanticConfig(ConformModel):
    enabled: bool = False
    base_url: str | None = None
    model: str | None = None
    api_key_env: str = "CONFORMDAG_MODEL_API_KEY"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_input_tokens: PositiveInt = 32000
    max_output_tokens: PositiveInt = 4000
    max_concurrency: PositiveInt = Field(default=4, le=4)
    native_structured_output: bool = False
    cache_path: Path = Path(".conformdag/semantic-cache.json")


class ProjectRuntimeConfig(ConformModel):
    enabled: bool = False
    airflow_version: AirflowProfile | None = None
    image: str | None = None
    network_enabled: bool = False
    timeout_seconds: PositiveInt = 300


class ProjectConfig(ConformModel):
    config_version: Literal["1"] = "1"
    scan: ProjectScanConfig = Field(default_factory=ProjectScanConfig)
    semantic: ProjectSemanticConfig = Field(default_factory=ProjectSemanticConfig)
    runtime: ProjectRuntimeConfig = Field(default_factory=ProjectRuntimeConfig)


# Preserve the pre-package wildcard-import surface, including incidental imports.
__all__ = [
    "annotations",
    "re",
    "datetime",
    "StrEnum",
    "Path",
    "Annotated",
    "Any",
    "Literal",
    "BaseModel",
    "ConfigDict",
    "Field",
    "NonNegativeInt",
    "PositiveInt",
    "field_validator",
    "ConformModel",
    "LifecycleStatus",
    "Severity",
    "EnforcementType",
    "FindingStatus",
    "AirflowProfile",
    "Confidence",
    "PolicySource",
    "Ownership",
    "PolicyScope",
    "ExceptionPolicy",
    "EnforcementConfig",
    "RequiredOwnerConfig",
    "RequiredTagsConfig",
    "ExecutionTimeoutConfig",
    "RetryBoundsConfig",
    "TopLevelIOConfig",
    "OperatorRule",
    "ForbiddenOperatorsConfig",
    "IdempotenceConfig",
    "OrchestrationBoundaryConfig",
    "SensitiveLoggingConfig",
    "StartDateFreshnessConfig",
    "CatchupPolicyConfig",
    "ModuleScopeVariablesConfig",
    "DynamicDagFactoryConfig",
    "RuffAirConfig",
    "ApprovedAbstractionsConfig",
    "PolicyConfiguration",
    "NoNewFindingsRule",
    "MaxSeverityRule",
    "MaxFindingsRule",
    "AlwaysBlockRule",
    "FailureRateRule",
    "GateRule",
    "QualityGate",
    "GateRuleResult",
    "GateResult",
    "Policy",
    "PolicyPack",
    "FindingEvidence",
    "FindingLocation",
    "RemediationAction",
    "RemediationTarget",
    "RemediationPayload",
    "Suppression",
    "SemanticAuditEvidence",
    "Finding",
    "RunIssue",
    "RuntimeObservation",
    "SemanticRunMetadata",
    "RunMetadata",
    "ScanReport",
    "RuntimeManifest",
    "SemanticRequest",
    "SemanticResponse",
    "ProjectScanConfig",
    "ProjectSemanticConfig",
    "ProjectRuntimeConfig",
    "ProjectConfig",
]
