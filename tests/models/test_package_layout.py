"""The public models import is a package, never a shadowed module."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_models_resolve_to_package_without_module_shadow() -> None:
    spec = importlib.util.find_spec("conformdag.models")
    assert spec is not None
    assert spec.origin is not None
    assert spec.origin.endswith("/src/conformdag/models/__init__.py")
    assert spec.submodule_search_locations is not None
    assert not (Path(spec.origin).parent.parent / "models.py").exists()
