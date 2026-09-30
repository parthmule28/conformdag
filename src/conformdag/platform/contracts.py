"""Canonical request and response contracts for the platform's HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from conformdag.application import coerce_platform_airflow_profile
from conformdag.models import (
    EnforcementConfig,
    ExceptionPolicy,
    FindingStatus,
    GateRule,
    LifecycleStatus,
    Ownership,
    PolicyConfiguration,
    PolicyScope,
    RemediationPayload,
    Severity,
)
from conformdag.platform.domain import ScanStatus


class PlatformResponse(BaseModel):
    """Strict base for wire responses; request DTO behavior remains unchanged."""

    model_config = ConfigDict(extra="forbid")


class RepositoryCreate(BaseModel):
    """Registration payload for one local DAG repository."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    path: str
    policy_pack: str | None = None
    airflow_profile: str | None = Field(default=None, max_length=32)

    @field_validator("airflow_profile")
    @classmethod
    def validate_airflow_profile(cls, value: str | None) -> str | None:
        coerce_platform_airflow_profile(value)
        return value


class WorkspaceLoadRequest(BaseModel):
    """Optional explicit path of the workspace file to register."""

    path: str | None = None


class PolicyVocabularyRequest(BaseModel):
    """Additive canonical vocabulary accepted by policy mutation requests."""

    deterministic_checks: list[str] | None = None
    configuration: dict[str, Any] | None = None


class PolicyUpsertRequest(PolicyVocabularyRequest):
    """Payload for creating or updating a policy in a pack.

    ``deterministic_checks`` and ``configuration`` are the canonical transport
    vocabulary. ``check_kind`` and ``check_config`` are retained as a beta
    compatibility view: ``check_kind`` means ``configuration.kind`` and never
    means a deterministic evaluator check.

    Editable fields are required. Contract metadata fields (``source_version``,
    ``ownership``, ``scope``, ``exceptions``, ``enforcement``, ``safe_path``)
    are optional: an existing policy keeps its persisted value when the request
    omits them, while a new policy must carry them completely. ``tags`` follows
    the preserve-on-omit rule; an explicit empty list clears the tags.
    """

    title: str
    version: str
    status: str
    severity: str
    check_kind: str | None = Field(
        default=None,
        deprecated=True,
        description="Compatibility alias for configuration.kind; never a deterministic check kind.",
    )
    check_config: dict[str, Any] | None = Field(
        default=None,
        deprecated=True,
        description="Compatibility alias for the canonical configuration object.",
    )
    source_document: str
    source_section: str
    invariant: str
    safe_path: str | None = None
    source_version: str | None = None
    ownership: dict[str, Any] | None = None
    scope: dict[str, Any] | None = None
    exceptions: dict[str, Any] | None = None
    enforcement: dict[str, Any] | None = None
    tags: list[str] | None = None


class SuppressionCreate(BaseModel):
    """Creation payload for an operational platform suppression."""

    policy_id: str
    fingerprint: str
    reason: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    expires_at: datetime


class SuppressionUpdate(BaseModel):
    """Editable fields for an existing platform suppression."""

    reason: str | None = None
    owner: str | None = None
    expires_at: datetime | None = None


class BaselineSetRequest(BaseModel):
    """Selection payload marking one scan as a repository's baseline."""

    scan_id: str


class GateUpsertRequest(BaseModel):
    """Payload for creating or replacing one quality gate in a pack."""

    rules: list[GateRule]


class HealthResponse(PlatformResponse):
    """Unauthenticated health-check response."""

    status: Literal["ok"]


class RepositoryRegistrationResponse(PlatformResponse):
    """Successful repository registration response."""

    id: str
    name: str


class WorkspaceLoadResponse(PlatformResponse):
    """Number of repositories registered from a workspace file."""

    repositories_registered: int = Field(ge=0)


class RepositoryResponse(PlatformResponse):
    """One repository as exposed by the repository listing API."""

    id: str
    name: str
    path: str
    policy_pack: str | None
    airflow_profile: str | None
    baseline_scan_id: str | None


