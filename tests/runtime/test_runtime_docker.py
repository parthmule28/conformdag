"""Owner contracts for the C23 Docker runner and runtime execution boundary."""

from __future__ import annotations

import ast
import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

import conformdag.runtime as runtime
import conformdag.runtime.docker as docker_owner
from conformdag.models import AirflowProfile, FindingStatus, ProjectRuntimeConfig, RuntimeManifest, RuntimeObservation

PINNED_IMAGE = (
    "ghcr.io/parthmule28/conformdag/airflow-3.3.0@"
    "sha256:7d61c78df9dda06265997793d8ee3a38e03245073c937d0e5fca1c2835ed350b"
)
CUSTOM_IMAGE = "registry.example/airflow@sha256:" + "f" * 64


def _imported_modules(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_docker_owner_is_the_single_source_of_truth() -> None:
    assert Path(docker_owner.__file__).name == "docker.py"
    assert Path(docker_owner.__file__).parent.name == "runtime"
    assert docker_owner.DockerResult is runtime.DockerResult
    assert docker_owner.DockerRunner is runtime.DockerRunner
    assert docker_owner.execute_runtime is runtime.execute_runtime
    assert runtime.DockerResult.__module__ == "conformdag.runtime.docker"
    assert runtime.DockerRunner.__module__ == "conformdag.runtime.docker"


def test_docker_owner_keeps_the_facade_subprocess_patch_target() -> None:
    completed = SimpleNamespace(stdout="", stderr="", returncode=0)

    with patch("conformdag.runtime.subprocess.run", return_value=completed) as mocked:
        result = docker_owner.DockerRunner().run(["version"], 7)

    assert result == docker_owner.DockerResult("", "", 0)
    assert mocked.call_args.args[0] == ["docker", "version"]
    assert mocked.call_args.kwargs["timeout"] == 7


def test_docker_owner_builds_the_exact_sandbox_argv(tmp_path: Path) -> None:
    manifest = runtime.build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image=CUSTOM_IMAGE),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout='{"observations": [{"policy_id": "AIR-DET-001", "status": "PASS"}]}',
            stderr="",
            returncode=0,
        )

    with patch("conformdag.runtime.subprocess.run", side_effect=fake_run):
        observations = docker_owner.DockerRunner().run_manifest(manifest, CUSTOM_IMAGE, 30)

    command = cast(list[str], captured["command"])
    assert command[:14] == [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--user=airflow",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--cpus=1",
        "--memory=512m",
        "--pids-limit=128",
        "--mount",
        f"type=bind,src={tmp_path.resolve()},dst=/workspace,readonly",
        "--mount",
    ]
    assert command[14].startswith("type=bind,src=")
    assert command[14].endswith(",dst=/conformdag/runtime-manifest.json,readonly")
    assert command[15:] == [
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108 - sandbox boundary assertion
        CUSTOM_IMAGE,
        "--manifest",
        "/conformdag/runtime-manifest.json",
    ]
    assert captured["kwargs"] == {
        "capture_output": True,
        "text": True,
        "timeout": 30,
        "check": False,
        "shell": False,
    }
    assert [(item.policy_id, item.status.value) for item in observations] == [("AIR-DET-001", "PASS")]


def test_docker_owner_execute_runtime_returns_observations_and_digest(tmp_path: Path) -> None:
    runner = docker_owner.DockerRunner()
    observations = [
        RuntimeObservation(policy_id="B", status=FindingStatus.PASS),
        RuntimeObservation(policy_id="A", status=FindingStatus.FAIL),
    ]

    with (
        patch.object(runner, "require_daemon") as require_daemon,
        patch.object(runner, "run_manifest", return_value=observations) as run_manifest,
    ):
        resolved, digest = docker_owner.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, image=CUSTOM_IMAGE),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
            runner,
        )

    require_daemon.assert_called_once_with()
    assert digest == CUSTOM_IMAGE
    assert [(item.policy_id, item.status.value) for item in resolved] == [
        ("A", "FAIL"),
        ("B", "PASS"),
    ]
    assert run_manifest.call_args.args[1] == CUSTOM_IMAGE


def test_docker_owner_rejects_a_manifest_without_an_image(tmp_path: Path) -> None:
    manifest = RuntimeManifest(
        repository_root=tmp_path.resolve(),
        include=[],
        exclude=[],
        policy_ids=[],
        image=None,
    )

    with (
        patch.object(docker_owner, "build_runtime_manifest", return_value=manifest),
        pytest.raises(docker_owner.RuntimePhaseError, match="runtime manifest did not resolve an image"),
    ):
        docker_owner.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, image=CUSTOM_IMAGE),
            [],
            [],
            [],
        )


def test_docker_owner_rejects_a_mismatched_profile_digest(tmp_path: Path) -> None:
    runner = docker_owner.DockerRunner()
    unreviewed = "ghcr.io/parthmule28/conformdag/airflow-3.3.0@sha256:" + "0" * 64

    with (
        patch.object(runner, "require_daemon"),
        patch.object(runner, "pull_image"),
        patch.object(runner, "resolve_digest", return_value=unreviewed),
        patch.object(runner, "run_manifest") as run_manifest,
        pytest.raises(docker_owner.RuntimePhaseError, match="reviewed runtime profile identity"),
    ):
        docker_owner.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
            runner,
        )

    run_manifest.assert_not_called()


def test_docker_owner_has_no_facade_or_profile_dependency() -> None:
    imported = _imported_modules(Path(docker_owner.__file__))

    assert "conformdag.runtime" not in imported
    assert "conformdag.runtime.profiles" not in imported
    assert "conformdag.runtime.manifest" in imported
    assert "conformdag.models" in imported
    assert "subprocess" in imported
    assert "tempfile" in imported
    assert "json" in imported


def test_docker_result_pickle_global_still_resolves() -> None:
    loaded = pickle.loads(b"cconformdag.runtime\nDockerResult\n.")  # noqa: S301 - trusted historical bytes

    assert loaded is runtime.DockerResult
    assert loaded is docker_owner.DockerResult


def test_docker_owner_wildcard_surface_contains_the_public_runner() -> None:
    namespace: dict[str, Any] = {}
    exec("from conformdag.runtime.docker import *", namespace)  # noqa: S102 - inspect owner surface
    assert "DockerResult" in namespace
    assert "DockerRunner" in namespace
    assert "execute_runtime" in namespace


def test_docker_owner_preserves_the_exact_supported_profile_identity(tmp_path: Path) -> None:
    runner = docker_owner.DockerRunner()

    with (
        patch.object(runner, "require_daemon"),
        patch.object(runner, "pull_image") as pull_image,
        patch.object(runner, "resolve_digest", return_value=PINNED_IMAGE),
        patch.object(runner, "run_manifest", return_value=[]),
    ):
        _observations, digest = docker_owner.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
            [],
            [],
            [],
            runner,
        )

    assert digest == PINNED_IMAGE
    pull_image.assert_called_once_with(PINNED_IMAGE, timeout_seconds=300)
