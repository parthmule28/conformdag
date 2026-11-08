"""C22 structural contract: semantic must be a package, not a shadowed module."""

from __future__ import annotations

from pathlib import Path

import conformdag.semantic as semantic

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "conformdag"


def test_semantic_import_origin_is_the_package_initializer() -> None:
    assert semantic.__file__ is not None
    origin = Path(semantic.__file__).resolve()

    assert origin.name == "__init__.py"
    assert origin.parent.name == "semantic"
    assert hasattr(semantic, "__path__")


def test_no_competing_semantic_module_or_shadow_package_exists() -> None:
    assert not (PACKAGE_ROOT / "semantic.py").exists()
    assert (PACKAGE_ROOT / "semantic" / "__init__.py").is_file()
