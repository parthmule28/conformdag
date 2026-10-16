"""Deterministic canonical report normalization."""

from __future__ import annotations

import hashlib
import json

from conformdag.models import ScanReport


def normalize_report(report: ScanReport) -> ScanReport:
    """Return a stable report ordering and fingerprint independent of timestamps."""
    findings = sorted(
        report.findings,
        key=lambda finding: (
            finding.policy_id,
            str(finding.location.file),
            finding.location.start_line or 0,
            finding.fingerprint,
        ),
    )
    issues = sorted(report.issues, key=lambda issue: (issue.phase, issue.code, str(issue.path)))
    files = sorted(report.files_scanned, key=str)
    runtime_observations = sorted(
        report.runtime_observations,
        key=lambda observation: (
            observation.policy_id,
            observation.status.value,
            observation.message or "",
        ),
    )
    payload = {
        "complete": report.complete,
        "files_scanned": [str(path) for path in files],
        "policies_evaluated": sorted(report.policies_evaluated),
        "policies_skipped": sorted(report.policies_skipped),
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "runtime_observations": [observation.model_dump(mode="json") for observation in runtime_observations],
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "input_hashes": dict(sorted(report.run.input_hashes.items())),
        "policy_pack_id": report.run.policy_pack_id,
        "policy_pack_version": report.run.policy_pack_version,
        "runtime_profile": report.run.runtime_profile,
        "runtime_image_digest": report.run.runtime_image_digest,
        "semantic_provider": report.run.semantic_provider,
        "semantic_model": report.run.semantic_model,
        "prompt_hashes": dict(sorted(report.run.prompt_hashes.items())),
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return report.model_copy(
        update={
            "files_scanned": files,
            "findings": findings,
            "runtime_observations": runtime_observations,
            "issues": issues,
            "result_fingerprint": fingerprint,
        }
    )