class ScanTransitionResponse(PlatformResponse):
    """Queue or cancellation result for a scan."""

    scan_id: str
    status: ScanStatus


class ScanStatusResponse(PlatformResponse):
    """Persisted scan status and its completion summary."""

    scan_id: str
    repository_id: str
    status: ScanStatus
    created_at: datetime
    finished_at: datetime | None
    complete: bool | None
    result_fingerprint: str | None
    error: str | None
    gate_passed: bool | None


class ScanSummaryResponse(PlatformResponse):
    """One scan history entry plus completion and gate fields."""

    scan_id: str
    status: ScanStatus
    created_at: datetime
    finished_at: datetime | None
    result_fingerprint: str | None
    complete: bool | None
    gate_passed: bool | None
    artifact_available: bool


class BaselineResponse(PlatformResponse):
    """Repository baseline assignment response."""

    repository_id: str
    baseline_scan_id: str


class FindingResponse(PlatformResponse):
    """One normalized finding as exposed by the findings API."""

    policy_id: str
    policy_version: str
    status: FindingStatus
    severity: Severity
    file_path: str | None
    start_line: int | None
    end_line: int | None
    fingerprint: str
    explanation: str | None
    remediation: str | None
    fix: RemediationPayload | None
    suppressed: bool
    baseline_status: Literal["existing", "new"] | None


class SuppressionResponse(PlatformResponse):
    """One platform suppression as exposed by the suppression API."""

    id: str
    policy_id: str
    fingerprint: str
    reason: str
    owner: str
    created_at: datetime
    expires_at: datetime
    source: str


class PackSummaryResponse(PlatformResponse):
    """Summary metadata for one available policy pack."""

    name: str
    path: str
    id: str | None
    version: str | None
    policy_count: int
    error: str | None


class PackValidationResponse(PlatformResponse):
    """Policy-pack validation result."""

    valid: bool
    errors: list[str]


class PolicyVocabularyResponse(PlatformResponse):
    """Canonical policy vocabulary plus the beta compatibility projection."""

    deterministic_checks: list[str]
    configuration: PolicyConfiguration
    check_kind: str
    check_config: PolicyConfiguration


class PolicyResponse(PolicyVocabularyResponse):
    """Flattened, stable policy representation returned by the policy API."""

    id: str
    title: str
    version: str
    status: LifecycleStatus
    severity: Severity
    tags: list[str]
    source_document: str
    source_section: str
    source_version: str | None
    invariant: str
    safe_path: str | None
    ownership: Ownership
    scope: PolicyScope
    exceptions: ExceptionPolicy
    enforcement: EnforcementConfig


class GateResponse(PlatformResponse):
    """One quality gate as exposed by the gates API."""

    id: str
    rules: list[GateRule]


class PolicyMutationResponse(PlatformResponse):
    """Successful policy save or delete result."""

    status: Literal["saved", "deleted"]
    policy_id: str


class GateMutationResponse(PlatformResponse):
    """Successful quality-gate save or delete result."""

    status: Literal["saved", "deleted"]
    gate_id: str


class TrendPoint(PlatformResponse):
    """One UTC-day trend bucket derived only from completed scans."""

    date: date
    completed_scan_count: int
    fail_finding_count: int
    error_finding_count: int
    suppressed_finding_count: int
    new_finding_count: int


class OverviewScan(PlatformResponse):
    """One recent scan summary on the overview surface."""

    scan_id: str
    repository_id: str
    repository_name: str
    status: ScanStatus
    created_at: datetime
    finished_at: datetime | None
    complete: bool | None
    gate_passed: bool | None


class OverviewResponse(PlatformResponse):
    """Read-only overview aggregates across registered repositories."""

    repository_count: int
    completed_scan_count: int
    active_scan_count: int
    current_failure_count: int
    current_error_count: int
    current_new_finding_count: int
    trends: list[TrendPoint]
    recent_scans: list[OverviewScan]


class RepositoryTrendsResponse(PlatformResponse):
    """Read-only daily trend points for one repository."""

    repository_id: str
    points: list[TrendPoint]
