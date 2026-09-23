"""Configuration resolver contracts across the supported source layers."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, cast

import pytest
from ruamel.yaml import YAML

from conformdag.application.configuration import (
    EffectiveScanConfiguration,
    ScanOverrides,
    resolve_effective_configuration,
)
from conformdag.bundled import resolve_bundled_pack_path
from conformdag.models import (
    AirflowProfile,
    ProjectConfig,
    ProjectRuntimeConfig,
    ProjectSemanticConfig,
)

_PROFILE = AirflowProfile.AIRFLOW_3_3_0
_PROJECT_IMAGE = "ghcr.io/example/project@sha256:" + "1" * 64
_PLATFORM_IMAGE = "ghcr.io/example/platform@sha256:" + "2" * 64
_INVOCATION_IMAGE = "ghcr.io/example/invocation@sha256:" + "3" * 64

_PRECEDENCE_CASES: list[tuple[str, object, object, object, object]] = [
    (
        "policy_pack",
        Path("project-pack.yaml"),
        Path("/workspace/c07-platform-pack.yaml"),
        Path("invocation-pack.yaml"),
        Path("policies/pack.yaml"),
    ),
    ("airflow_profile", _PROFILE.value, _PROFILE, _PROFILE, None),
    ("runtime_image", _PROJECT_IMAGE, _PLATFORM_IMAGE, _INVOCATION_IMAGE, None),
    ("semantic_enabled", True, True, False, False),
    (
        "semantic_base_url",
        "https://project.example/v1",
        "https://platform.example/v1",
        "https://invoke.example/v1",
        None,
    ),
    ("semantic_model", "project-model", "platform-model", "invocation-model", None),
    ("semantic_structured_output", True, True, False, False),
]


def _write_project_config(root: Path, payload: dict[str, Any]) -> None:
    yaml = YAML(typ="safe")
    with (root / "conformdag.yaml").open("w", encoding="utf-8") as stream:
        yaml.dump(payload, stream)  # pyright: ignore[reportUnknownMemberType]


def _write_one_project_field(root: Path, field: str, value: object) -> None:
    if field == "policy_pack":
        payload = {"config_version": "1", "scan": {"policy_pack": cast(Path, value).as_posix()}}
    elif field == "airflow_profile":
        payload = {"config_version": "1", "runtime": {"airflow_version": str(value)}}
    elif field == "runtime_image":
        payload = {"config_version": "1", "runtime": {"image": value}}
    elif field == "semantic_enabled":
        payload = {"config_version": "1", "semantic": {"enabled": value}}
    elif field == "semantic_base_url":
        payload = {"config_version": "1", "semantic": {"base_url": value}}
    elif field == "semantic_model":
        payload = {"config_version": "1", "semantic": {"model": value}}
    elif field == "semantic_structured_output":
        payload = {"config_version": "1", "semantic": {"native_structured_output": value}}
    else:
        raise AssertionError(f"unhandled resolver field: {field}")
    _write_project_config(root, payload)


def _override(field: str, value: object | None) -> ScanOverrides:
    if value is None:
        return ScanOverrides()
    if field == "policy_pack":
        return ScanOverrides(policy_pack=cast(Path, value))
    if field == "airflow_profile":
        return ScanOverrides(airflow_profile=cast(AirflowProfile, value))
    if field == "runtime_image":
        return ScanOverrides(runtime_image=cast(str, value))
    if field == "semantic_enabled":
        return ScanOverrides(semantic_enabled=cast(bool, value))
    if field == "semantic_base_url":
        return ScanOverrides(semantic_base_url=cast(str, value))
    if field == "semantic_model":
        return ScanOverrides(semantic_model=cast(str, value))
    if field == "semantic_structured_output":
        return ScanOverrides(semantic_structured_output=cast(bool, value))
    raise AssertionError(f"unhandled resolver field: {field}")


def _resolved_value(configuration: EffectiveScanConfiguration, field: str) -> object:
    if field == "policy_pack":
        return configuration.resolved_policy_pack
    if field == "airflow_profile":
        return configuration.runtime.airflow_version
    if field == "runtime_image":
        return configuration.runtime.image
    if field == "semantic_enabled":
        return configuration.semantic.enabled
    if field == "semantic_base_url":
        return configuration.semantic.base_url
    if field == "semantic_model":
        return configuration.semantic.model
    if field == "semantic_structured_output":
        return configuration.semantic.native_structured_output
    raise AssertionError(f"unhandled resolver field: {field}")


@pytest.mark.parametrize(
    ("field", "project_value", "platform_value", "invocation_value", "default_value"),
    _PRECEDENCE_CASES,
)
@pytest.mark.parametrize("winner", ["invocation", "platform", "project", "default"])
def test_resolver_applies_precedence_for_each_field(
    tmp_path: Path,
    field: str,
    project_value: object,
    platform_value: object,
    invocation_value: object,
    default_value: object,
    winner: str,
) -> None:
    root = tmp_path / f"{field}-{winner}"
    root.mkdir()
    caller = tmp_path / "caller"
    caller.mkdir()
    if winner != "default":
        _write_one_project_field(root, field, project_value)

    invocation = _override(field, invocation_value if winner == "invocation" else None)
    platform_value_for_call = platform_value if winner in {"invocation", "platform"} else None
    platform = _override(field, platform_value_for_call)
    configuration = resolve_effective_configuration(
        root,
        invocation_overrides=invocation,
        platform_overrides=platform,
        invocation_working_directory=caller,
    )

    selected = {
        "invocation": invocation_value,
        "platform": platform_value,
        "project": project_value,
        "default": default_value,
    }[winner]
    if field == "policy_pack":
        selected_path = cast(Path, selected)
        if winner == "invocation":
            expected: object = (caller / selected_path).resolve()
        elif winner in {"project", "default"}:
            expected = (root / selected_path).resolve()
        else:
            expected = selected_path.resolve()
    elif field == "airflow_profile" and selected is not None:
        expected = AirflowProfile(cast(str, selected))
    else:
        expected = selected

    assert _resolved_value(configuration, field) == expected
    if field == "airflow_profile":
        assert configuration.runtime.enabled is (winner == "invocation")


def test_no_config_uses_complete_model_defaults(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    configuration = resolve_effective_configuration(root)

    assert configuration.project == ProjectConfig()
    assert configuration.runtime == ProjectRuntimeConfig()
    assert configuration.semantic == ProjectSemanticConfig()
    assert configuration.resolved_policy_pack == (root / "policies/pack.yaml").resolve()


def test_conflicting_invocation_runtime_selectors_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(ValueError, match="cannot be used together"):
        resolve_effective_configuration(
            root,
            invocation_overrides=ScanOverrides(
                airflow_profile=_PROFILE,
                runtime_image=_INVOCATION_IMAGE,
            ),
        )


def test_invocation_profile_enables_runtime_and_clears_project_image(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_project_config(root, {"config_version": "1", "runtime": {"image": _PROJECT_IMAGE}})

    configuration = resolve_effective_configuration(
        root,
        invocation_overrides=ScanOverrides(airflow_profile=_PROFILE),
    )

    assert configuration.runtime.enabled is True
    assert configuration.runtime.airflow_version is _PROFILE
    assert configuration.runtime.image is None


def test_invocation_image_enables_runtime_and_clears_project_profile(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_project_config(root, {"config_version": "1", "runtime": {"airflow_version": _PROFILE.value}})

    configuration = resolve_effective_configuration(
        root,
        invocation_overrides=ScanOverrides(runtime_image=_INVOCATION_IMAGE),
    )

    assert configuration.runtime.enabled is True
    assert configuration.runtime.image == _INVOCATION_IMAGE
    assert configuration.runtime.airflow_version is None


def test_platform_profile_does_not_enable_runtime_or_clear_project_image(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_project_config(root, {"config_version": "1", "runtime": {"image": _PROJECT_IMAGE}})

    configuration = resolve_effective_configuration(
        root,
        platform_overrides=ScanOverrides(airflow_profile=_PROFILE),
    )

    assert configuration.runtime.enabled is False
    assert configuration.runtime.airflow_version is _PROFILE
    assert configuration.runtime.image == _PROJECT_IMAGE


def test_policy_pack_path_origins_are_preserved(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    caller = tmp_path / "invoker"
    caller.mkdir()
    cli_pack = Path("local/custom-pack.yaml")

    invocation = resolve_effective_configuration(
        root,
        invocation_overrides=ScanOverrides(policy_pack=cli_pack),
        invocation_working_directory=caller,
    )
    assert invocation.resolved_policy_pack == (caller / cli_pack).resolve()

    project_pack = Path("project-policies/pack.yaml")
    _write_one_project_field(root, "policy_pack", project_pack)
    project = resolve_effective_configuration(root)
    assert project.resolved_policy_pack == (root / project_pack).resolve()

    platform_pack = (tmp_path / "workspace" / "resolved-pack.yaml").resolve()
    platform = resolve_effective_configuration(
        root,
        platform_overrides=ScanOverrides(policy_pack=platform_pack),
    )
    assert platform.resolved_policy_pack == platform_pack


def test_bundled_policy_pack_reference_uses_existing_alias_resolution(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    configuration = resolve_effective_configuration(
        root,
        invocation_overrides=ScanOverrides(policy_pack=Path("community")),
    )

    assert configuration.resolved_policy_pack == resolve_bundled_pack_path(Path("community"))


def test_effective_configuration_does_not_retain_secret_values_or_secret_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    secret = "C07-API-KEY-MUST-NOT-ENTER-CONFIG"
    monkeypatch.setenv("CONFORMDAG_C07_API_KEY", secret)
    _write_project_config(
        root,
        {
            "config_version": "1",
            "semantic": {"enabled": True, "api_key_env": "CONFORMDAG_C07_API_KEY"},
        },
    )

    overrides = ScanOverrides(semantic_enabled=True)
    configuration = resolve_effective_configuration(root, invocation_overrides=overrides)
    field_names = {
        field.name.lower() for value in (ScanOverrides, EffectiveScanConfiguration) for field in fields(value)
    }
    serialized = json.dumps(
        {
            "overrides": asdict(overrides),
            "configuration": {
                "project": configuration.project.model_dump(mode="json"),
                "resolved_policy_pack": str(configuration.resolved_policy_pack),
                "runtime": configuration.runtime.model_dump(mode="json"),
                "semantic": configuration.semantic.model_dump(mode="json"),
            },
        },
        default=str,
        sort_keys=True,
    )

    assert secret not in serialized
    assert not any(secret_field in name for name in field_names for secret_field in ("api_key", "token", "dsn"))
    assert "C07-API-KEY-MUST-NOT-ENTER-CONFIG" not in serialized
