"""Tests for the validated Docker runtime boundary."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from conformdag.models import ProjectRuntimeConfig
from conformdag.runtime import DockerRunner, RuntimePhaseError, build_runtime_manifest


def test_runtime_requires_explicit_profile_or_custom_image(tmp_path: Path) -> None:
    with pytest.raises(RuntimePhaseError, match="requires an Airflow profile"):
        build_runtime_manifest(
            tmp_path,
            ProjectRuntimeConfig(enabled=True),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
        )


def test_builds_custom_image_manifest(tmp_path: Path) -> None:
    manifest = build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image="registry.example/airflow@sha256:" + "a" * 64),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        ["**/.git/**"],
    )

    assert manifest.image is not None
    assert manifest.image.endswith("a" * 64)
    assert manifest.network_enabled is False


def test_docker_runner_uses_argument_arrays_and_validates_output(tmp_path: Path) -> None:
    runner = DockerRunner()
    output = '{"observations": [{"policy_id": "AIR-DET-001", "status": "PASS"}]}'
    completed = SimpleNamespace(stdout=output, stderr="", returncode=0)
    manifest = build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image="airflow-custom@sha256:" + "b" * 64),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )

    with patch("conformdag.runtime.subprocess.run", return_value=completed) as mocked:
        observations = runner.run_manifest(manifest, manifest.image or "", 30)

    assert observations[0].policy_id == "AIR-DET-001"
    command = mocked.call_args.args[0]
    assert command[0] == "docker"
    assert "--network=none" in command
    assert "--read-only" in command
    assert mocked.call_args.kwargs["shell"] is False


def test_digest_resolution_rejects_tag_only_images() -> None:
    runner = DockerRunner()
    completed = SimpleNamespace(stdout="airflow:latest\n", stderr="", returncode=0)

    with (
        patch("conformdag.runtime.subprocess.run", return_value=completed),
        pytest.raises(RuntimePhaseError, match="immutable digest"),
    ):
        runner.resolve_digest("airflow:latest")
