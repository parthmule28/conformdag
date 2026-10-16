"""Baseline characterization tests for report normalization and fingerprints."""

import json
from datetime import UTC, datetime

from conformdag.reporting import normalize_report

from .fixtures import fixed_report

EXPECTED_FINGERPRINT = "8050ab09ad677b729bc5287e99347713afc10bf0d87957066b1494442f034e26"
EXPECTED_NORMALIZED_JSON = """
{"complete":true,"files_scanned":["dags/a.py","dags/b.py","dags/z.py"],"findings":[{"audit_evidence":[],"blocking":true,"confidence":null,"enforcement":"deterministic","evidence":{"code_hash":"code-fp-a-error","end_line":8,"start_line":7,"text":"secret=fixture-secret-evidence"},"explanation":"Bearer fixture-bearer","fingerprint":"fp-a-error","fix":null,"location":{"end_line":8,"file":"dags/a.py","start_line":7},"policy_id":"A-POLICY","policy_version":"1.2.3","remediation":"token=fixture-token-remediation","severity":"critical","status":"ERROR","suppressed":false,"suppression":null},{"audit_evidence":[],"blocking":true,"confidence":null,"enforcement":"deterministic","evidence":{"code_hash":"code-fp-b-suppressed","end_line":13,"start_line":12,"text":"api_key=fixture-evidence <unsafe>"},"explanation":"password=fixture-explanation <unsafe>","fingerprint":"fp-b-suppressed","fix":null,"location":{"end_line":13,"file":"dags/b.py","start_line":12},"policy_id":"B-POLICY","policy_version":"1.2.3","remediation":"credential=fixture-remediation","severity":"high","status":"FAIL","suppressed":true,"suppression":{"created_at":"2025-12-01T00:00:00Z","expires_at":"2026-12-31T00:00:00Z","fingerprint":"fp-b-suppressed","owner":"platform","policy_id":"B-POLICY","reason":"tracked fixture exception"}},{"audit_evidence":[],"blocking":false,"confidence":null,"enforcement":"deterministic","evidence":{"code_hash":"code-fp-b-tie","end_line":13,"start_line":12,"text":"tie evidence"},"explanation":"tie <b>& explanation","fingerprint":"fp-b-tie","fix":null,"location":{"end_line":13,"file":"dags/b.py","start_line":12},"policy_id":"B-POLICY","policy_version":"1.2.3","remediation":"manual review","severity":"low","status":"FAIL","suppressed":false,"suppression":null},{"audit_evidence":[],"blocking":false,"confidence":null,"enforcement":"deterministic","evidence":{"code_hash":"code-fp-m-fail","end_line":21,"start_line":20,"text":"medium evidence"},"explanation":"medium <m>& explanation","fingerprint":"fp-m-fail","fix":null,"location":{"end_line":21,"file":"dags/m.py","start_line":20},"policy_id":"M-POLICY","policy_version":"1.2.3","remediation":"review medium finding","severity":"medium","status":"FAIL","suppressed":false,"suppression":null},{"audit_evidence":[],"blocking":false,"confidence":null,"enforcement":"deterministic","evidence":{"code_hash":"code-fp-z-pass","end_line":4,"start_line":3,"text":"pass evidence"},"explanation":"pass <safe>","fingerprint":"fp-z-pass","fix":null,"location":{"end_line":4,"file":"dags/z.py","start_line":3},"policy_id":"Z-PASS","policy_version":"1.2.3","remediation":"no action","severity":"info","status":"PASS","suppressed":false,"suppression":null}],"gate_result":{"gate_id":"fixture-gate","passed":false,"rules":[{"detail":"fixture gate failed","matching_findings":3,"passed":false,"rule_type":"max-findings"}]},"issues":[{"code":"A-ISSUE","fatal":false,"message":"a issue","path":"dags/a.py","phase":"discovery"},{"code":"Z-ISSUE","fatal":false,"message":"z issue","path":"dags/z.py","phase":"runtime"}],"policies_evaluated":["Z-POLICY","A-POLICY","B-POLICY"],"policies_skipped":["Z-SKIPPED","A-SKIPPED"],"report_version":"2","result_fingerprint":"8050ab09ad677b729bc5287e99347713afc10bf0d87957066b1494442f034e26","run":{"environment":{"FIXTURE_ENV":"value"},"input_hashes":{"dags/a.py":"hash-a","dags/z.py":"hash-z"},"policy_pack_id":"fixture-pack","policy_pack_version":"2.0","prompt_hashes":{"A-POLICY":"prompt-a","Z-POLICY":"prompt-z"},"repository_revision":"revision-excluded-from-fingerprint","resolved_configuration":{"z":"configuration"},"runtime_image_digest":"sha256:fixture-image","runtime_profile":null,"semantic_model":"fixture-model","semantic_provider":"fixture-provider","semantic_runs":[],"timestamp":"2026-01-02T03:04:05Z","tool_version":"fixture-tool-1.0"},"runtime_observations":[{"message":null,"payload":{"a":1},"policy_id":"A-RUNTIME","schema_version":"1","status":"PASS"},{"message":"runtime z","payload":{"z":2},"policy_id":"Z-RUNTIME","schema_version":"1","status":"FAIL"}]}
"""


