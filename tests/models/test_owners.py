"""Direct owner imports must be the same public class objects."""

from __future__ import annotations

import importlib

import pytest
from pydantic import TypeAdapter, ValidationError

import conformdag.models as facade


@pytest.mark.parametrize(
    ("owner", "names"),
    [
        ("common", "ConformModel LifecycleStatus Severity EnforcementType FindingStatus AirflowProfile Confidence"),
        (
            "gates",
            "NoNewFindingsRule MaxSeverityRule MaxFindingsRule AlwaysBlockRule FailureRateRule GateRule QualityGate GateRuleResult GateResult",
        ),
        (
            "policy",
            "PolicySource Ownership PolicyScope ExceptionPolicy EnforcementConfig RequiredOwnerConfig RequiredTagsConfig ExecutionTimeoutConfig RetryBoundsConfig TopLevelIOConfig OperatorRule ForbiddenOperatorsConfig IdempotenceConfig OrchestrationBoundaryConfig SensitiveLoggingConfig StartDateFreshnessConfig CatchupPolicyConfig ModuleScopeVariablesConfig DynamicDagFactoryConfig RuffAirConfig ApprovedAbstractionsConfig PolicyConfiguration Policy PolicyPack",
        ),
    ],
)
def test_model_owner_identity(owner: str, names: str) -> None:
    module = importlib.import_module(f"conformdag.models.{owner}")
    for name in names.split():
        assert getattr(module, name) is getattr(facade, name)


def test_gate_discriminator_keeps_tags_and_errors() -> None:
    gate = facade.QualityGate.model_validate({"id": "x", "rules": [{"type": "failure-rate", "max_percent": 12.5}]})
    assert gate.model_dump(mode="json")["rules"] == [{"type": "failure-rate", "max_percent": 12.5}]
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        facade.QualityGate.model_validate({"id": "x", "rules": [{"type": "mystery"}]})


def test_policy_union_order_and_validator_bindings() -> None:
    owner = importlib.import_module("conformdag.models.policy")
    assert owner.Policy.valid_tags.__func__ is facade.Policy.valid_tags.__func__
    assert owner.PolicyPack.unique_policy_ids.__func__ is facade.PolicyPack.unique_policy_ids.__func__
    schema = TypeAdapter(facade.PolicyConfiguration).json_schema()
    assert schema["oneOf"] == [
        {"$ref": f"#/$defs/{name}"}
        for name in (
            "RequiredOwnerConfig",
            "RequiredTagsConfig",
            "ExecutionTimeoutConfig",
            "RetryBoundsConfig",
            "TopLevelIOConfig",
            "ForbiddenOperatorsConfig",
            "IdempotenceConfig",
            "OrchestrationBoundaryConfig",
            "SensitiveLoggingConfig",
            "ApprovedAbstractionsConfig",
            "StartDateFreshnessConfig",
            "CatchupPolicyConfig",
            "ModuleScopeVariablesConfig",
            "DynamicDagFactoryConfig",
            "RuffAirConfig",
        )
    ]
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        TypeAdapter(facade.PolicyConfiguration).validate_python({"kind": "unknown"})
