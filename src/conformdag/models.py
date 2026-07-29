"""Versioned public models shared by policy, scan, runtime, and report layers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, field_validator


def _empty_airflow_profiles() -> list[AirflowProfile]:
    return []


def _empty_paths() -> list[Path]:
    return []


def _empty_findings() -> list[Finding]:
    return []


def _empty_issues() -> list[RunIssue]:
    return []


class ConformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    CONFLICTED = "CONFLICTED"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EnforcementType(StrEnum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class FindingStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class AirflowProfile(StrEnum):
    AIRFLOW_2_11_2 = "2.11.2"
    AIRFLOW_3_3_0 = "3.3.0"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PolicySource(ConformModel):
    document: Path
    section: str
    version: str | None = None
    content_hash: str


class Ownership(ConformModel):
    owner: str
    approvers: list[str] = Field(default_factory=list)
    approved_at: datetime | None = None
    review_before: datetime | None = None
    expires_at: datetime | None = None


class PolicyScope(ConformModel):
    files: list[str] = Field(default_factory=lambda: ["dags/**/*.py"])
    operators: list[str] = Field(default_factory=list)


class ExceptionPolicy(ConformModel):
    require_reason: bool = True
    require_expiry: bool = True


class EnforcementConfig(ConformModel):
    type: EnforcementType
    deterministic_checks: list[str] = Field(default_factory=list)
    model_check: bool = False
    allow_abstention: bool = True
    blocking: bool = False


class RequiredOwnerConfig(ConformModel):
    kind: Literal["required-owner"] = "required-owner"
    allowed_values: list[str] = Field(default_factory=lambda: [])
    allowed_pattern: str | None = None


class RequiredTagsConfig(ConformModel):
    kind: Literal["required-tags"] = "required-tags"
    required_keys: list[str] = Field(default_factory=lambda: [])
    allowed_values: dict[str, list[str]] = Field(default_factory=lambda: {})


class ExecutionTimeoutConfig(ConformModel):
    kind: Literal["execution-timeout"] = "execution-timeout"
    min_seconds: NonNegativeInt | None = None
    max_seconds: PositiveInt | None = None
    approved_default_seconds: PositiveInt | None = None


class RetryBoundsConfig(ConformModel):
    kind: Literal["retry-bounds"] = "retry-bounds"
    min_retries: NonNegativeInt = 0
    max_retries: NonNegativeInt
    min_delay_seconds: NonNegativeInt = 0
    max_delay_seconds: PositiveInt | None = None
    allow_zero_retries: bool = True


class TopLevelIOConfig(ConformModel):
    kind: Literal["top-level-io"] = "top-level-io"
    forbidden_calls: list[str] = Field(default_factory=lambda: [])
    uncertain_as_review: bool = True


class OperatorRule(ConformModel):
    replacement: str
    airflow_profiles: list[AirflowProfile] = Field(default_factory=_empty_airflow_profiles)
    min_airflow_version: str | None = None
    max_airflow_version: str | None = None


class ForbiddenOperatorsConfig(ConformModel):
    kind: Literal["forbidden-operators"] = "forbidden-operators"
    operators: dict[str, str | OperatorRule] = Field(default_factory=lambda: {})


class IdempotenceConfig(ConformModel):
    kind: Literal["idempotence"] = "idempotence"
    external_write_markers: list[str] = Field(default_factory=lambda: [])


class OrchestrationBoundaryConfig(ConformModel):
    kind: Literal["orchestration-boundary"] = "orchestration-boundary"
    max_statements: PositiveInt | None = None
    max_complexity: PositiveInt | None = None
    signal_patterns: list[str] = Field(default_factory=lambda: [])


class SensitiveLoggingConfig(ConformModel):
    kind: Literal["sensitive-logging"] = "sensitive-logging"
    secret_patterns: list[str] = Field(default_factory=lambda: [])
    logging_calls: list[str] = Field(default_factory=lambda: [])


class ApprovedAbstractionsConfig(ConformModel):
    kind: Literal["approved-abstractions"] = "approved-abstractions"
    abstractions: dict[str, str] = Field(default_factory=lambda: {})


PolicyConfiguration = Annotated[
    RequiredOwnerConfig
    | RequiredTagsConfig
    | ExecutionTimeoutConfig
    | RetryBoundsConfig
    | TopLevelIOConfig
    | ForbiddenOperatorsConfig
    | IdempotenceConfig
    | OrchestrationBoundaryConfig
    | SensitiveLoggingConfig
    | ApprovedAbstractionsConfig,
    Field(discriminator="kind"),
]


class Policy(ConformModel):
    id: str = Field(pattern=r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
    title: str
    version: str
    status: LifecycleStatus
    severity: Severity
    airflow_profiles: list[AirflowProfile] = Field(default_factory=_empty_airflow_profiles)
    scope: PolicyScope = Field(default_factory=PolicyScope)
    ownership: Ownership
    source: PolicySource
    invariant: str
    safe_path: str | None = None
    enforcement: EnforcementConfig
    exceptions: ExceptionPolicy = Field(default_factory=ExceptionPolicy)
    configuration: PolicyConfiguration


class PolicyPack(ConformModel):
    schema_version: Literal["1"] = "1"
    id: str
    version: str
    policies: list[Policy]

    @field_validator("policies")
    @classmethod
    def unique_policy_ids(cls, policies: list[Policy]) -> list[Policy]:
        ids = [policy.id for policy in policies]
        if len(ids) != len(set(ids)):
            raise ValueError("policy IDs must be unique within a pack")
        return policies


class FindingEvidence(ConformModel):
    text: str
    start_line: PositiveInt | None = None
    end_line: PositiveInt | None = None
    code_hash: str | None = None


class FindingLocation(ConformModel):
    file: Path | None = None
    start_line: PositiveInt | None = None
    end_line: PositiveInt | None = None


class Suppression(ConformModel):
    fingerprint: str
    policy_id: str
    reason: str
    owner: str
    created_at: datetime
    expires_at: datetime


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
    fingerprint: str
    suppressed: bool = False
    suppression: Suppression | None = None


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
    resolved_configuration: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime


class ScanReport(ConformModel):
    report_version: Literal["1"] = "1"
    complete: bool
    result_fingerprint: str
    files_scanned: list[Path] = Field(default_factory=_empty_paths)
    policies_evaluated: list[str] = Field(default_factory=list)
    policies_skipped: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=_empty_findings)
    issues: list[RunIssue] = Field(default_factory=_empty_issues)
    run: RunMetadata


class RuntimeManifest(ConformModel):
    schema_version: Literal["1"] = "1"
    repository_root: Path
    include: list[str]
    exclude: list[str]
    policy_ids: list[str]
    airflow_profile: AirflowProfile | None = None
    image: str | None = None
    network_enabled: bool = False
    timeout_seconds: PositiveInt = 300


class RuntimeObservation(ConformModel):
    schema_version: Literal["1"] = "1"
    status: FindingStatus
    policy_id: str
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SemanticRequest(ConformModel):
    policy_id: str
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


class ProjectScanConfig(ConformModel):
    policy_pack: Path = Path("policies/pack.yaml")
    include: list[str] = Field(default_factory=lambda: ["dags/**/*.py"])
    exclude: list[str] = Field(
        default_factory=lambda: ["**/.venv/**", "**/.git/**", "**/vendor/**", "**/generated/**"]
    )
    follow_internal_symlinks: bool = False


class ProjectSemanticConfig(ConformModel):
    enabled: bool = False
    base_url: str | None = None
    model: str | None = None
    api_key_env: str = "CONFORMDAG_MODEL_API_KEY"
    temperature: float = 0.0
    max_input_tokens: PositiveInt = 32000
    max_output_tokens: PositiveInt = 4000
    max_concurrency: PositiveInt = 4


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
