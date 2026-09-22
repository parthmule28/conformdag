"""Airflow metadata deterministic evaluators."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from conformdag.analysis import DagRecord, SourceModel
from conformdag.checks.common import (
    EvaluationContext,
    EvaluationPhaseError,
    finding,
    fix_target,
    redact_evidence,
    structural_fingerprint,
)
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    Policy,
    RemediationAction,
    RemediationPayload,
    RequiredOwnerConfig,
    RequiredTagsConfig,
)


class OwnerEvaluator:
    policy_id = "AIR-DET-001"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        if not isinstance(context.policy.configuration, RequiredOwnerConfig):
            raise EvaluationPhaseError("AIR-DET-001 requires a required-owner configuration")
        findings = [self._finding(context.policy, model, dag) for model in context.models for dag in model.dags]
        return sorted(
            findings,
            key=lambda finding: (
                str(finding.location.file),
                finding.location.start_line or 0,
                finding.policy_id,
                finding.status.value,
            ),
        )

    @staticmethod
    def _finding(policy: Policy, model: SourceModel, dag: DagRecord) -> Finding:
        configuration = cast(RequiredOwnerConfig, policy.configuration)
        allowed = bool(dag.owner) and (not configuration.allowed_values or dag.owner in configuration.allowed_values)
        if configuration.allowed_pattern and dag.owner:
            allowed = allowed and bool(re.fullmatch(configuration.allowed_pattern, dag.owner))
        status = FindingStatus.PASS if allowed else FindingStatus.FAIL
        owner_text = f"effective owner={dag.owner!r} source={dag.owner_source or 'unresolved'}"
        explanation = (
            f"{owner_text} is approved"
            if status is FindingStatus.PASS
            else f"{owner_text} is absent or not approved by policy"
        )
        anchor = f"dag:{dag.variable_name or dag.line}:owner:{dag.owner or 'missing'}"
        payload: RemediationPayload | None = None
        if status is FindingStatus.FAIL:
            enclosing = dag.variable_name or f"dag@{dag.line}"
            if configuration.allowed_values:
                value = sorted(configuration.allowed_values)[0]
                action = RemediationAction.SET_KWARG if dag.owner else RemediationAction.ADD_OWNER
                payload = RemediationPayload(
                    fix_kind="required-owner",
                    action=action,
                    kwarg="owner",
                    target=fix_target(dag.line, enclosing, "dag-call"),
                    value=value,
                    hint=f'sets owner="{value}" on the DAG call',
                )
            elif configuration.allowed_pattern:
                payload = RemediationPayload(
                    fix_kind="required-owner",
                    action=RemediationAction.MANUAL,
                    target=fix_target(dag.line, enclosing, "dag-call"),
                    hint="policy constrains owner by pattern; choose a compliant owner value",
                )
            else:
                payload = RemediationPayload(
                    fix_kind="required-owner",
                    action=RemediationAction.MANUAL,
                    target=fix_target(dag.line, enclosing, "dag-call"),
                    hint="policy declares no allowed values; configure allowed_values or allowed_pattern",
                )
        return Finding(
            policy_id=policy.id,
            policy_version=policy.version,
            status=status,
            severity=policy.severity,
            enforcement=EnforcementType.DETERMINISTIC,
            location=FindingLocation(
                file=Path(model.source.relative_path),
                start_line=dag.line,
                end_line=dag.line,
            ),
            evidence=FindingEvidence(
                text=redact_evidence(owner_text),
                start_line=dag.line,
                end_line=dag.line,
            ),
            explanation=explanation,
            remediation=policy.safe_path,
            fix=payload,
            fingerprint=structural_fingerprint(policy, model.source.relative_path, anchor, status),
        )


class TagEvaluator:
    policy_id = "AIR-DET-002"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RequiredTagsConfig, context.policy.configuration)
        findings: list[Finding] = []
        for model in context.models:
            for dag in model.dags:
                tags = {
                    key: value for tag in dag.tags for key, value in [tag.split(":", 1) if ":" in tag else (tag, None)]
                }
                missing = [key for key in configuration.required_keys if key not in tags]
                invalid = [
                    f"{key}={tags[key]!r}"
                    for key, allowed in configuration.allowed_values.items()
                    if key in tags and allowed and tags[key] not in allowed
                ]
                status = FindingStatus.PASS if not missing and not invalid else FindingStatus.FAIL
                detail = (
                    "DAG tags satisfy policy"
                    if status is FindingStatus.PASS
                    else f"missing tags={missing!r}; invalid tags={invalid!r}"
                )
                payload: RemediationPayload | None = None
                if status is FindingStatus.FAIL:
                    enclosing = dag.variable_name or f"dag@{dag.line}"
                    if invalid:
                        payload = RemediationPayload(
                            fix_kind="required-tags",
                            action=RemediationAction.MANUAL,
                            target=fix_target(dag.line, enclosing, "dag-call"),
                            hint="tags carry disallowed values; choose compliant values from policy",
                        )
                    elif missing:
                        additions = [
                            f"{key}:{sorted(configuration.allowed_values[key])[0]}"
                            if configuration.allowed_values.get(key)
                            else key
                            for key in missing
                        ]
                        payload = RemediationPayload(
                            fix_kind="required-tags",
                            action=RemediationAction.ADD_TAGS,
                            kwarg="tags",
                            target=fix_target(dag.line, enclosing, "dag-call"),
                            value=json.dumps(additions),
                            hint=f"adds compliant tags {additions!r} to the DAG tags list",
                        )
                findings.append(
                    finding(
                        context.policy,
                        model,
                        dag.line,
                        status,
                        detail,
                        f"dag:{dag.variable_name or dag.line}:tags:{','.join(sorted(dag.tags))}",
                        fix_payload=payload,
                    )
                )
        return findings
