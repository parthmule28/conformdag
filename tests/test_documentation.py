"""Regression checks for documentation and source-of-truth contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from runpy import run_path
from shutil import copy2
from typing import cast

from conformdag.benchmark import load_benchmark_manifest
from conformdag.fixing.codemods import AUTOFIX_KINDS
from conformdag.models import AirflowProfile
from conformdag.policy import load_policy_pack
from conformdag.runtime import runtime_profile

ROOT = Path(__file__).resolve().parents[1]
_INVENTORY_SCRIPT = cast(
    Callable[[Path], list[str]],
    run_path(str(ROOT / "scripts/verify_dependency_inventory.py"))["check_dependency_inventory"],
)


def test_current_release_references_are_distinguished_from_history() -> None:
    release = (ROOT / "docs/release.md").read_text(encoding="utf-8")
    current, historical = release.split("## Historical 0.1.0b1 release evidence", maxsplit=1)

    assert "1.0.0b1" in current
    assert "v1.0.0-beta.1" in current
    assert "0.1.0b1" not in current
    assert "v0.1.0-beta.1" not in current
    assert "v0.1.0-beta.1" in historical

    roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
    assert "1.0.0b1" in roadmap
    assert "0.1.0b1" not in roadmap


def test_current_runtime_identity_is_recorded_in_current_release_evidence() -> None:
    release = (ROOT / "docs/release.md").read_text(encoding="utf-8")
    current, _historical = release.split("## Historical 0.1.0b1 release evidence", maxsplit=1)
    image = runtime_profile(AirflowProfile.AIRFLOW_3_3_0).image

    assert "v1.0.0-beta.1" in current
    assert image.split("@", maxsplit=1)[1] in current


def test_benchmark_documentation_records_manifest_shape() -> None:
    manifest = load_benchmark_manifest(ROOT / "benchmarks/synthetic/manifest.yaml", ROOT / "benchmarks/synthetic")
    counts = Counter(case.policy_id for case in manifest.cases)
    assert len(counts) == 6
    assert len(set(counts.values())) == 1

    guide = (ROOT / "docs/user-guide.md").read_text(encoding="utf-8")
    assert f"{len(manifest.cases)} offline cases" in guide
    assert f"{len(counts)} policy populations" in guide
    assert f"{next(iter(counts.values()))} cases" in guide


def test_architecture_documents_check_kind_and_legacy_registries() -> None:
    architecture = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")

    assert "registered by check kind in `CHECK_EVALUATORS`" in architecture
    assert "Legacy policy-ID aliases" in architecture
    assert "`LEGACY_POLICY_EVALUATORS`" in architecture


def test_quality_tasks_scope_ruff_to_repository_python_paths() -> None:
    mise = (ROOT / "mise.toml").read_text(encoding="utf-8")

    assert 'run = "uv run ruff check src tests scripts"' in mise
    assert 'run = "uv run ruff format --check src tests scripts"' in mise


def test_release_gate_documentation_separates_corpus_from_autofix_population() -> None:
    """The 240-case corpus and the round-trip gate's 80-case autofix population must not be conflated."""
    manifest = load_benchmark_manifest(ROOT / "benchmarks/synthetic/manifest.yaml", ROOT / "benchmarks/synthetic")
    pack = load_policy_pack(ROOT / "policies/pack.yaml", ROOT)
    # Independent derivation of the round-trip population (mirrors the fixability matrix, not the
    # roundtrip module's private helper) so the documented figure is a real cross-check.
    fixable_ids = {
        policy.id
        for policy in pack.policies
        if policy.enforcement.type.value in {"deterministic", "hybrid"} and policy.configuration.kind in AUTOFIX_KINDS
    }
    population = sum(
        1
        for case in manifest.cases
        if case.label == "violation" and case.expected_applicable and case.policy_id in fixable_ids
    )
    corpus_size = len(manifest.cases)

    agents = " ".join((ROOT / "AGENTS.md").read_text(encoding="utf-8").split())
    release = " ".join((ROOT / "docs/release.md").read_text(encoding="utf-8").split())
    roundtrip_bullet = " ".join(
        release.split("- [x] Round-trip gate:", maxsplit=1)[1].split("- [x]", maxsplit=1)[0].split()
    )

    assert f"full synthetic benchmark corpus is {corpus_size} cases" in agents
    assert f"autofix violation population — {population} cases" in agents
    assert "runs the fix engine over 80 benchmark cases" not in agents

    assert f"autofix violation population — {population} of the {corpus_size}-case synthetic corpus" in roundtrip_bullet
    assert "over the 240-case synthetic corpus; a regression fails the build" not in release