def test_normalize_report_matches_frozen_baseline_json_and_fingerprint() -> None:
    normalized = normalize_report(fixed_report())

    assert normalized.result_fingerprint == EXPECTED_FINGERPRINT
    assert normalized.model_dump(mode="json") == json.loads(EXPECTED_NORMALIZED_JSON)


def test_normalize_report_preserves_input_and_applies_all_ordering_keys() -> None:
    report = fixed_report()
    before = report.model_dump(mode="json")

    normalized = normalize_report(report)

    assert report.model_dump(mode="json") == before
    assert [str(path) for path in normalized.files_scanned] == ["dags/a.py", "dags/b.py", "dags/z.py"]
    assert [finding.policy_id for finding in normalized.findings] == [
        "A-POLICY",
        "B-POLICY",
        "B-POLICY",
        "M-POLICY",
        "Z-PASS",
    ]
    assert [finding.fingerprint for finding in normalized.findings[1:3]] == [
        "fp-b-suppressed",
        "fp-b-tie",
    ]
    assert [(issue.phase, issue.code) for issue in normalized.issues] == [
        ("discovery", "A-ISSUE"),
        ("runtime", "Z-ISSUE"),
    ]
    assert [(item.policy_id, item.status.value) for item in normalized.runtime_observations] == [
        ("A-RUNTIME", "PASS"),
        ("Z-RUNTIME", "FAIL"),
    ]


def test_normalize_report_ignores_timestamp_and_seed_fingerprint() -> None:
    report = fixed_report().model_copy(
        update={
            "result_fingerprint": "different-seed",
            "run": fixed_report().run.model_copy(update={"timestamp": datetime(2030, 1, 1, tzinfo=UTC)}),
        }
    )

    normalized = normalize_report(report)

    assert normalized.result_fingerprint == EXPECTED_FINGERPRINT
    assert normalized.run.timestamp == datetime(2030, 1, 1, tzinfo=UTC)


def test_normalize_report_hashes_sorted_mapping_and_policy_copies_without_reordering_returned_lists() -> None:
    report = fixed_report().model_copy(
        update={
            "policies_evaluated": ["B-POLICY", "A-POLICY", "Z-POLICY"],
            "policies_skipped": ["A-SKIPPED", "Z-SKIPPED"],
            "run": fixed_report().run.model_copy(
                update={
                    "input_hashes": {"dags/a.py": "hash-a", "dags/z.py": "hash-z"},
                    "prompt_hashes": {"A-POLICY": "prompt-a", "Z-POLICY": "prompt-z"},
                }
            ),
        }
    )

    normalized = normalize_report(report)

    assert normalized.result_fingerprint == EXPECTED_FINGERPRINT
    assert normalized.policies_evaluated == ["B-POLICY", "A-POLICY", "Z-POLICY"]
    assert normalized.policies_skipped == ["A-SKIPPED", "Z-SKIPPED"]


def test_normalize_report_excludes_gate_result_from_fingerprint() -> None:
    report = fixed_report()
    assert report.gate_result is not None
    changed_gate = report.gate_result.model_copy(update={"gate_id": "different-gate", "passed": True})

    normalized = normalize_report(report.model_copy(update={"gate_result": changed_gate}))

    assert normalized.result_fingerprint == EXPECTED_FINGERPRINT
    assert normalized.gate_result is changed_gate
