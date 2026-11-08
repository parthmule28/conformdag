"""Validated Docker CLI boundary for optional runtime inspection."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
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
from conformdag.runtime.manifest import (
    RuntimePhaseError,
    build_runtime_manifest,
    normalize_runtime_observations,
)
from conformdag.runtime.profiles import (
    RUNTIME_PROFILES,
    RuntimeProfile,
    RuntimeReleaseError,
    runtime_profile,
    validate_runtime_release,
)

# Preserve the pre-package wildcard-import surface, including incidental imports.
__all__ = [
    "annotations",
    "json",
    "re",
    "subprocess",
    "tempfile",
    "Sequence",
    "dataclass",
    "Path",
    "Any",
    "cast",
    "AirflowProfile",
    "ProjectRuntimeConfig",
    "RuntimeManifest",
    "RuntimeObservation",
    "RuntimeProfile",
    "RUNTIME_PROFILES",
    "runtime_profile",
    "RuntimeReleaseError",
    "validate_runtime_release",
    "RuntimePhaseError",
    "DockerResult",
    "DockerRunner",
    "build_runtime_manifest",
    "normalize_runtime_observations",
    "execute_runtime",
]


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
        repository_root = manifest.repository_root.resolve()
        with tempfile.TemporaryDirectory(prefix="conformdag-runtime-") as temporary_directory:
            manifest_root = Path(temporary_directory).resolve()
            if manifest_root == repository_root or manifest_root.is_relative_to(repository_root):
                raise RuntimePhaseError("runtime manifest staging directory must be outside the scanned repository")
            manifest_path = manifest_root / "runtime-manifest.json"
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
                f"type=bind,src={repository_root},dst=/workspace,readonly",
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
        if image_digest != selected_image:
            raise RuntimePhaseError(
                "runtime image does not match the reviewed runtime profile identity: "
                f"expected {selected_image}, got {image_digest}"
            )
    else:
        image_digest = selected_image
    immutable_manifest = manifest.model_copy(update={"image": image_digest})
    observations = docker.run_manifest(
        immutable_manifest,
        image_digest,
        timeout_seconds=config.timeout_seconds,
    )
    return normalize_runtime_observations(observations), image_digest
