"""Tests for the validated Docker runtime boundary."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from conformdag.models import AirflowProfile, ProjectRuntimeConfig
from conformdag.runtime import (
    DockerRunner,
    RuntimePhaseError,
    build_runtime_manifest,
    execute_runtime,
)

pytestmark = pytest.mark.runtime


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


def test_custom_image_requires_immutable_digest(tmp_path: Path) -> None:
    with pytest.raises(RuntimePhaseError, match="immutable sha256 digest"):
        build_runtime_manifest(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, image="registry.example/airflow:latest"),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
        )


def test_supported_profile_rejects_network_enablement(tmp_path: Path) -> None:
    with pytest.raises(RuntimePhaseError, match="network-enabled"):
        build_runtime_manifest(
            tmp_path,
            ProjectRuntimeConfig(
                enabled=True,
                airflow_version=AirflowProfile.AIRFLOW_3_3_0,
                network_enabled=True,
            ),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
        )


def test_supported_profile_resolves_pinned_image_and_providers(tmp_path: Path) -> None:
    manifest = build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )

    assert manifest.supported_profile is True
    assert manifest.image == "ghcr.io/parthmule28/conformdag/airflow-3.3.0:v0.1.0-beta.1"
    assert manifest.provider_versions["apache-airflow-providers-google"] == "22.2.2"


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
    assert "--user=airflow" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges:true" in command
    assert "--cpus=1" in command
    assert "--memory=512m" in command
    assert "--pids-limit=128" in command
    assert "/tmp:rw,noexec,nosuid,size=64m" in command  # noqa: S108 - boundary assertion
    assert command[-2:] == ["--manifest", "/conformdag/runtime-manifest.json"]
    assert mocked.call_args.kwargs["shell"] is False


def test_runtime_import_failure_is_returned_as_structured_error(tmp_path: Path) -> None:
    runner = DockerRunner()
    output = '{"observations": [{"policy_id": "AIR-DET-001", "status": "ERROR", "message": "import failed"}]}'
    manifest = build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image="airflow-custom@sha256:" + "c" * 64),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )

    with patch(
        "conformdag.runtime.subprocess.run",
        return_value=SimpleNamespace(stdout=output, stderr="", returncode=0),
    ):
        observations = runner.run_manifest(manifest, manifest.image or "", 30)

    assert observations[0].status == "ERROR"
    assert observations[0].message == "import failed"


def test_runtime_rejects_malformed_output(tmp_path: Path) -> None:
    runner = DockerRunner()
    manifest = build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image="airflow-custom@sha256:" + "d" * 64),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )

    with (
        patch(
            "conformdag.runtime.subprocess.run",
            return_value=SimpleNamespace(stdout="not-json", stderr="", returncode=0),
        ),
        pytest.raises(RuntimePhaseError, match="invalid runtime observation output"),
    ):
        runner.run_manifest(manifest, manifest.image or "", 30)


def test_runtime_entrypoint_reserves_stdout_for_json_protocol() -> None:
    entrypoint = Path("runtime/entrypoint.py").resolve()
    probe = (
        "import runpy\n"
        f"module = runpy.run_path({str(entrypoint)!r}, run_name='runtime_probe')\n"
        "protocol = module['_reserve_protocol_stdout']()\n"
        "print('airflow diagnostic', flush=True)\n"
        "protocol.write('{\"observations\": []}\\n')\n"
        "protocol.close()\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == '{"observations": []}\n'
    assert completed.stderr == "airflow diagnostic\n"


def test_runtime_failure_includes_container_diagnostics(tmp_path: Path) -> None:
    runner = DockerRunner()
    manifest = build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image="airflow-custom@sha256:" + "e" * 64),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )

    with (
        patch(
            "conformdag.runtime.subprocess.run",
            return_value=SimpleNamespace(stdout="", stderr="permission denied", returncode=1),
        ),
        pytest.raises(RuntimePhaseError, match="permission denied"),
    ):
        runner.run_manifest(manifest, manifest.image or "", 30)


def test_runtime_daemon_failure_is_reported() -> None:
    runner = DockerRunner()

    with (
        patch(
            "conformdag.runtime.subprocess.run",
            return_value=SimpleNamespace(stdout="", stderr="Cannot connect to Docker", returncode=1),
        ),
        pytest.raises(RuntimePhaseError, match="Cannot connect to Docker"),
    ):
        runner.require_daemon()


def test_published_profile_is_pulled_and_executed_by_digest(tmp_path: Path) -> None:
    runner = DockerRunner()
    digest = "ghcr.io/parthmule28/conformdag/airflow-3.3.0@sha256:" + "f" * 64

    with (
        patch.object(runner, "require_daemon") as require_daemon,
        patch.object(runner, "pull_image") as pull_image,
        patch.object(runner, "resolve_digest", return_value=digest) as resolve_digest,
        patch.object(runner, "run_manifest", return_value=[]) as run_manifest,
    ):
        observations, resolved = execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(
                enabled=True,
                airflow_version=AirflowProfile.AIRFLOW_3_3_0,
            ),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
            runner,
        )

    assert observations == []
    assert resolved == digest
    require_daemon.assert_called_once_with()
    pull_image.assert_called_once_with(
        "ghcr.io/parthmule28/conformdag/airflow-3.3.0:v0.1.0-beta.1",
        timeout_seconds=300,
    )
    resolve_digest.assert_called_once()
    assert run_manifest.call_args.args[1] == digest


def test_digest_resolution_rejects_tag_only_images() -> None:
    runner = DockerRunner()
    completed = SimpleNamespace(stdout="airflow:latest\n", stderr="", returncode=0)

    with (
        patch("conformdag.runtime.subprocess.run", return_value=completed),
        pytest.raises(RuntimePhaseError, match="immutable digest"),
    ):
        runner.resolve_digest("airflow:latest")
