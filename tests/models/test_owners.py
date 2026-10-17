"""Direct owner imports must be the same public class objects."""

from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

import conformdag.models as facade


@pytest.mark.parametrize(
    ("owner", "names"),
    [
        ("common", "ConformModel LifecycleStatus Severity EnforcementType FindingStatus AirflowProfile Confidence"),
        (
            "gates",
            "NoNewFindingsRule MaxSeverityRule MaxFindingsRule AlwaysBlockRule FailureRateRule GateRule QualityGate GateRuleResult GateResult",
        ),
    ],
)
def test_common_and_gate_owner_identity(owner: str, names: str) -> None:
    module = importlib.import_module(f"conformdag.models.{owner}")
    for name in names.split():
        assert getattr(module, name) is getattr(facade, name)


def test_gate_discriminator_keeps_tags_and_errors() -> None:
    gate = facade.QualityGate.model_validate({"id": "x", "rules": [{"type": "failure-rate", "max_percent": 12.5}]})
    assert gate.model_dump(mode="json")["rules"] == [{"type": "failure-rate", "max_percent": 12.5}]
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        facade.QualityGate.model_validate({"id": "x", "rules": [{"type": "mystery"}]})
