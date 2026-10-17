"""Frozen C21 characterization of the legacy models import and wire surface."""

from __future__ import annotations

import hashlib
import importlib
import json
import pickle
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import conformdag.models as models

EXPORTS = [
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

SCHEMA_HASHES = {
    "policy-pack": "dd6d7a46ada43036b37bdac53df158635f76bd64f1d309993c90ba286ccef143",
    "project-config": "7915a1880b803447c3d634d3be8d90d813898e6a15663ea338685b4c8ba35f3a",
    "runtime-manifest": "471a3e650fb037afd1d6993aae5d93e1552ceab552ff9422810e4ffc149779de",
    "scan-report": "ae1a33e78e0ab5a72a13f629cbcd91de6e3f64baf34af99e47142a2616486695",
    "semantic-request": "e63906384ae7bf2e450095481b4d7df43276277a64dbafe5e9c52379c8e3d59f",
    "semantic-response": "b26267fa206e994ccfd741c903a35ae2d222ff475416d86d195b47e35cefec75",
    "suppression": "0ef3eb979cb76d384db1407edca057485069031dc6a8d2086244b17166bdd529",
}

# Generated with Python 3.12 pickle protocol 4 from the unmodified legacy module.
LEGACY_SEVERITY_PICKLE = bytes.fromhex(
    "8004952d000000000000008c11636f6e666f726d6461672e6d6f64656c73948c0853657665726974799493948c046869676894859452942e"
)
LEGACY_MODEL_PICKLE = bytes.fromhex(
    "80049585000000000000008c11636f6e666f726d6461672e6d6f64656c73948c0c436f6e666f726d4d6f64656c9493942981947d94288c085f5f646963745f5f947d948c125f5f707964616e7469635f65787472615f5f944e8c175f5f707964616e7469635f6669656c64735f7365745f5f948f948c145f5f707964616e7469635f707269766174655f5f944e75622e"
)


def test_legacy_public_surface_and_star_bindings() -> None:
    assert models.__all__ == EXPORTS
    assert all(name in vars(models) for name in EXPORTS)
    namespace: dict[str, Any] = {}
    exec("from conformdag.models import *", namespace)  # noqa: S102 - exercise legacy import syntax
    assert list(namespace)[1:] == EXPORTS
    for name in EXPORTS:
        assert namespace[name] is getattr(models, name)
    for name in (
        "ConformModel",
        "Severity",
        "GateRule",
        "Policy",
        "SemanticRequest",
        "Finding",
        "ScanReport",
        "RuntimeManifest",
        "ProjectConfig",
    ):
        assert getattr(importlib.import_module("conformdag.models"), name) is getattr(models, name)


def test_legacy_pickle_globals_load() -> None:
    assert pickle.loads(LEGACY_SEVERITY_PICKLE) is models.Severity.HIGH  # noqa: S301 - trusted frozen fixture
    assert type(pickle.loads(LEGACY_MODEL_PICKLE)) is models.ConformModel  # noqa: S301 - trusted fixture


@pytest.mark.parametrize(("name", "digest"), SCHEMA_HASHES.items())
def test_schema_bytes_and_live_render_match_legacy(name: str, digest: str) -> None:
    schema_bytes = (Path(__file__).resolve().parents[2] / "schemas" / f"{name}.json").read_bytes()
    assert hashlib.sha256(schema_bytes).hexdigest() == digest
    model = {
        "policy-pack": models.PolicyPack,
        "project-config": models.ProjectConfig,
        "runtime-manifest": models.RuntimeManifest,
        "scan-report": models.ScanReport,
        "semantic-request": models.SemanticRequest,
        "semantic-response": models.SemanticResponse,
        "suppression": models.Suppression,
    }[name]
    assert (json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n").encode() == schema_bytes


def test_legacy_defaults_discriminators_and_validation() -> None:
    assert list(models.Policy.model_fields)[:5] == ["id", "title", "version", "status", "severity"]
    first = models.ProjectConfig()
    second = models.ProjectConfig()
    first.scan.include.append("extra.py")
    assert second.scan.include == ["dags/**/*.py"]
    gate = models.QualityGate.model_validate({"id": "x", "rules": [{"type": "max-severity", "severity": "high"}]})
    assert gate.model_dump(mode="json")["rules"] == [{"type": "max-severity", "severity": "high"}]
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        models.QualityGate.model_validate({"id": "x", "rules": [{"type": "unknown"}]})
