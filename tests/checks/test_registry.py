"""Contract tests for the authoritative check catalogue."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Final

import pytest
from conformdag.checks import registry
from pydantic import TypeAdapter

from conformdag.fixing.codemods import (
    AUTOFIX_KINDS,
    FIXERS,
    MANUAL_KINDS,
    PROPOSED_ONLY_KINDS,
)
from conformdag.models import PolicyConfiguration

EXPECTED_FIX_KINDS: Final[dict[str, str]] = {
    "effective-owner": "required-owner",
    "tags": "required-tags",
    "effective-timeout": "execution-timeout",
    "retry-bounds": "retry-bounds",
    "module-scope-io": "top-level-io",
    "operator-allow-list": "forbidden-operators",
    "start-date-freshness": "start-date-freshness",
    "catchup-policy": "catchup-policy",
    "module-scope-variables": "module-scope-variables",
    "sensitive-logging": "sensitive-logging",
    "dynamic-dag-factory": "dynamic-dag-factory",
    "ruff-air": "ruff-air",
    "idempotence": "idempotence",
    "orchestration-boundary": "orchestration-boundary",
    "approved-abstractions": "approved-abstractions",
}
EXECUTABLE_KINDS: Final[tuple[str, ...]] = tuple(EXPECTED_FIX_KINDS)[:12]
NON_EXECUTABLE_KINDS: Final[frozenset[str]] = frozenset(EXPECTED_FIX_KINDS) - set(EXECUTABLE_KINDS)
NON_EXECUTABLE_ORDER: Final[tuple[str, ...]] = (
    "idempotence",
    "orchestration-boundary",
    "approved-abstractions",
)

EXPECTED_FIXABILITIES: Final[dict[str, registry.Fixability]] = {
    "effective-owner": registry.Fixability.AUTOFIX,
    "tags": registry.Fixability.AUTOFIX,
    "effective-timeout": registry.Fixability.AUTOFIX,
    "retry-bounds": registry.Fixability.AUTOFIX,
    "module-scope-io": registry.Fixability.PROPOSED_ONLY,
    "operator-allow-list": registry.Fixability.MANUAL,
    "start-date-freshness": registry.Fixability.MANUAL,
    "catchup-policy": registry.Fixability.AUTOFIX,
    "module-scope-variables": registry.Fixability.MANUAL,
    "sensitive-logging": registry.Fixability.MANUAL,
    "dynamic-dag-factory": registry.Fixability.MANUAL,
    "ruff-air": registry.Fixability.MANUAL,
    "idempotence": registry.Fixability.MANUAL,
    "orchestration-boundary": registry.Fixability.MANUAL,
    "approved-abstractions": registry.Fixability.MANUAL,
}

EXPECTED_LEGACY_POLICY_CHECKS: Final[dict[str, str]] = {
    "AIR-DET-001": "effective-owner",
    "AIR-DET-002": "tags",
    "AIR-DET-003": "effective-timeout",
    "AIR-DET-004": "retry-bounds",
    "AIR-DET-005": "module-scope-io",
    "AIR-DET-006": "operator-allow-list",
    "AIR-DET-012": "ruff-air",
}

EXPECTED_SCAFFOLDS: Final[dict[str, dict[str, object]]] = {
    "effective-owner": {"kind": "required-owner", "allowed_values": ["platform"]},
    "tags": {
        "kind": "required-tags",
        "required_keys": ["domain", "owner"],
        "allowed_values": {"domain": ["data", "analytics", "platform"]},
    },
    "effective-timeout": {
        "kind": "execution-timeout",
        "min_seconds": 1,
        "max_seconds": 86400,
        "approved_default_seconds": 3600,
    },
    "retry-bounds": {
        "kind": "retry-bounds",
        "min_retries": 0,
        "max_retries": 5,
        "min_delay_seconds": 0,
        "max_delay_seconds": 3600,
        "allow_zero_retries": True,
    },
    "module-scope-io": {
        "kind": "top-level-io",
        "forbidden_calls": ["requests.get", "boto3.client", "subprocess.run"],
        "uncertain_as_review": True,
    },
    "operator-allow-list": {
        "kind": "forbidden-operators",
        "operators": {"airflow.operators.python.PythonOperator": "use-taskflow"},
    },
    "start-date-freshness": {"kind": "start-date-freshness", "max_age_years": 2, "require_timezone": True},
    "catchup-policy": {"kind": "catchup-policy", "allow_catchup": False},
    "module-scope-variables": {"kind": "module-scope-variables", "patterns": ["Variable.get"]},
    "sensitive-logging": {
        "kind": "sensitive-logging",
        "secret_patterns": ["password", "token", "secret"],
        "logging_calls": ["logging.info", "logging.warning", "logging.error"],
    },
    "dynamic-dag-factory": {"kind": "dynamic-dag-factory", "allow": False},
    "ruff-air": {"kind": "ruff-air", "rules": ["AIR001", "AIR002", "AIR301", "AIR302", "AIR311", "AIR312"]},
}

_CONFIGURATION_ADAPTER = TypeAdapter(PolicyConfiguration)


def _assert_mutable_containers_are_distinct(left: object, right: object) -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        assert left is not right
        assert left.keys() == right.keys()
        for key in left:
            _assert_mutable_containers_are_distinct(left[key], right[key])
    elif isinstance(left, list) and isinstance(right, list):
        assert left is not right
        assert len(left) == len(right)
        for left_item, right_item in zip(left, right, strict=True):
            _assert_mutable_containers_are_distinct(left_item, right_item)


def test_catalogue_contains_all_known_kinds_in_stable_order() -> None:
    assert tuple(registry.CHECK_SPECS) == (*EXECUTABLE_KINDS, *NON_EXECUTABLE_ORDER)
    assert set(NON_EXECUTABLE_ORDER) == NON_EXECUTABLE_KINDS
    assert {spec.kind for spec in registry.CHECK_SPECS.values()} == set(EXPECTED_FIX_KINDS)
    assert {kind: spec.fix_kind for kind, spec in registry.CHECK_SPECS.items()} == EXPECTED_FIX_KINDS
    assert {kind: spec.fixability for kind, spec in registry.CHECK_SPECS.items()} == EXPECTED_FIXABILITIES


def test_derived_views_expose_only_executable_entries() -> None:
    assert tuple(registry.CHECK_EVALUATORS) == EXECUTABLE_KINDS
    assert tuple(registry.CHECK_CONFIGURATION_KINDS) == EXECUTABLE_KINDS
    assert all(registry.CHECK_SPECS[kind].evaluator is not None for kind in EXECUTABLE_KINDS)
    assert all(registry.CHECK_SPECS[kind].scaffold_factory is not None for kind in EXECUTABLE_KINDS)
    assert all(registry.CHECK_SPECS[kind].evaluator is None for kind in NON_EXECUTABLE_KINDS)
    assert all(kind not in registry.CHECK_EVALUATORS for kind in NON_EXECUTABLE_KINDS)
    assert all(kind not in registry.CHECK_CONFIGURATION_KINDS for kind in NON_EXECUTABLE_KINDS)


def test_fixability_views_are_derived_from_fix_kind() -> None:
    expected = {
        registry.Fixability.AUTOFIX: frozenset(
            EXPECTED_FIX_KINDS[kind]
            for kind, fixability in EXPECTED_FIXABILITIES.items()
            if fixability is registry.Fixability.AUTOFIX
        ),
        registry.Fixability.PROPOSED_ONLY: frozenset(
            EXPECTED_FIX_KINDS[kind]
            for kind, fixability in EXPECTED_FIXABILITIES.items()
            if fixability is registry.Fixability.PROPOSED_ONLY
        ),
        registry.Fixability.MANUAL: frozenset(
            EXPECTED_FIX_KINDS[kind]
            for kind, fixability in EXPECTED_FIXABILITIES.items()
            if fixability is registry.Fixability.MANUAL
        ),
    }
    assert expected[registry.Fixability.AUTOFIX] == AUTOFIX_KINDS
    assert expected[registry.Fixability.PROPOSED_ONLY] == PROPOSED_ONLY_KINDS
    assert expected[registry.Fixability.MANUAL] == MANUAL_KINDS
    assert AUTOFIX_KINDS.isdisjoint(PROPOSED_ONLY_KINDS)
    assert AUTOFIX_KINDS.isdisjoint(MANUAL_KINDS)
    assert PROPOSED_ONLY_KINDS.isdisjoint(MANUAL_KINDS)
    assert frozenset(EXPECTED_FIX_KINDS.values()) == AUTOFIX_KINDS | PROPOSED_ONLY_KINDS | MANUAL_KINDS


def test_legacy_views_match_catalogue_policy_ids() -> None:
    assert registry.LEGACY_POLICY_CHECKS == EXPECTED_LEGACY_POLICY_CHECKS
    legacy_policy_ids = [policy_id for spec in registry.CHECK_SPECS.values() for policy_id in spec.legacy_policy_ids]
    assert len(legacy_policy_ids) == len(set(legacy_policy_ids))
    assert set(legacy_policy_ids) == set(EXPECTED_LEGACY_POLICY_CHECKS)
    for policy_id, kind in EXPECTED_LEGACY_POLICY_CHECKS.items():
        spec = registry.CHECK_SPECS[kind]
        assert registry.LEGACY_POLICY_EVALUATORS[policy_id] is spec.evaluator
        assert registry.LEGACY_POLICY_CONFIGURATION_KINDS[policy_id] == spec.configuration_kind


def test_scaffolds_are_fresh_and_schema_valid() -> None:
    for kind in EXECUTABLE_KINDS:
        spec = registry.CHECK_SPECS[kind]
        assert spec.scaffold_factory is not None
        first = spec.scaffold_factory()
        second = spec.scaffold_factory()
        assert first == EXPECTED_SCAFFOLDS[kind]
        assert second == EXPECTED_SCAFFOLDS[kind]
        _assert_mutable_containers_are_distinct(first, second)
        assert _CONFIGURATION_ADAPTER.validate_python(first).kind == spec.configuration_kind
        assert _CONFIGURATION_ADAPTER.validate_python(second).kind == spec.configuration_kind


def test_fixers_match_catalogue_fixability() -> None:
    for spec in registry.CHECK_SPECS.values():
        if spec.fixability in {registry.Fixability.AUTOFIX, registry.Fixability.PROPOSED_ONLY}:
            assert spec.fix_kind in FIXERS
        else:
            assert spec.fix_kind not in FIXERS


def test_unknown_catalogue_kind_has_a_clear_lookup_error() -> None:
    with pytest.raises(KeyError, match="does-not-exist"):
        registry.check_spec("does-not-exist")


def _run_import_order(order: str) -> None:
    script = dedent(
        f"""
        from pathlib import Path

        from conformdag.models import (
            EnforcementConfig,
            EnforcementType,
            LifecycleStatus,
            Ownership,
            Policy,
            PolicySource,
            RequiredOwnerConfig,
            Severity,
        )

        if {order!r} == "registry-first":
            import conformdag.checks.registry as registry
            from conformdag.evaluator import (
                CHECK_CONFIGURATION_KINDS,
                CHECK_EVALUATORS,
                LEGACY_POLICY_CONFIGURATION_KINDS,
                LEGACY_POLICY_EVALUATORS,
                evaluate_deterministic,
            )
        else:
            import conformdag.evaluator
            import conformdag.checks.registry as registry
            from conformdag.evaluator import (
                CHECK_CONFIGURATION_KINDS,
                CHECK_EVALUATORS,
                LEGACY_POLICY_CONFIGURATION_KINDS,
                LEGACY_POLICY_EVALUATORS,
                evaluate_deterministic,
            )

        spec = registry.check_spec("effective-owner")
        assert spec.evaluator is registry.CHECK_EVALUATORS["effective-owner"]
        assert CHECK_EVALUATORS is registry.CHECK_EVALUATORS
        assert CHECK_CONFIGURATION_KINDS is registry.CHECK_CONFIGURATION_KINDS
        assert LEGACY_POLICY_EVALUATORS is registry.LEGACY_POLICY_EVALUATORS
        assert LEGACY_POLICY_CONFIGURATION_KINDS is registry.LEGACY_POLICY_CONFIGURATION_KINDS
        policy = Policy.model_construct(
            id="AIR-TST-001",
            title="Owner",
            version="1.0.0",
            status=LifecycleStatus.ACTIVE,
            severity=Severity.MEDIUM,
            airflow_profiles=[],
            ownership=Ownership(owner="platform"),
            source=PolicySource(document=Path("standards.md"), section="Owners", content_hash="hash"),
            invariant="An owner is present.",
            safe_path="Add an owner.",
            enforcement=EnforcementConfig(
                type=EnforcementType.DETERMINISTIC,
                deterministic_checks=["effective-owner"],
                blocking=True,
            ),
            configuration=RequiredOwnerConfig(allowed_values=["platform"]),
        )
        findings, evaluated, skipped = evaluate_deterministic([policy], [])
        assert findings == []
        assert evaluated == ["AIR-TST-001"]
        assert skipped == []
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("order", ["registry-first", "evaluator-first"])
def test_registry_and_evaluator_import_orders_execute_catalogue_lookup(order: str) -> None:
    _run_import_order(order)
