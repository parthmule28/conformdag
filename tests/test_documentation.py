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
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / relative, target)

    package_path = tmp_path / "frontend/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    del package["dependencies"]["react"]
    package_path.write_text(json.dumps(package), encoding="utf-8")

    assert "package-lock.json root declaration drift: react" in _INVENTORY_SCRIPT(tmp_path)
