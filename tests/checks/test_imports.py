"""Import and identity contracts for the modular deterministic checks."""

import importlib
from collections.abc import Mapping
from typing import Any

import pytest

from conformdag import evaluator
from conformdag.checks import common, registry


EVALUATOR_OWNERS: Mapping[str, str] = {
    "OwnerEvaluator": "conformdag.checks.airflow.metadata",
    "TagEvaluator": "conformdag.checks.airflow.metadata",
    "TimeoutEvaluator": "conformdag.checks.airflow.scheduling",
    "RetryEvaluator": "conformdag.checks.airflow.scheduling",
    "StartDateFreshnessEvaluator": "conformdag.checks.airflow.scheduling",
    "CatchupPolicyEvaluator": "conformdag.checks.airflow.scheduling",
    "TopLevelIOEvaluator": "conformdag.checks.airflow.safety",
    "ForbiddenOperatorEvaluator": "conformdag.checks.airflow.safety",
    "ModuleScopeVariablesEvaluator": "conformdag.checks.airflow.safety",
    "SensitiveLoggingEvaluator": "conformdag.checks.airflow.safety",
    "DynamicDagFactoryEvaluator": "conformdag.checks.airflow.safety",
    "RuffAirEvaluator": "conformdag.checks.airflow.safety",
}


@pytest.mark.parametrize(("name", "module_name"), EVALUATOR_OWNERS.items())
def test_facade_reexports_the_single_family_class(name: str, module_name: str) -> None:
    facade_class = getattr(evaluator, name)
    family_class = getattr(importlib.import_module(module_name), name)

    assert facade_class is family_class
    assert facade_class().policy_id.startswith("AIR-DET-")


@pytest.mark.parametrize(
    "name",
    (
        "EvaluationContext",
        "DeterministicEvaluator",
        "fix_target",
        "policy_applies",
        "redact_evidence",
        "structural_fingerprint",
    ),
)
def test_facade_reexports_common_contracts(name: str) -> None:
    assert getattr(evaluator, name) is getattr(common, name)


@pytest.mark.parametrize(
    "name",
    (
        "CHECK_CONFIGURATION_KINDS",
        "CHECK_EVALUATORS",
        "LEGACY_POLICY_CONFIGURATION_KINDS",
        "LEGACY_POLICY_EVALUATORS",
    ),
)
def test_facade_registry_views_are_authoritative(name: str) -> None:
    facade_view: Any = getattr(evaluator, name)
    registry_view: Any = getattr(registry, name)

    assert facade_view is registry_view
