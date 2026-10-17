"""Package imports keep the approved dependency graph and legacy pickle globals."""

from __future__ import annotations

import ast
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

import conformdag.models as models

DEPENDENCIES: dict[str, set[str]] = {
    "common": set(),
    "gates": {"common"},
    "policy": {"common", "gates"},
    "semantic": {"common"},
    "findings": {"common", "semantic"},
    "runtime": {"common"},
    "report": {"common", "gates", "findings", "runtime", "semantic"},
    "config": {"common"},
}

IMPORT_SMOKE = """
import importlib
import sys

for owner in sys.argv[1:]:
    importlib.import_module('conformdag.models.' + owner)
models = importlib.import_module('conformdag.models')
namespace = {}
exec('from conformdag.models import *', namespace)
assert list(namespace)[1:] == models.__all__
assert len(models.__all__) == 74
classes = 0
for name in models.__all__:
    value = getattr(models, name)
    assert namespace[name] is value
    if isinstance(value, type) and value.__module__.startswith('conformdag.models.'):
        classes += 1
        assert getattr(importlib.import_module(value.__module__), name) is value
assert classes == 58
for prefix in ('conformdag.application', 'conformdag.platform', 'conformdag.cli', 'fastapi', 'typer', 'sqlalchemy'):
    assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules), prefix
print('models import contract passed')
"""


@pytest.mark.parametrize("owner", DEPENDENCIES)
def test_owner_imports_follow_the_approved_acyclic_graph(owner: str) -> None:
    assert models.__file__ is not None
    source = (Path(models.__file__).parent / f"{owner}.py").read_text(encoding="utf-8")
    actual: set[str] = set()
    external = {"__future__", "datetime", "enum", "pathlib", "typing", "re", "pydantic"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert node.module is not None
            if node.level:
                assert node.level == 1 and node.module in DEPENDENCIES[owner], ast.unparse(node)
                actual.add(node.module)
            else:
                assert node.module.split(".")[0] in external, ast.unparse(node)
        elif isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in external for alias in node.names), ast.unparse(node)
    assert actual == DEPENDENCIES[owner]


@pytest.mark.parametrize(
    "order",
    [
        tuple(DEPENDENCIES),
        tuple(reversed(DEPENDENCIES)),
        ("report", "policy", "findings", "config", "semantic", "runtime", "gates", "common"),
    ],
)
def test_fresh_process_owner_imports_keep_facade_and_have_no_adapter_side_effects(
    order: tuple[str, ...], tmp_path: Path
) -> None:
    child_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
    }
    result = subprocess.run(
        [sys.executable, "-I", "-c", IMPORT_SMOKE, *order],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "models import contract passed"
    assert list(tmp_path.iterdir()) == []


def test_all_legacy_class_pickle_globals_resolve_to_facade_objects() -> None:
    classes = {
        name: getattr(models, name)
        for name in models.__all__
        if isinstance(getattr(models, name), type) and getattr(models, name).__module__.startswith("conformdag.models.")
    }
    assert len(classes) == 58
    for name, model in classes.items():
        legacy_global = f"cconformdag.models\n{name}\n.".encode()
        assert pickle.loads(legacy_global) is model  # noqa: S301 - trusted legacy globals, not external input


def test_new_owner_path_pickle_round_trips_nested_model_values() -> None:
    values = (
        models.ProjectConfig(),
        models.PolicyPack.model_validate(
            {
                "id": "pack",
                "version": "1",
                "policies": [],
                "quality_gates": [{"id": "release", "rules": [{"type": "max-severity", "severity": "high"}]}],
            }
        ),
        models.SemanticResponse(status="PASS", evidence="owner", explanation="ok", confidence=models.Confidence.HIGH),
    )
    for value in values:
        encoded = pickle.dumps(value, protocol=4)
        assert value.__class__.__module__.encode() in encoded
        decoded = pickle.loads(encoded)  # noqa: S301 - round trip of values created in this test
        assert type(decoded) is type(value)
        assert decoded.model_dump(mode="json") == value.model_dump(mode="json")


def test_facade_only_reexports_models_and_keeps_factories_private() -> None:
    assert models.__file__ is not None
    tree = ast.parse(Path(models.__file__).read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef)) for node in ast.walk(tree))
    assert not any(name.startswith("_") for name in models.__all__)
