"""Authoritative metadata catalogue for deterministic and semantic checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from conformdag.checks.common import DeterministicEvaluator


class Fixability(StrEnum):
    """Compatibility classification for a remediation vocabulary value."""

    AUTOFIX = "autofix"
    PROPOSED_ONLY = "proposed-only"
    MANUAL = "manual"


ScaffoldFactory = Callable[[], dict[str, object]]


@dataclass(frozen=True)
class CheckSpec:
    """Complete metadata for one known check/configuration kind."""

    kind: str
    configuration_kind: str
    evaluator: DeterministicEvaluator | None
    fixability: Fixability
    fix_kind: str
    scaffold_factory: ScaffoldFactory | None
    legacy_policy_ids: tuple[str, ...]


RUFF_AIR_RULES: Final[tuple[str, ...]] = (
    "AIR001",
    "AIR002",
    "AIR301",
    "AIR302",
    "AIR311",
    "AIR312",
)


def _required_owner_scaffold() -> dict[str, object]:
    return {"kind": "required-owner", "allowed_values": ["platform"]}


def _required_tags_scaffold() -> dict[str, object]:
    return {
        "kind": "required-tags",
        "required_keys": ["domain", "owner"],
        "allowed_values": {"domain": ["data", "analytics", "platform"]},
    }


def _execution_timeout_scaffold() -> dict[str, object]:
    return {
        "kind": "execution-timeout",
        "min_seconds": 1,
        "max_seconds": 86400,
        "approved_default_seconds": 3600,
    }


def _retry_bounds_scaffold() -> dict[str, object]:
    return {
        "kind": "retry-bounds",
        "min_retries": 0,
        "max_retries": 5,
        "min_delay_seconds": 0,
        "max_delay_seconds": 3600,
        "allow_zero_retries": True,
    }


def _top_level_io_scaffold() -> dict[str, object]:
    return {
        "kind": "top-level-io",
        "forbidden_calls": ["requests.get", "boto3.client", "subprocess.run"],
        "uncertain_as_review": True,
    }


def _forbidden_operators_scaffold() -> dict[str, object]:
    return {
        "kind": "forbidden-operators",
        "operators": {"airflow.operators.python.PythonOperator": "use-taskflow"},
    }


def _start_date_freshness_scaffold() -> dict[str, object]:
    return {"kind": "start-date-freshness", "max_age_years": 2, "require_timezone": True}


def _catchup_policy_scaffold() -> dict[str, object]:
    return {"kind": "catchup-policy", "allow_catchup": False}


def _module_scope_variables_scaffold() -> dict[str, object]:
    return {"kind": "module-scope-variables", "patterns": ["Variable.get"]}


def _sensitive_logging_scaffold() -> dict[str, object]:
    return {
        "kind": "sensitive-logging",
        "secret_patterns": ["password", "token", "secret"],
        "logging_calls": ["logging.info", "logging.warning", "logging.error"],
    }


def _dynamic_dag_factory_scaffold() -> dict[str, object]:
    return {"kind": "dynamic-dag-factory", "allow": False}


def _ruff_air_scaffold() -> dict[str, object]:
    return {"kind": "ruff-air", "rules": list(RUFF_AIR_RULES)}


def _build_check_specs() -> dict[str, CheckSpec]:
    """Build the catalogue after evaluator definitions are available."""
    from conformdag.checks.airflow.metadata import (
        OwnerEvaluator,
        TagEvaluator,
    )
    from conformdag.checks.airflow.safety import (
        DynamicDagFactoryEvaluator,
        ForbiddenOperatorEvaluator,
        ModuleScopeVariablesEvaluator,
        RuffAirEvaluator,
        SensitiveLoggingEvaluator,
        TopLevelIOEvaluator,
    )
    from conformdag.checks.airflow.scheduling import (
        CatchupPolicyEvaluator,
        RetryEvaluator,
        StartDateFreshnessEvaluator,
        TimeoutEvaluator,
    )

    return {
        "effective-owner": CheckSpec(
            kind="effective-owner",
            configuration_kind="required-owner",
            evaluator=OwnerEvaluator(),
            fixability=Fixability.AUTOFIX,
            fix_kind="required-owner",
            scaffold_factory=_required_owner_scaffold,
            legacy_policy_ids=("AIR-DET-001",),
        ),
        "tags": CheckSpec(
            kind="tags",
            configuration_kind="required-tags",
            evaluator=TagEvaluator(),
            fixability=Fixability.AUTOFIX,
            fix_kind="required-tags",
            scaffold_factory=_required_tags_scaffold,
            legacy_policy_ids=("AIR-DET-002",),
        ),
        "effective-timeout": CheckSpec(
            kind="effective-timeout",
            configuration_kind="execution-timeout",
            evaluator=TimeoutEvaluator(),
            fixability=Fixability.AUTOFIX,
            fix_kind="execution-timeout",
            scaffold_factory=_execution_timeout_scaffold,
            legacy_policy_ids=("AIR-DET-003",),
        ),
        "retry-bounds": CheckSpec(
            kind="retry-bounds",
            configuration_kind="retry-bounds",
            evaluator=RetryEvaluator(),
            fixability=Fixability.AUTOFIX,
            fix_kind="retry-bounds",
            scaffold_factory=_retry_bounds_scaffold,
            legacy_policy_ids=("AIR-DET-004",),
        ),
        "module-scope-io": CheckSpec(
            kind="module-scope-io",
            configuration_kind="top-level-io",
            evaluator=TopLevelIOEvaluator(),
            fixability=Fixability.PROPOSED_ONLY,
            fix_kind="top-level-io",
            scaffold_factory=_top_level_io_scaffold,
            legacy_policy_ids=("AIR-DET-005",),
        ),
        "operator-allow-list": CheckSpec(
            kind="operator-allow-list",
            configuration_kind="forbidden-operators",
            evaluator=ForbiddenOperatorEvaluator(),
            fixability=Fixability.MANUAL,
            fix_kind="forbidden-operators",
            scaffold_factory=_forbidden_operators_scaffold,
            legacy_policy_ids=("AIR-DET-006",),
        ),
        "start-date-freshness": CheckSpec(
            kind="start-date-freshness",
            configuration_kind="start-date-freshness",
            evaluator=StartDateFreshnessEvaluator(),
            fixability=Fixability.MANUAL,
            fix_kind="start-date-freshness",
            scaffold_factory=_start_date_freshness_scaffold,
            legacy_policy_ids=(),
        ),
        "catchup-policy": CheckSpec(
            kind="catchup-policy",
            configuration_kind="catchup-policy",
            evaluator=CatchupPolicyEvaluator(),
            fixability=Fixability.AUTOFIX,
            fix_kind="catchup-policy",
            scaffold_factory=_catchup_policy_scaffold,
            legacy_policy_ids=(),
        ),
        "module-scope-variables": CheckSpec(
            kind="module-scope-variables",
            configuration_kind="module-scope-variables",
            evaluator=ModuleScopeVariablesEvaluator(),
            fixability=Fixability.MANUAL,
            fix_kind="module-scope-variables",
            scaffold_factory=_module_scope_variables_scaffold,
            legacy_policy_ids=(),
        ),
        "sensitive-logging": CheckSpec(
            kind="sensitive-logging",
            configuration_kind="sensitive-logging",
            evaluator=SensitiveLoggingEvaluator(),
            fixability=Fixability.MANUAL,
            fix_kind="sensitive-logging",
            scaffold_factory=_sensitive_logging_scaffold,
            legacy_policy_ids=(),
        ),
        "dynamic-dag-factory": CheckSpec(
            kind="dynamic-dag-factory",
            configuration_kind="dynamic-dag-factory",
            evaluator=DynamicDagFactoryEvaluator(),
            fixability=Fixability.MANUAL,
            fix_kind="dynamic-dag-factory",
            scaffold_factory=_dynamic_dag_factory_scaffold,
            legacy_policy_ids=(),
        ),
        "ruff-air": CheckSpec(
            kind="ruff-air",
            configuration_kind="ruff-air",
            evaluator=RuffAirEvaluator(),
            fixability=Fixability.MANUAL,
            fix_kind="ruff-air",
            scaffold_factory=_ruff_air_scaffold,
            legacy_policy_ids=("AIR-DET-012",),
        ),
        "idempotence": CheckSpec(
            kind="idempotence",
            configuration_kind="idempotence",
            evaluator=None,
            fixability=Fixability.MANUAL,
            fix_kind="idempotence",
            scaffold_factory=None,
            legacy_policy_ids=(),
        ),
        "orchestration-boundary": CheckSpec(
            kind="orchestration-boundary",
            configuration_kind="orchestration-boundary",
            evaluator=None,
            fixability=Fixability.MANUAL,
            fix_kind="orchestration-boundary",
            scaffold_factory=None,
            legacy_policy_ids=(),
        ),
        "approved-abstractions": CheckSpec(
            kind="approved-abstractions",
            configuration_kind="approved-abstractions",
            evaluator=None,
            fixability=Fixability.MANUAL,
            fix_kind="approved-abstractions",
            scaffold_factory=None,
            legacy_policy_ids=(),
        ),
    }


CHECK_SPECS: Final[dict[str, CheckSpec]] = _build_check_specs()

CHECK_EVALUATORS: Final[dict[str, DeterministicEvaluator]] = {
    kind: spec.evaluator for kind, spec in CHECK_SPECS.items() if spec.evaluator is not None
}
CHECK_CONFIGURATION_KINDS: Final[dict[str, str]] = {
    kind: spec.configuration_kind for kind, spec in CHECK_SPECS.items() if spec.evaluator is not None
}
LEGACY_POLICY_CHECKS: Final[dict[str, str]] = {
    policy_id: spec.kind for spec in CHECK_SPECS.values() for policy_id in spec.legacy_policy_ids
}
LEGACY_POLICY_EVALUATORS: Final[dict[str, DeterministicEvaluator]] = {
    policy_id: CHECK_EVALUATORS[kind] for policy_id, kind in LEGACY_POLICY_CHECKS.items()
}
LEGACY_POLICY_CONFIGURATION_KINDS: Final[dict[str, str]] = {
    policy_id: CHECK_SPECS[kind].configuration_kind for policy_id, kind in LEGACY_POLICY_CHECKS.items()
}


def _fixability_kinds(fixability: Fixability) -> frozenset[str]:
    return frozenset(spec.fix_kind for spec in CHECK_SPECS.values() if spec.fixability is fixability)


AUTOFIX_KINDS: Final[frozenset[str]] = _fixability_kinds(Fixability.AUTOFIX)
PROPOSED_ONLY_KINDS: Final[frozenset[str]] = _fixability_kinds(Fixability.PROPOSED_ONLY)
MANUAL_KINDS: Final[frozenset[str]] = _fixability_kinds(Fixability.MANUAL)


def check_spec(kind: str) -> CheckSpec:
    """Return complete catalogue metadata for a check kind."""
    try:
        return CHECK_SPECS[kind]
    except KeyError as exc:
        raise KeyError(f"unknown check kind {kind!r}") from exc
