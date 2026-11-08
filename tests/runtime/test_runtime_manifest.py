"""Owner contracts for the C23 runtime manifest and observation boundary."""

from __future__ import annotations

import ast
import pickle
import re
from pathlib import Path
from typing import Any

import pytest

import conformdag.runtime as runtime
import conformdag.runtime.manifest as manifest_owner
from conformdag.models import (
    AirflowProfile,
    FindingStatus,
    ProjectRuntimeConfig,
    RuntimeManifest,
    RuntimeObservation,
)

PINNED_IMAGE = (
    "ghcr.io/parthmule28/conformdag/airflow-3.3.0@"
    "sha256:7d61c78df9dda06265997793d8ee3a38e03245073c937d0e5fca1c2835ed350b"
)


def _imported_modules(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_manifest_owner_is_the_single_source_of_truth() -> None:
    assert Path(manifest_owner.__file__).name == "manifest.py"
    assert Path(manifest_owner.__file__).parent.name == "runtime"
    assert manifest_owner.RuntimePhaseError is runtime.RuntimePhaseError
    assert manifest_owner.build_runtime_manifest is runtime.build_runtime_manifest
    assert manifest_owner.normalize_runtime_observations is runtime.normalize_runtime_observations
    assert runtime.RuntimePhaseError.__module__ == "conformdag.runtime.manifest"


def test_manifest_owner_builds_the_exact_supported_payload(tmp_path: Path) -> None:
    manifest = manifest_owner.build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
        ["AIR-DET-002", "AIR-DET-001"],
        ["dags/**/*.py"],
        ["**/.git/**"],
    )

    assert manifest == RuntimeManifest(
        repository_root=tmp_path.resolve(),
        include=["dags/**/*.py"],
        exclude=["**/.git/**"],
        policy_ids=["AIR-DET-002", "AIR-DET-001"],
        airflow_profile=AirflowProfile.AIRFLOW_3_3_0,
        image=PINNED_IMAGE,
        provider_versions={
            "apache-airflow-providers-standard": "1.15.0",
            "apache-airflow-providers-postgres": "6.8.0",
            "apache-airflow-providers-http": "6.0.4",
            "apache-airflow-providers-google": "22.2.2",
        },
        supported_profile=True,
        network_enabled=False,
        timeout_seconds=300,
    )


def test_manifest_owner_preserves_custom_image_acceptance(tmp_path: Path) -> None:
    permissive = "registry.example/airflow@sha256:" + "d" * 64 + ":suffix"
    manifest = manifest_owner.build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image=permissive, network_enabled=True),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )

    assert manifest.image == permissive
    assert manifest.supported_profile is False
    assert manifest.network_enabled is True
    assert manifest.provider_versions == {}


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (ProjectRuntimeConfig(enabled=False), "runtime analysis is not enabled"),
        (ProjectRuntimeConfig(enabled=True), "runtime requires an Airflow profile or custom image"),
        (
            ProjectRuntimeConfig(
                enabled=True,
                airflow_version=AirflowProfile.AIRFLOW_3_3_0,
                image="registry.example/airflow@sha256:" + "e" * 64,
            ),
            "runtime cannot select both an Airflow profile and custom image",
        ),
        (
            ProjectRuntimeConfig(enabled=True, image="registry.example/airflow:latest"),
            "custom runtime image must include an immutable sha256 digest",
        ),
        (
            ProjectRuntimeConfig(
                enabled=True,
                airflow_version=AirflowProfile.AIRFLOW_3_3_0,
                network_enabled=True,
            ),
            "network-enabled runtime execution is not supported for Airflow profiles",
        ),
    ],
)
def test_manifest_owner_preserves_validation_precedence(
    tmp_path: Path, config: ProjectRuntimeConfig, message: str
) -> None:
    with pytest.raises(manifest_owner.RuntimePhaseError, match=re.escape(message)):
        manifest_owner.build_runtime_manifest(tmp_path, config, [], ["dags/**/*.py"], [])


def test_manifest_owner_normalizes_observation_order() -> None:
    observations = [
        RuntimeObservation(policy_id="B", status=FindingStatus.PASS),
        RuntimeObservation(policy_id="A", status=FindingStatus.PASS),
        RuntimeObservation(policy_id="A", status=FindingStatus.ERROR, message="z"),
        RuntimeObservation(policy_id="A", status=FindingStatus.ERROR, message="a"),
    ]

    assert [
        (item.policy_id, item.status.value, item.message)
        for item in manifest_owner.normalize_runtime_observations(observations)
    ] == [
        ("A", "ERROR", "a"),
        ("A", "ERROR", "z"),
        ("A", "PASS", None),
        ("B", "PASS", None),
    ]


def test_manifest_owner_has_no_docker_or_facade_dependency() -> None:
    imported = _imported_modules(Path(manifest_owner.__file__))

    assert "conformdag.runtime" not in imported
    assert "conformdag.runtime.docker" not in imported
    assert "subprocess" not in imported
    assert "tempfile" not in imported
    assert "json" not in imported
    assert "conformdag.runtime.profiles" in imported
    assert "conformdag.models" in imported


def _forbidden_run(*_args: object, **_kwargs: object) -> Any:
    raise AssertionError("manifest owner must not invoke Docker")


def test_manifest_owner_never_invokes_docker(tmp_path: Path) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(runtime.subprocess, "run", _forbidden_run)

        manifest = manifest_owner.build_runtime_manifest(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
        )

    assert manifest.image == PINNED_IMAGE


def test_manifest_phase_error_pickle_global_still_resolves() -> None:
    loaded = pickle.loads(b"cconformdag.runtime\nRuntimePhaseError\n.")  # noqa: S301 - trusted historical bytes

    assert loaded is runtime.RuntimePhaseError
    assert loaded is manifest_owner.RuntimePhaseError


def test_manifest_owner_wildcard_surface_excludes_private_names() -> None:
    namespace: dict[str, Any] = {}
    exec("from conformdag.runtime.manifest import *", namespace)  # noqa: S102 - inspect owner surface
    assert "RuntimePhaseError" in namespace
    assert "build_runtime_manifest" in namespace
    assert "normalize_runtime_observations" in namespace
