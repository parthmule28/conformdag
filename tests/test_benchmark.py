"""Tests for versioned benchmark manifests and fixture verification."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from conformdag.benchmark import (
    BenchmarkValidationError,
    benchmark_identity,
    benchmark_manifest_payload,
    load_benchmark_manifest,
    render_benchmark_report,
    run_deterministic_benchmark,
)


def _manifest(fixture_hash: str) -> str:
    return f"""schema_version: '1'
dataset_id: synthetic-beta
dataset_version: '2026.07'
license:
  name: Apache-2.0
  url: https://www.apache.org/licenses/LICENSE-2.0
source_admissions:
  - source_id: conformdag-test-source
    kind: synthetic
    url: https://example.invalid/conformdag-test-source
    revision: test-revision
    license:
      name: Apache-2.0
    redistribution: redistributable
    transformation: test fixture
    privacy_review: Completed
    secrets_review: Completed
cases:
  - id: owner-001
    fixture: fixture.py
    fixture_sha256: '{fixture_hash}'
    policy_id: AIR-DET-001
    source_id: conformdag-test-source
    label: violation
    expected_applicable: true
    expected_status: FAIL
    expected_location:
      file: fixture.py
      start_line: 1
    expected_evidence: missing owner
"""


def test_loads_and_normalizes_hashed_manifest(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.py"
    fixture.write_text("dag = None\n", encoding="utf-8")
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(_manifest(digest), encoding="utf-8")

    manifest = load_benchmark_manifest(manifest_path, tmp_path)

    assert manifest.cases[0].expected_status.value == "FAIL"
    assert benchmark_manifest_payload(manifest)["dataset_id"] == "synthetic-beta"
    changed = manifest.model_copy(update={"policy_versions": {"AIR-DET-001": "2.0.0"}})
    assert benchmark_identity(manifest) != benchmark_identity(changed)


def test_rejects_changed_fixture_hash(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.py"
    fixture.write_text("changed\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(_manifest("0" * 64), encoding="utf-8")

    with pytest.raises(BenchmarkValidationError, match="fixture hash mismatch"):
        load_benchmark_manifest(manifest_path, tmp_path)


def test_rejects_case_with_unknown_source_admission(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.py"
    fixture.write_text("changed\n", encoding="utf-8")
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        _manifest(digest).replace(
            "    source_id: conformdag-test-source\n", "    source_id: unknown\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkValidationError, match="unknown source admission"):
        load_benchmark_manifest(manifest_path, tmp_path)


def test_synthetic_release_has_balanced_cases_and_admission_metadata() -> None:
    root = Path("benchmarks/synthetic")
    manifest = load_benchmark_manifest(root / "manifest.yaml", root)

    by_policy: dict[str, list] = {}
    for case in manifest.cases:
        by_policy.setdefault(case.policy_id, []).append(case)

    assert set(by_policy) == {f"AIR-DET-00{index}" for index in range(1, 7)}
    assert all(len(cases) == 40 for cases in by_policy.values())
    assert all(
        sum(case.label == "violation" for case in cases) == 20 for cases in by_policy.values()
    )
    assert all(
        sum(case.label in {"valid", "safe-counterexample"} for case in cases) == 20
        for cases in by_policy.values()
    )
    assert len(manifest.source_admissions) == 6
    assert {source.kind for source in manifest.source_admissions} == {"public", "synthetic"}
    synthetic = [source for source in manifest.source_admissions if source.kind == "synthetic"]
    assert len(synthetic) == 1
    assert synthetic[0].privacy_review.startswith("Completed")
    assert set(synthetic[0].derived_from) == {
        source.source_id for source in manifest.source_admissions if source.kind == "public"
    }
    assert {case.source_id for case in manifest.cases} == {"conformdag-synthetic-generator"}
    assert all(
        case.mutation_recipe is not None for case in manifest.cases if case.label == "violation"
    )
    assert all(case.mutation_recipe is None for case in manifest.cases if case.label != "violation")


def test_synthetic_regeneration_preserves_manifest_hash() -> None:
    manifest_path = Path("benchmarks/synthetic/manifest.yaml")
    before = hashlib.sha256(manifest_path.read_bytes()).digest()

    subprocess.run(
        [sys.executable, "scripts/generate_synthetic_benchmark.py"],
        check=True,
    )

    assert hashlib.sha256(manifest_path.read_bytes()).digest() == before


def test_deterministic_benchmark_executes_all_cases_offline() -> None:
    result = run_deterministic_benchmark(
        Path("benchmarks/synthetic/manifest.yaml"),
        Path("policies/pack.yaml"),
        Path("."),
    )

    assert result.passed
    assert result.total_cases == 240
    assert result.failed_cases == 0
    assert result.metrics["aggregate"].precision == 1.0
    assert result.metrics["aggregate"].recall == 1.0
    assert all(gate.passed for gate in result.quality_gates)
    assert [baseline.status for baseline in result.baselines] == [
        "executed",
        "not_executed",
        "not_executed",
        "not_executed",
    ]
    report = render_benchmark_report(result)
    assert "# ConformDAG Benchmark Report" in report
    assert "| aggregate | 240 | 1.0 | 1.0 | 1.0 | PASS |" in report
