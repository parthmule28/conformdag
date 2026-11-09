"""Owner contracts for the C23 runtime profile and release boundary."""

from __future__ import annotations

import ast
import pickle
import re
from pathlib import Path
from typing import Any, cast

import pytest

import conformdag.runtime as runtime
import conformdag.runtime.profiles as profiles
from conformdag.models import AirflowProfile


def _imported_modules(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_profile_owner_module_is_the_single_source_of_truth() -> None:
    assert Path(profiles.__file__).name == "profiles.py"
    assert Path(profiles.__file__).parent.name == "runtime"
    assert profiles.RuntimeProfile is runtime.RuntimeProfile
    assert profiles.RUNTIME_PROFILES is runtime.RUNTIME_PROFILES
    assert profiles.runtime_profile is runtime.runtime_profile
    assert profiles.RuntimeReleaseError is runtime.RuntimeReleaseError
    assert profiles.validate_runtime_release is runtime.validate_runtime_release


def test_profile_owner_keeps_the_frozen_metadata() -> None:
    profile = profiles.runtime_profile(AirflowProfile.AIRFLOW_3_3_0)

    assert profile.image == (
        "ghcr.io/parthmule28/conformdag/airflow-3.3.0@"
        "sha256:7d61c78df9dda06265997793d8ee3a38e03245073c937d0e5fca1c2835ed350b"
    )
    assert profile.reviewed_release == "v1.0.0-beta.1"
    assert profile.provider_versions == {
        "apache-airflow-providers-standard": "1.15.0",
        "apache-airflow-providers-postgres": "6.8.0",
        "apache-airflow-providers-http": "6.0.4",
        "apache-airflow-providers-google": "22.2.2",
    }
    assert profiles.RUNTIME_PROFILES[AirflowProfile.AIRFLOW_3_3_0] is profile
    assert cast(Any, profiles)._IMMUTABLE_DIGEST.pattern == r"@sha256:[0-9a-f]{64}$"


def test_profile_owner_classes_keep_natural_module_identity() -> None:
    assert runtime.RuntimeProfile.__module__ == "conformdag.runtime.profiles"
    assert runtime.RuntimeReleaseError.__module__ == "conformdag.runtime.profiles"


@pytest.mark.parametrize(
    ("name", "legacy_pickle"),
    [
        ("RuntimeProfile", b"cconformdag.runtime\nRuntimeProfile\n."),
        ("RuntimeReleaseError", b"cconformdag.runtime\nRuntimeReleaseError\n."),
    ],
)
def test_legacy_pickle_globals_resolve_through_the_facade(name: str, legacy_pickle: bytes) -> None:
    loaded = pickle.loads(legacy_pickle)  # noqa: S301 - trusted historical bytes

    assert loaded is getattr(runtime, name)
    assert loaded is getattr(profiles, name)


def test_profile_owner_has_no_docker_manifest_or_facade_dependency() -> None:
    imported = _imported_modules(Path(profiles.__file__))

    assert not {module for module in imported if module.startswith("conformdag.runtime")}
    assert "subprocess" not in imported
    assert "tempfile" not in imported
    assert "json" not in imported
    assert "conformdag.models" in imported


def test_facade_registry_mutation_reaches_owner_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = profiles.runtime_profile(AirflowProfile.AIRFLOW_3_3_0)
    tag_pinned = runtime.RuntimeProfile(
        airflow_profile=profile.airflow_profile,
        image="ghcr.io/parthmule28/conformdag/airflow-3.3.0:v9.9.9",
        provider_versions=profile.provider_versions,
        reviewed_release=profile.reviewed_release,
    )
    monkeypatch.setitem(runtime.RUNTIME_PROFILES, AirflowProfile.AIRFLOW_3_3_0, tag_pinned)

    assert profiles.RUNTIME_PROFILES[AirflowProfile.AIRFLOW_3_3_0] is tag_pinned
    with pytest.raises(profiles.RuntimeReleaseError, match="immutable sha256 digest"):
        profiles.validate_runtime_release(profile.reviewed_release)


def test_profile_owner_does_not_duplicate_the_registry() -> None:
    registry = profiles.RUNTIME_PROFILES

    assert registry is runtime.RUNTIME_PROFILES
    assert (
        registry[AirflowProfile.AIRFLOW_3_3_0].provider_versions
        is registry[AirflowProfile.AIRFLOW_3_3_0].provider_versions
    )
    assert re.search(r"@sha256:[0-9a-f]{64}$", registry[AirflowProfile.AIRFLOW_3_3_0].image)


def test_profile_owner_wildcard_surface_is_not_a_compatibility_contract() -> None:
    namespace: dict[str, Any] = {}
    exec("from conformdag.runtime.profiles import *", namespace)  # noqa: S102 - inspect owner surface
    assert "RuntimeProfile" in namespace
    assert "RUNTIME_PROFILES" in namespace
    assert "_IMMUTABLE_DIGEST" not in namespace
