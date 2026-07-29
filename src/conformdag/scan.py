"""Offline source-only scan orchestration for the first deterministic policy."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from conformdag import __version__
from conformdag.analysis import SourceModel, analyze_source, discover_python_files
from conformdag.config import load_project_config
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    Policy,
    RequiredOwnerConfig,
    RunIssue,
    RunMetadata,
    ScanReport,
)
from conformdag.policy import select_policy_pack


def _fingerprint(policy: Policy, path: str, line: int, status: FindingStatus) -> str:
    value = f"{policy.id}:{policy.version}:{path}:{line}:{status.value}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _owner_finding(policy: Policy, model: SourceModel, dag_line: int, owner: str | None) -> Finding:
    configuration = policy.configuration
    allowed = isinstance(configuration, RequiredOwnerConfig) and (
        not configuration.allowed_values or owner in configuration.allowed_values
    )
    status = FindingStatus.PASS if owner and allowed else FindingStatus.FAIL
    explanation = (
        f"effective owner {owner!r} is approved"
        if status is FindingStatus.PASS
        else f"effective owner {owner!r} is not in the approved owner set"
    )
    return Finding(
        policy_id=policy.id,
        policy_version=policy.version,
        status=status,
        severity=policy.severity,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(
            file=Path(model.source.relative_path), start_line=dag_line, end_line=dag_line
        ),
        evidence=FindingEvidence(
            text=f"DAG owner={owner!r}", start_line=dag_line, end_line=dag_line
        ),
        explanation=explanation,
        remediation=policy.safe_path,
        fingerprint=_fingerprint(policy, model.source.relative_path, dag_line, status),
    )


def scan_repository(repository_root: Path, policy_pack: Path | None = None) -> ScanReport:
    """Run an offline scan and return a canonical report without importing source files."""
    root = repository_root.resolve()
    config = load_project_config(root / "conformdag.yaml")
    configured_pack = policy_pack or config.scan.policy_pack
    if not configured_pack.is_absolute():
        configured_pack = root / configured_pack
    pack = select_policy_pack(configured_pack, root)
    files, discovery_issues = discover_python_files(
        root,
        config.scan.include,
        config.scan.exclude,
        config.scan.follow_internal_symlinks,
    )
    findings: list[Finding] = []
    issues = [
        RunIssue(code="DISCOVERY", message=issue.message, path=Path(issue.path), phase="discovery")
        for issue in discovery_issues
    ]
    models: list[SourceModel] = []
    for source in files:
        model, parse_issue = analyze_source(source)
        if parse_issue:
            issues.append(
                RunIssue(
                    code="PARSE_ERROR",
                    message=parse_issue.message,
                    path=Path(parse_issue.path),
                    phase="analysis",
                )
            )
        elif model:
            models.append(model)

    evaluated: list[str] = []
    skipped: list[str] = []
    for policy in pack.policies:
        if policy.status.value != "ACTIVE":
            skipped.append(policy.id)
            continue
        if policy.enforcement.type not in (EnforcementType.DETERMINISTIC, EnforcementType.HYBRID):
            skipped.append(policy.id)
            continue
        evaluated.append(policy.id)
        if policy.id == "AIR-DET-001":
            for model in models:
                for dag in model.dags:
                    findings.append(_owner_finding(policy, model, dag.line, dag.owner))

    payload = json.dumps([finding.model_dump(mode="json") for finding in findings], sort_keys=True)
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    complete = not issues
    return ScanReport(
        complete=complete,
        result_fingerprint=fingerprint,
        files_scanned=[source.path.relative_to(root) for source in files],
        policies_evaluated=evaluated,
        policies_skipped=skipped,
        findings=findings,
        issues=issues,
        run=RunMetadata(
            tool_version=__version__,
            input_hashes={source.relative_path: source.content_hash for source in files},
            policy_pack_id=pack.id,
            policy_pack_version=pack.version,
            timestamp=datetime.now(UTC),
        ),
    )