def test_dependency_inventory_is_enforced_by_the_default_gate_and_ci() -> None:
    mise = (ROOT / "mise.toml").read_text(encoding="utf-8")
    agents = " ".join((ROOT / "AGENTS.md").read_text(encoding="utf-8").split())
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert 'depends = ["format-check", "lint", "typecheck", "test", "validate:packs", "inventory"]' in mise
    assert "format-check → lint → typecheck → test → validate:packs → inventory" in agents

    fast_job = ci.split("\n  fast:", maxsplit=1)[1].split("\n  frontend-e2e:", maxsplit=1)[0]
    assert "mise run check" in fast_job
    release_job = ci.split("\n  release-validation:", maxsplit=1)[1].split("\n  host-macos:", maxsplit=1)[0]
    assert "mise run inventory" in release_job


def test_dependency_inventory_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify_dependency_inventory.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_dependency_inventory_check_reports_removed_package(tmp_path: Path) -> None:
    for relative in (
        "docs/dependency-inventory.md",
        "pyproject.toml",
        "uv.lock",
        "frontend/package.json",
        "frontend/package-lock.json",
        "runtime/airflow-3.3.0/constraints.txt",
        "runtime/airflow-3.3.0/Dockerfile",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / relative, target)

    inventory_path = tmp_path / "docs/dependency-inventory.md"
    inventory = inventory_path.read_text(encoding="utf-8")
    inventory_path.write_text(
        inventory.replace(
            "| `httpx` | runtime | `httpx>=0.28,<1` | BSD-3-Clause | OpenAI-compatible provider transport |\n",
            "",
        ),
        encoding="utf-8",
    )

    assert "Python inventory missing: httpx" in _INVENTORY_SCRIPT(tmp_path)


def test_dependency_inventory_check_reports_frontend_manifest_drift(tmp_path: Path) -> None:
    for relative in (
        "docs/dependency-inventory.md",
        "pyproject.toml",
        "uv.lock",
        "frontend/package.json",
        "frontend/package-lock.json",
        "runtime/airflow-3.3.0/constraints.txt",
        "runtime/airflow-3.3.0/Dockerfile",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / relative, target)

    package_path = tmp_path / "frontend/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    del package["dependencies"]["react"]
    package_path.write_text(json.dumps(package), encoding="utf-8")

    assert "package-lock.json root declaration drift: react" in _INVENTORY_SCRIPT(tmp_path)


def test_dependency_inventory_checks_runtime_dockerfile_pins(tmp_path: Path) -> None:
    for relative in (
        "docs/dependency-inventory.md",
        "pyproject.toml",
        "uv.lock",
        "frontend/package.json",
        "frontend/package-lock.json",
        "runtime/airflow-3.3.0/constraints.txt",
        "runtime/airflow-3.3.0/Dockerfile",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / relative, target)

    dockerfile_path = tmp_path / "runtime/airflow-3.3.0/Dockerfile"
    dockerfile_path.write_text(
        dockerfile_path.read_text(encoding="utf-8").replace("tornado==6.5.8", "tornado==6.5.9"),
        encoding="utf-8",
    )

    assert "Dockerfile runtime package drift: tornado" in _INVENTORY_SCRIPT(tmp_path)
