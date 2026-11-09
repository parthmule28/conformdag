"""Host/container runtime manifest construction and observation normalization."""

from __future__ import annotations

from pathlib import Path

from conformdag.models import ProjectRuntimeConfig, RuntimeManifest, RuntimeObservation
from conformdag.runtime.profiles import runtime_profile


class RuntimePhaseError(RuntimeError):
    """Raised when the runtime boundary cannot complete safely."""


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
        raise RuntimePhaseError("network-enabled runtime execution is not supported for Airflow profiles")
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
    return sorted(observations, key=lambda item: (item.policy_id, item.status.value, item.message or ""))
