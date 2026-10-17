"""Versioned public models shared by policy, scan, runtime, and report layers."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, field_validator

from .common import AirflowProfile, Confidence, ConformModel, EnforcementType, FindingStatus, LifecycleStatus, Severity
from .config import (
    ProjectConfig,
    ProjectRuntimeConfig,
    ProjectScanConfig,
    ProjectSemanticConfig,
)
from .findings import (
    Finding,
    FindingEvidence,
    FindingLocation,
    RemediationAction,
    RemediationPayload,
    RemediationTarget,
    Suppression,
)
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
from .report import (
    RunIssue,
    RunMetadata,
    ScanReport,
)
from .runtime import (
    RuntimeManifest,
    RuntimeObservation,
)
from .semantic import (
    SemanticAuditEvidence,
    SemanticRequest,
    SemanticResponse,
    SemanticRunMetadata,
)

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
