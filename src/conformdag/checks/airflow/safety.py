"""Airflow safety and Ruff deterministic evaluators."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from conformdag.analysis import CallRecord, SourceModel, secret_like
from conformdag.checks.common import (
    EvaluationContext,
    _finding,
    fix_target,
    policy_applies,
    redact_evidence,
    structural_fingerprint,
)
from conformdag.models import (
    AirflowProfile,
    DynamicDagFactoryConfig,
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    ForbiddenOperatorsConfig,
    ModuleScopeVariablesConfig,
    OperatorRule,
    Policy,
    RemediationAction,
    RemediationPayload,
    RemediationTarget,
    RuffAirConfig,
    SensitiveLoggingConfig,
    TopLevelIOConfig,
)
from conformdag.ruff_adapter import ruff_rule_matches, run_ruff


class TopLevelIOEvaluator:
    policy_id = "AIR-DET-005"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(TopLevelIOConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for call in model.calls:
                if not call.module_scope:
                    continue
                if call.uncertain and configuration.uncertain_as_review:
                    findings.append(
                        _finding(
                            context.policy,
                            model,
                            call.line,
                            FindingStatus.NEEDS_REVIEW,
                            "module-scope dynamic call could not be classified with high confidence",
                            f"dynamic-call:{call.line}:{call.column}",
                            fix_payload=RemediationPayload(
                                fix_kind="top-level-io",
                                action=RemediationAction.MANUAL,
                                target=fix_target(call.line, None, "statement"),
                                hint="dynamic module-scope call needs human review",
                            ),
                        )
                    )
                    continue
                matched = next(
                    (pattern for pattern in configuration.forbidden_calls if call.qualified_name == pattern),
                    None,
                )
                if matched:
                    findings.append(
                        _finding(
                            context.policy,
                            model,
                            call.line,
                            FindingStatus.FAIL,
                            f"module-scope call {call.qualified_name} matches forbidden I/O pattern {matched}",
                            f"call:{call.qualified_name}:{call.line}",
                            fix_payload=RemediationPayload(
                                fix_kind="top-level-io",
                                action=RemediationAction.MOVE_STATEMENT,
                                target=fix_target(call.line, call.qualified_name, "statement"),
                                hint="proposed-only structural move of the module-scope "
                                "statement into a task callable; never auto-applied",
                            ),
                        )
                    )
        return findings


def _resolve_imported_call(model: SourceModel, call: CallRecord) -> str:
    for item in model.imports:
        local_name = item.alias or item.module.rsplit(".", 1)[-1]
        if call.qualified_name == local_name:
            return item.module
        if call.qualified_name.startswith(f"{local_name}.") and item.alias:
            return f"{item.module}{call.qualified_name[len(local_name) :]}"
    return call.qualified_name


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


class ForbiddenOperatorEvaluator:
    policy_id = "AIR-DET-006"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(ForbiddenOperatorsConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for call in model.calls:
                resolved = _resolve_imported_call(model, call)
                if resolved not in configuration.operators:
                    continue
                rule = configuration.operators[resolved]
                if isinstance(rule, OperatorRule):
                    if (
                        context.airflow_profile is not None
                        and rule.airflow_profiles
                        and context.airflow_profile not in rule.airflow_profiles
                    ):
                        continue
                    profile_version = (
                        _version_tuple(context.airflow_profile.value) if context.airflow_profile is not None else None
                    )
                    if (
                        profile_version is not None
                        and rule.min_airflow_version
                        and profile_version < _version_tuple(rule.min_airflow_version)
                    ):
                        continue
                    if (
                        profile_version is not None
                        and rule.max_airflow_version
                        and profile_version > _version_tuple(rule.max_airflow_version)
                    ):
                        continue
                    replacement = rule.replacement
                else:
                    replacement = rule
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        call.line,
                        FindingStatus.FAIL,
                        f"forbidden operator {resolved}; replacement guidance: {replacement}",
                        f"operator:{resolved}:{call.line}",
                        replacement,
                        fix_payload=RemediationPayload(
                            fix_kind="forbidden-operators",
                            action=RemediationAction.MANUAL,
                            target=fix_target(call.line, resolved, "statement"),
                            value=replacement,
                            hint="not auto-fixable; apply the replacement guidance",
                        ),
                    )
                )
        return findings


class ModuleScopeVariablesEvaluator:
    """Deterministic check kind: ``module-scope-variables``."""

    policy_id = "AIR-DET-009"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(ModuleScopeVariablesConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for call in model.calls:
                if not call.module_scope:
                    continue
                if not any(call.qualified_name == pattern for pattern in configuration.patterns):
                    continue
                anchor = f"call:{call.qualified_name}:{call.line}"
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        call.line,
                        FindingStatus.FAIL,
                        f"top-level {call.qualified_name}() hits the metadata database on every scheduler parse cycle",
                        anchor,
                        fix_payload=RemediationPayload(
                            fix_kind="module-scope-variables",
                            action=RemediationAction.MOVE_STATEMENT,
                            target=fix_target(call.line, call.qualified_name, "statement"),
                            hint="move the variable access into a task body, or use a {{ var.value.* }} Jinja template",
                        ),
                    )
                )
        return findings


class SensitiveLoggingEvaluator:
    """Deterministic check kind: ``sensitive-logging`` (hardcoded secrets)."""

    policy_id = "AIR-DET-010"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(SensitiveLoggingConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for constant in model.constants:
                if not isinstance(constant.value, str):
                    continue
                looks_secret = secret_like(constant.name) or any(
                    pattern.lower() in constant.name.lower() for pattern in configuration.secret_patterns
                )
                if not looks_secret:
                    continue
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        constant.line,
                        FindingStatus.FAIL,
                        f"module-scope constant {constant.name!r} looks like a hardcoded credential",
                        anchor=f"secret:{constant.name}:{constant.line}",
                        fix_payload=RemediationPayload(
                            fix_kind="sensitive-logging",
                            action=RemediationAction.MANUAL,
                            target=fix_target(constant.line, constant.name, "statement"),
                            hint="move the value into an Airflow Connection or a secrets "
                            "backend; never commit credentials",
                        ),
                    )
                )
        return findings


class DynamicDagFactoryEvaluator:
    """Deterministic check kind: ``dynamic-dag-factory`` (loop-generated DAGs)."""

    policy_id = "AIR-DET-011"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(DynamicDagFactoryConfig, context.policy.configuration)
        if configuration.allow:
            return []
        findings: list[Finding] = []
        for model in context.models:
            for line in model.dynamic_dag_lines:
                anchor = f"dynamic-dag:{model.source.relative_path}:{line}"
                findings.append(
                    _finding(
                        context.policy,
                        model,
                        line,
                        FindingStatus.FAIL,
                        "module-scope loop generates DAGs; per Airflow best practices "
                        "this slows fleet-wide parsing and multiplies scheduling load",
                        anchor,
                        fix_payload=RemediationPayload(
                            fix_kind="dynamic-dag-factory",
                            action=RemediationAction.MANUAL,
                            target=fix_target(line, None, "statement"),
                            hint="prefer dynamic task mapping, DAG bundles, or config-file "
                            "generation committed to the repo",
                        ),
                    )
                )
        return findings


def _ruff_path(repository_root: Path, filename: object) -> str | None:
    """Normalize a Ruff filename to the scan-relative identity of its source.

    Violations carry the scan identity recorded by the Ruff adapter, so
    filenames are matched textually against the repository root: resolving
    them here would collapse an internal symlink such as ``dags/link.py``
    back onto its target and lose the identity the file was scanned under.
    """
    if not isinstance(filename, str) or not filename:
        return None
    path = Path(filename)
    try:
        if path.is_absolute():
            return path.relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return None
    if path.parts and path.parts[0] == "..":
        return None
    return path.as_posix()


def ruff_policies_for_scan(policies: Iterable[Policy], airflow_profile: AirflowProfile | None) -> list[Policy]:
    """Return active policies that contribute Ruff rules to this scan."""
    return [
        policy
        for policy in policies
        if policy.status.value == "ACTIVE"
        and policy.enforcement.type in (EnforcementType.DETERMINISTIC, EnforcementType.HYBRID)
        and policy_applies(policy, airflow_profile)
        and ("ruff-air" in policy.enforcement.deterministic_checks or policy.id == "AIR-DET-012")
    ]


def ruff_rules_for_policies(policies: Iterable[Policy], airflow_profile: AirflowProfile | None) -> list[str]:
    """Build one deterministic, sorted Ruff selector list for a scan."""
    return sorted(
        {
            rule
            for policy in ruff_policies_for_scan(policies, airflow_profile)
            for rule in cast(RuffAirConfig, policy.configuration).rules
        }
    )


class RuffAirEvaluator:
    """Deterministic check kind: ``ruff-air`` (composed Ruff AIR violations)."""

    policy_id = "AIR-DET-012"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RuffAirConfig, context.policy.configuration)
        if context.repository_root is None:
            return []
        violations = context.ruff_violations
        if violations is None:
            violations = (
                run_ruff(context.repository_root, configuration.rules, [model.source.path for model in context.models])
                or []
            )
        scanned = {model.source.relative_path for model in context.models}
        findings: list[Finding] = []
        for violation in violations:
            code = violation.get("code")
            if not isinstance(code, str) or not any(
                ruff_rule_matches(code, selector) for selector in configuration.rules
            ):
                continue
            relative = _ruff_path(context.repository_root, violation.get("filename"))
            if relative is None or relative not in scanned:
                continue
            location = violation.get("location")
            if not isinstance(location, dict):
                continue
            location = cast(dict[str, Any], location)
            row = location.get("row")
            if not isinstance(row, int) or isinstance(row, bool) or row <= 0:
                continue
            raw_message = violation.get("message", "")
            message = raw_message if isinstance(raw_message, str) else str(raw_message)
            detail = f"{code}: {message}"
            findings.append(
                Finding(
                    policy_id=context.policy.id,
                    policy_version=context.policy.version,
                    status=FindingStatus.FAIL,
                    severity=context.policy.severity,
                    enforcement=EnforcementType.DETERMINISTIC,
                    location=FindingLocation(file=Path(relative), start_line=row, end_line=row),
                    evidence=FindingEvidence(text=redact_evidence(detail), start_line=row, end_line=row),
                    explanation=detail,
                    remediation=context.policy.safe_path,
                    fix=RemediationPayload(
                        fix_kind="ruff-air",
                        action=RemediationAction.MANUAL,
                        target=RemediationTarget(line=row, column=0, node="statement"),
                        hint=f"review Ruff rule {code}; source fixes are disabled",
                    ),
                    fingerprint=structural_fingerprint(
                        context.policy, relative, f"ruff:{code}:{row}", FindingStatus.FAIL
                    ),
                )
            )
        return findings
