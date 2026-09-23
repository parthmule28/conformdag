"""Resolve scan configuration from adapter overrides and project defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conformdag.config import load_project_config
from conformdag.models import AirflowProfile, ProjectConfig, ProjectRuntimeConfig, ProjectSemanticConfig
from conformdag.policy import resolve_configured_policy_pack


@dataclass(frozen=True)
class ScanOverrides:
    """Partial scan settings supplied by an invocation or platform repository."""

    policy_pack: Path | None = None
    airflow_profile: AirflowProfile | None = None
    runtime_image: str | None = None
    semantic_enabled: bool | None = None
    semantic_base_url: str | None = None
    semantic_model: str | None = None
    semantic_structured_output: bool | None = None


_EMPTY_SCAN_OVERRIDES = ScanOverrides()


@dataclass(frozen=True)
class EffectiveScanConfiguration:
    """Complete project, phase, and policy-pack configuration for one scan."""

    project: ProjectConfig
    resolved_policy_pack: Path
    runtime: ProjectRuntimeConfig
    semantic: ProjectSemanticConfig


def _first_not_none[ValueT](invocation: ValueT | None, platform: ValueT | None, project: ValueT) -> ValueT:
    if invocation is not None:
        return invocation
    if platform is not None:
        return platform
    return project


def resolve_effective_configuration(
    repository_root: Path,
    *,
    invocation_overrides: ScanOverrides = _EMPTY_SCAN_OVERRIDES,
    platform_overrides: ScanOverrides = _EMPTY_SCAN_OVERRIDES,
    invocation_working_directory: Path | None = None,
) -> EffectiveScanConfiguration:
    """Resolve the four configuration layers once for an application scan."""
    if invocation_overrides.airflow_profile is not None and invocation_overrides.runtime_image is not None:
        raise ValueError("--runtime and --runtime-image cannot be used together")

    root = repository_root.resolve()
    project = load_project_config(root / "conformdag.yaml")

    if invocation_overrides.policy_pack is not None:
        configured_pack = invocation_overrides.policy_pack
        from_cli = True
    elif platform_overrides.policy_pack is not None:
        configured_pack = platform_overrides.policy_pack
        from_cli = False
    else:
        configured_pack = project.scan.policy_pack
        from_cli = False
    resolved_policy_pack = resolve_configured_policy_pack(
        configured_pack,
        scan_root=root,
        from_cli=from_cli,
        working_directory=invocation_working_directory,
    )

    airflow_profile = _first_not_none(
        invocation_overrides.airflow_profile,
        platform_overrides.airflow_profile,
        project.runtime.airflow_version,
    )
    runtime_image = _first_not_none(
        invocation_overrides.runtime_image,
        platform_overrides.runtime_image,
        project.runtime.image,
    )
    runtime_updates: dict[str, object] = {
        "airflow_version": airflow_profile,
        "image": runtime_image,
    }
    if invocation_overrides.airflow_profile is not None:
        runtime_updates.update(
            {"enabled": True, "airflow_version": invocation_overrides.airflow_profile, "image": None}
        )
    elif invocation_overrides.runtime_image is not None:
        runtime_updates.update({"enabled": True, "airflow_version": None, "image": invocation_overrides.runtime_image})
    runtime = project.runtime.model_copy(update=runtime_updates)

    semantic = project.semantic.model_copy(
        update={
            "enabled": _first_not_none(
                invocation_overrides.semantic_enabled,
                platform_overrides.semantic_enabled,
                project.semantic.enabled,
            ),
            "base_url": _first_not_none(
                invocation_overrides.semantic_base_url,
                platform_overrides.semantic_base_url,
                project.semantic.base_url,
            ),
            "model": _first_not_none(
                invocation_overrides.semantic_model,
                platform_overrides.semantic_model,
                project.semantic.model,
            ),
            "native_structured_output": _first_not_none(
                invocation_overrides.semantic_structured_output,
                platform_overrides.semantic_structured_output,
                project.semantic.native_structured_output,
            ),
        }
    )

    return EffectiveScanConfiguration(
        project=project,
        resolved_policy_pack=resolved_policy_pack,
        runtime=runtime,
        semantic=semantic,
    )
