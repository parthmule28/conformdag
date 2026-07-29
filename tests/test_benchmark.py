"""Tests for versioned benchmark manifests and fixture verification."""

import hashlib
from pathlib import Path

import pytest

from conformdag.benchmark import (
    BenchmarkValidationError,
    benchmark_manifest_payload,
    load_benchmark_manifest,
)


def _manifest(fixture_hash: str) -> str:
    return f"""schema_version: '1'
dataset_id: synthetic-beta
dataset_version: '2026.07'
license:
  name: Apache-2.0
  url: https://www.apache.org/licenses/LICENSE-2.0
cases:
  - id: owner-001
    fixture: fixture.py
    fixture_sha256: '{fixture_hash}'
    policy_id: AIR-DET-001
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


def test_rejects_changed_fixture_hash(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.py"
    fixture.write_text("changed\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(_manifest("0" * 64), encoding="utf-8")

    with pytest.raises(BenchmarkValidationError, match="fixture hash mismatch"):
        load_benchmark_manifest(manifest_path, tmp_path)
