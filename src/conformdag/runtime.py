"""Validated Docker CLI boundary for optional runtime inspection."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from conformdag.models import (
    AirflowProfile,
    ProjectRuntimeConfig,
    RuntimeManifest,
    RuntimeObservation,
)


@dataclass(frozen=True)
class RuntimeProfile:
    """Published metadata for a supported Airflow runtime image."""

    airflow_profile: AirflowProfile
    image: str
    provider_versions: dict[str, str]


RUNTIME_PROFILES: dict[AirflowProfile, RuntimeProfile] = {
    AirflowProfile.AIRFLOW_3_3_0: RuntimeProfile(
        airflow_profile=AirflowProfile.AIRFLOW_3_3_0,
        image="ghcr.io/parthmule28/conformdag/airflow-3.3.0:v0.1.0-beta.1",
        provider_versions={
            "apache-airflow-providers-standard": "1.15.0",
            "apache-airflow-providers-postgres": "6.8.0",
            "apache-airflow-providers-http": "6.0.4",
            "apache-airflow-providers-google": "22.1.0",
        },
    ),
}


def runtime_profile(profile: AirflowProfile) -> RuntimeProfile:
    """Return the immutable profile definition for a supported Airflow version."""
    return RUNTIME_PROFILES[profile]


class RuntimePhaseError(RuntimeError):
    """Raised when the runtime boundary cannot complete safely."""


@dataclass(frozen=True)
class DockerResult:
    stdout: str
    stderr: str
    returncode: int


class DockerRunner:
    """Run Docker commands through argument arrays with bounded execution."""

    def __init__(self, executable: str = "docker") -> None:
        self.executable = executable

    def run(self, args: Sequence[str], timeout_seconds: int) -> DockerResult:
        command = [self.executable, *args]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimePhaseError(f"Docker command failed: {exc}") from exc
        return DockerResult(completed.stdout, completed.stderr, completed.returncode)

    def require_daemon(self, timeout_seconds: int = 10) -> None:
        result = self.run(["version", "--format", "{{.Server.Version}}"], timeout_seconds)
        if result.returncode != 0:
            detail = result.stderr.strip() or "Docker daemon is unavailable"
            raise RuntimePhaseError(detail)

    def pull_image(self, image: str, timeout_seconds: int = 300) -> None:
        """Pull a published profile before resolving its immutable digest."""
        result = self.run(["pull", image], timeout_seconds)
        if result.returncode != 0:
            detail = result.stderr.strip() or f"failed to pull runtime image: {image}"
            raise RuntimePhaseError(detail)

    def resolve_digest(self, image: str, timeout_seconds: int = 30) -> str:
        result = self.run(
            ["image", "inspect", "--format", "{{index .RepoDigests 0}}", image],
            timeout_seconds,
        )
        if result.returncode != 0 or "@sha256:" not in result.stdout:
            detail = result.stderr.strip() or f"image has no immutable digest: {image}"
            raise RuntimePhaseError(detail)
        return result.stdout.strip()

    def run_manifest(
        self,
        manifest: RuntimeManifest,
        image: str,
        timeout_seconds: int,
    ) -> list[RuntimeObservation]:
        manifest_path = manifest.repository_root / ".conformdag" / "runtime-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        command = [
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
            f"type=bind,src={manifest.repository_root},dst=/workspace,readonly",
            "--mount",
            f"type=bind,src={manifest_path},dst=/conformdag/runtime-manifest.json,readonly",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108 - bounded container tmpfs
            image,
            "--manifest",
            "/conformdag/runtime-manifest.json",
        ]
        result = self.run(command, timeout_seconds)
        if result.returncode != 0:
            detail = result.stderr.strip() or "runtime container failed"
            raise RuntimePhaseError(detail)
        try:
            payload = json.loads(result.stdout)
            raw_observations: list[Any]
            if isinstance(payload, list):
                raw_observations = cast(list[Any], payload)
            else:
                raw_observations = cast(dict[str, Any], payload)["observations"]
            return [RuntimeObservation.model_validate(item) for item in raw_observations]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimePhaseError(f"invalid runtime observation output: {exc}") from exc


def build_runtime_manifest(
    root: Path,
    config: ProjectRuntimeConfig,
    policy_ids: list[str],
    include: list[str],
    exclude: list[str],
) -> RuntimeManifest:
    """Validate explicit runtime activation and create the host/container contract."""
    if not config.enabled:
        raise RuntimePhaseError("runtime analysis is not enabled")
    if config.airflow_version is None and not config.image:
        raise RuntimePhaseError("runtime requires an Airflow profile or custom image")
    if config.airflow_version is not None and config.image:
        raise RuntimePhaseError("runtime cannot select both an Airflow profile and custom image")
    if config.image and "@sha256:" not in config.image:
        raise RuntimePhaseError("custom runtime image must include an immutable sha256 digest")
    if config.network_enabled and config.airflow_version is not None:
        raise RuntimePhaseError(
            "network-enabled runtime execution is not supported for Airflow profiles"
        )
    profile = runtime_profile(config.airflow_version) if config.airflow_version else None
    image = config.image or (profile.image if profile else None)
    return RuntimeManifest(
        repository_root=root.resolve(),
        include=include,
        exclude=exclude,
        policy_ids=policy_ids,
        airflow_profile=config.airflow_version,
        image=image,
        provider_versions=profile.provider_versions if profile else {},
        supported_profile=profile is not None,
        network_enabled=config.network_enabled,
        timeout_seconds=config.timeout_seconds,
    )


def normalize_runtime_observations(
    observations: list[RuntimeObservation],
) -> list[RuntimeObservation]:
    """Return stable observation order and reject invalid non-outcome statuses."""
    return sorted(
        observations, key=lambda item: (item.policy_id, item.status.value, item.message or "")
    )


def execute_runtime(
    root: Path,
    config: ProjectRuntimeConfig,
    policy_ids: list[str],
    include: list[str],
    exclude: list[str],
    runner: DockerRunner | None = None,
) -> tuple[list[RuntimeObservation], str]:
    """Execute one validated runtime profile and return observations plus its digest."""
    manifest = build_runtime_manifest(root, config, policy_ids, include, exclude)
    selected_image = manifest.image
    if selected_image is None:
        raise RuntimePhaseError("runtime manifest did not resolve an image")
    docker = runner or DockerRunner()
    docker.require_daemon()
    if manifest.supported_profile:
        docker.pull_image(selected_image, timeout_seconds=config.timeout_seconds)
        image_digest = docker.resolve_digest(selected_image)
    else:
        image_digest = selected_image
    immutable_manifest = manifest.model_copy(update={"image": image_digest})
    observations = docker.run_manifest(
        immutable_manifest,
        image_digest,
        timeout_seconds=config.timeout_seconds,
    )
    return normalize_runtime_observations(observations), image_digest
