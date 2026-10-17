"""Policy, policy-configuration, and policy-pack values."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, field_validator

from .common import AirflowProfile, ConformModel, EnforcementType, LifecycleStatus, Severity
from .gates import QualityGate

_POLICY_TAG_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?")


def _empty_airflow_profiles() -> list[AirflowProfile]:
    return []


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


class StartDateFreshnessConfig(ConformModel):
    kind: Literal["start-date-freshness"] = "start-date-freshness"
    max_age_years: int = Field(default=2, ge=1)
    require_timezone: bool = True


class CatchupPolicyConfig(ConformModel):
    kind: Literal["catchup-policy"] = "catchup-policy"
    allow_catchup: bool = False


class ModuleScopeVariablesConfig(ConformModel):
    kind: Literal["module-scope-variables"] = "module-scope-variables"
    patterns: list[str] = Field(default_factory=lambda: ["Variable.get"])


class DynamicDagFactoryConfig(ConformModel):
    kind: Literal["dynamic-dag-factory"] = "dynamic-dag-factory"
    allow: bool = False


class RuffAirConfig(ConformModel):
    kind: Literal["ruff-air"] = "ruff-air"
    rules: list[str] = Field(min_length=1)


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
    | ApprovedAbstractionsConfig
    | StartDateFreshnessConfig
    | CatchupPolicyConfig
    | ModuleScopeVariablesConfig
    | DynamicDagFactoryConfig
    | RuffAirConfig,
    Field(discriminator="kind"),
]


def _empty_quality_gates() -> list[QualityGate]:
    return []


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
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, tags: list[str]) -> list[str]:
        seen: set[str] = set()
        for tag in tags:
            if not _POLICY_TAG_PATTERN.fullmatch(tag):
                raise ValueError(
                    f"tag {tag!r} must be a lowercase slug of 1-32 alphanumeric characters with inner hyphens"
                )
            if tag in seen:
                raise ValueError(f"tag {tag!r} is duplicated; tags must be unique")
            seen.add(tag)
        return tags


class PolicyPack(ConformModel):
    schema_version: Literal["1"] = "1"
    id: str
    version: str
    policies: list[Policy]
    quality_gates: list[QualityGate] = Field(default_factory=_empty_quality_gates)

    @field_validator("policies")
    @classmethod
    def unique_policy_ids(cls, policies: list[Policy]) -> list[Policy]:
        ids = [policy.id for policy in policies]
        if len(ids) != len(set(ids)):
            raise ValueError("policy IDs must be unique within a pack")
        return policies
