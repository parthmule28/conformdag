"""Import-graph and compatibility-facade contracts for the runtime package."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

RUNTIME_PACKAGE = Path("src/conformdag/runtime")
OWNER_IMPORTS: dict[str, set[str]] = {
    "profiles": set(),
    "manifest": {"conformdag.runtime.profiles"},
    "docker": {"conformdag.runtime.manifest"},
}
IMPORT_ORDERS = (
    (
        "conformdag.runtime",
        "conformdag.runtime.profiles",
        "conformdag.runtime.manifest",
        "conformdag.runtime.docker",
    ),
    (
        "conformdag.runtime.docker",
        "conformdag.runtime.manifest",
        "conformdag.runtime.profiles",
        "conformdag.runtime",
    ),
    (
        "conformdag.runtime.manifest",
        "conformdag.runtime.profiles",
        "conformdag.runtime.docker",
        "conformdag.runtime",
    ),
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_owner_import_graph_has_only_the_approved_downward_edges() -> None:
    for owner, expected_imports in OWNER_IMPORTS.items():
        imported = _imported_modules(RUNTIME_PACKAGE / f"{owner}.py")
        runtime_imports = {
            module for module in imported if module == "conformdag.runtime" or module.startswith("conformdag.runtime.")
        }

        assert runtime_imports == expected_imports
        assert "conformdag.cli" not in imported
        assert not any(module.startswith("conformdag.platform") for module in imported)


@pytest.mark.parametrize("import_order", IMPORT_ORDERS, ids=("facade-first", "docker-first", "manifest-first"))
def test_runtime_legacy_and_owner_imports_work_in_isolated_orders(
    tmp_path: Path, import_order: tuple[str, ...]
) -> None:
    smoke = """
import importlib
import pickle
import sys

for module_name in sys.argv[1:]:
    importlib.import_module(module_name)

facade = importlib.import_module("conformdag.runtime")
profiles = importlib.import_module("conformdag.runtime.profiles")
manifest = importlib.import_module("conformdag.runtime.manifest")
docker = importlib.import_module("conformdag.runtime.docker")
assert facade.RuntimeProfile is profiles.RuntimeProfile
assert facade.RuntimeReleaseError is profiles.RuntimeReleaseError
assert facade.RuntimePhaseError is manifest.RuntimePhaseError
assert facade.DockerResult is docker.DockerResult
assert facade.DockerRunner is docker.DockerRunner
assert facade.execute_runtime is docker.execute_runtime

namespace = {}
exec("from conformdag.runtime import *", namespace)
assert list(namespace)[1:] == facade.__all__
assert pickle.loads(b"cconformdag.runtime\\nRuntimeProfile\\n.") is facade.RuntimeProfile
assert pickle.loads(b"cconformdag.runtime\\nRuntimeReleaseError\\n.") is facade.RuntimeReleaseError
assert pickle.loads(b"cconformdag.runtime\\nRuntimePhaseError\\n.") is facade.RuntimePhaseError
assert pickle.loads(b"cconformdag.runtime\\nDockerResult\\n.") is facade.DockerResult
assert facade.RuntimeProfile.__module__ == "conformdag.runtime.profiles"
assert facade.RuntimePhaseError.__module__ == "conformdag.runtime.manifest"
assert facade.DockerRunner.__module__ == "conformdag.runtime.docker"
assert not any(
    name == "conformdag.cli" or name.startswith("conformdag.platform")
    for name in sys.modules
)
print("runtime compatibility imports passed")
"""
    child_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
    }
    result = subprocess.run(
        [sys.executable, "-c", smoke, *import_order],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "runtime compatibility imports passed"
