"""Fast characterization contracts for the pre-C23 runtime module.

These tests are deliberately unmarked: the historical ``tests/test_runtime.py``
suite is entirely ``pytest.mark.runtime`` and therefore skipped by the default
gate. They freeze the public surface, validation/error strings, manifest bytes,
Docker argument arrays and mocked process behavior that the C23 package split
must preserve. They must keep passing unchanged after the move.
"""

from __future__ import annotations
import __future__

import collections.abc
import contextlib
import dataclasses
import hashlib
import inspect
import json
import pickle
import re
import subprocess
import sys
import tempfile
import typing
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

import conformdag.runtime as runtime
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
PINNED_PROVIDERS = {
    "apache-airflow-providers-standard": "1.15.0",
    "apache-airflow-providers-postgres": "6.8.0",
    "apache-airflow-providers-http": "6.0.4",
    "apache-airflow-providers-google": "22.2.2",
}
REVIEWED_RELEASE = "v1.0.0-beta.1"
CUSTOM_IMAGE = "registry.example/airflow@sha256:" + "a" * 64

RUNTIME_WILDCARD = [
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

SCHEMA_HASHES = {
    "policy-pack.json": "dd6d7a46ada43036b37bdac53df158635f76bd64f1d309993c90ba286ccef143",
    "project-config.json": "7915a1880b803447c3d634d3be8d90d813898e6a15663ea338685b4c8ba35f3a",
    "runtime-manifest.json": "471a3e650fb037afd1d6993aae5d93e1552ceab552ff9422810e4ffc149779de",
    "scan-report.json": "ae1a33e78e0ab5a72a13f629cbcd91de6e3f64baf34af99e47142a2616486695",
    "semantic-request.json": "e63906384ae7bf2e450095481b4d7df43276277a64dbafe5e9c52379c8e3d59f",
    "semantic-response.json": "b26267fa206e994ccfd741c903a35ae2d222ff475416d86d195b47e35cefec75",
    "suppression.json": "0ef3eb979cb76d384db1407edca057485069031dc6a8d2086244b17166bdd529",
}


def _star_import() -> list[str]:
    namespace: dict[str, Any] = {}
    exec("from conformdag.runtime import *", namespace)  # noqa: S102 - explicit contract check
    return [name for name in namespace if not name.startswith("__")]


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _parameters(value: Callable[..., object] | type[object]) -> list[str]:
    return list(inspect.signature(value).parameters)


def _manifest_mount_path(command: list[str]) -> Path:
    mount = next(item for item in command if item.startswith("type=bind,src=") and "runtime-manifest.json" in item)
    return Path(mount.removeprefix("type=bind,src=").split(",dst=", maxsplit=1)[0])


def _repository_mount_path(command: list[str]) -> Path:
    mount = next(item for item in command if item.startswith("type=bind,src=") and "dst=/workspace" in item)
    return Path(mount.removeprefix("type=bind,src=").split(",dst=", maxsplit=1)[0])


def _custom_manifest(root: Path) -> RuntimeManifest:
    return runtime.build_runtime_manifest(
        root,
        ProjectRuntimeConfig(enabled=True, image=CUSTOM_IMAGE),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        ["**/.git/**"],
    )


def test_runtime_is_a_package_after_the_atomic_bootstrap() -> None:
    module_path = Path(runtime.__file__)

    assert module_path.name == "__init__.py"
    assert module_path.parent.name == "runtime"
    assert hasattr(runtime, "__path__")


def test_legacy_wildcard_bindings_and_order_are_frozen() -> None:
    assert _star_import() == RUNTIME_WILDCARD


def test_incidental_wildcard_objects_keep_their_stdlib_identity() -> None:
    assert runtime.annotations is __future__.annotations
    assert runtime.json is json
    assert runtime.re is re
    assert runtime.subprocess is subprocess
    assert runtime.tempfile is tempfile
    assert runtime.Sequence is collections.abc.Sequence
    assert runtime.dataclass is dataclasses.dataclass
    assert runtime.Path is Path
    assert runtime.Any is typing.Any
    assert runtime.cast is typing.cast
    assert runtime.AirflowProfile is AirflowProfile
    assert runtime.ProjectRuntimeConfig is ProjectRuntimeConfig
    assert runtime.RuntimeManifest is RuntimeManifest
    assert runtime.RuntimeObservation is RuntimeObservation


@pytest.mark.parametrize(
    ("name", "legacy_pickle"),
    [
        ("RuntimeProfile", b"cconformdag.runtime\nRuntimeProfile\n."),
        ("DockerResult", b"cconformdag.runtime\nDockerResult\n."),
        ("RuntimePhaseError", b"cconformdag.runtime\nRuntimePhaseError\n."),
        ("RuntimeReleaseError", b"cconformdag.runtime\nRuntimeReleaseError\n."),
    ],
)
def test_legacy_pickle_globals_still_resolve(name: str, legacy_pickle: bytes) -> None:
    loaded = pickle.loads(legacy_pickle)  # noqa: S301 - trusted historical bytes
    assert loaded is getattr(runtime, name)


def test_public_callable_signatures_and_defaults_are_stable() -> None:
    assert _parameters(runtime.runtime_profile) == ["profile"]
    assert _parameters(runtime.validate_runtime_release) == ["release_ref"]
    assert _parameters(runtime.build_runtime_manifest) == [
        "root",
        "config",
        "policy_ids",
        "include",
        "exclude",
    ]
    assert _parameters(runtime.normalize_runtime_observations) == ["observations"]
    assert _parameters(runtime.execute_runtime) == [
        "root",
        "config",
        "policy_ids",
        "include",
        "exclude",
        "runner",
    ]
    assert inspect.signature(runtime.execute_runtime).parameters["runner"].default is None

    assert _parameters(runtime.DockerRunner.__init__) == ["self", "executable"]
    assert inspect.signature(runtime.DockerRunner.__init__).parameters["executable"].default == "docker"
    assert _parameters(runtime.DockerRunner.run) == ["self", "args", "timeout_seconds"]
    assert _parameters(runtime.DockerRunner.require_daemon) == ["self", "timeout_seconds"]
    assert inspect.signature(runtime.DockerRunner.require_daemon).parameters["timeout_seconds"].default == 10
    assert _parameters(runtime.DockerRunner.pull_image) == ["self", "image", "timeout_seconds"]
    assert inspect.signature(runtime.DockerRunner.pull_image).parameters["timeout_seconds"].default == 300
    assert _parameters(runtime.DockerRunner.resolve_digest) == ["self", "image", "timeout_seconds"]
    assert inspect.signature(runtime.DockerRunner.resolve_digest).parameters["timeout_seconds"].default == 30
    assert _parameters(runtime.DockerRunner.run_manifest) == ["self", "manifest", "image", "timeout_seconds"]


def test_dataclass_shapes_and_frozen_semantics_are_stable() -> None:
    assert [field.name for field in fields(runtime.RuntimeProfile)] == [
        "airflow_profile",
        "image",
        "provider_versions",
        "reviewed_release",
    ]
    assert [field.name for field in fields(runtime.DockerResult)] == ["stdout", "stderr", "returncode"]
    assert cast(Any, runtime.RuntimeProfile).__dataclass_params__.frozen is True
    assert cast(Any, runtime.DockerResult).__dataclass_params__.frozen is True
    profile = runtime.runtime_profile(AirflowProfile.AIRFLOW_3_3_0)
    with pytest.raises(FrozenInstanceError):
        cast(Any, profile).image = "changed"


def test_reviewed_profile_identity_is_frozen() -> None:
    profile = runtime.runtime_profile(AirflowProfile.AIRFLOW_3_3_0)

    assert profile.airflow_profile is AirflowProfile.AIRFLOW_3_3_0
    assert profile.image == PINNED_IMAGE
    assert profile.provider_versions == PINNED_PROVIDERS
    assert profile.reviewed_release == REVIEWED_RELEASE
    assert {AirflowProfile.AIRFLOW_3_3_0: profile} == runtime.RUNTIME_PROFILES
    assert runtime.RUNTIME_PROFILES[AirflowProfile.AIRFLOW_3_3_0] is profile
    assert runtime.RUNTIME_PROFILES[AirflowProfile.AIRFLOW_3_3_0].provider_versions is profile.provider_versions


def test_release_validation_accepts_only_the_reviewed_ref() -> None:
    runtime.validate_runtime_release(REVIEWED_RELEASE)

    with pytest.raises(
        runtime.RuntimeReleaseError,
        match=f"refusing unreviewed release {re.escape('v9.9.9-rc.999')}",
    ):
        runtime.validate_runtime_release("v9.9.9-rc.999")

    with pytest.raises(runtime.RuntimeReleaseError, match=re.escape(REVIEWED_RELEASE)):
        runtime.validate_runtime_release("v9.9.9-rc.999")


def test_release_validation_requires_a_trailing_immutable_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = runtime.runtime_profile(AirflowProfile.AIRFLOW_3_3_0)
    tag_pinned = runtime.RuntimeProfile(
        airflow_profile=profile.airflow_profile,
        image="ghcr.io/parthmule28/conformdag/airflow-3.3.0:v9.9.9",
        provider_versions=profile.provider_versions,
        reviewed_release=profile.reviewed_release,
    )
    monkeypatch.setitem(runtime.RUNTIME_PROFILES, AirflowProfile.AIRFLOW_3_3_0, tag_pinned)

    with pytest.raises(runtime.RuntimeReleaseError, match="immutable sha256 digest"):
        runtime.validate_runtime_release(profile.reviewed_release)

    suffixed = runtime.RuntimeProfile(
        airflow_profile=profile.airflow_profile,
        image=PINNED_IMAGE + ":extra",
        provider_versions=profile.provider_versions,
        reviewed_release=profile.reviewed_release,
    )
    monkeypatch.setitem(runtime.RUNTIME_PROFILES, AirflowProfile.AIRFLOW_3_3_0, suffixed)

    with pytest.raises(runtime.RuntimeReleaseError, match="immutable sha256 digest"):
        runtime.validate_runtime_release(profile.reviewed_release)


def test_supported_profile_manifest_payload_is_frozen(tmp_path: Path) -> None:
    manifest = runtime.build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
        ["AIR-DET-002", "AIR-DET-001"],
        ["dags/**/*.py", "plugins/**/*.py"],
        ["**/.git/**"],
    )

    assert manifest.model_dump(mode="json") == {
        "schema_version": "1",
        "repository_root": str(tmp_path.resolve()),
        "include": ["dags/**/*.py", "plugins/**/*.py"],
        "exclude": ["**/.git/**"],
        "policy_ids": ["AIR-DET-002", "AIR-DET-001"],
        "airflow_profile": "3.3.0",
        "image": PINNED_IMAGE,
        "provider_versions": PINNED_PROVIDERS,
        "supported_profile": True,
        "network_enabled": False,
        "timeout_seconds": 300,
    }
    assert manifest.model_dump_json(indent=2) + "\n" == json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"


def test_custom_image_manifest_preserves_existing_acceptance_and_network_flag(tmp_path: Path) -> None:
    permissive_image = "registry.example/airflow@sha256:" + "b" * 64 + ":suffix"
    manifest = runtime.build_runtime_manifest(
        tmp_path,
        ProjectRuntimeConfig(enabled=True, image=permissive_image, network_enabled=True, timeout_seconds=42),
        ["AIR-DET-001"],
        ["dags/**/*.py"],
        [],
    )

    assert manifest.image == permissive_image
    assert manifest.airflow_profile is None
    assert manifest.provider_versions == {}
    assert manifest.supported_profile is False
    assert manifest.network_enabled is True
    assert manifest.timeout_seconds == 42
    assert manifest.repository_root == tmp_path.resolve()


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (ProjectRuntimeConfig(enabled=False), "runtime analysis is not enabled"),
        (ProjectRuntimeConfig(enabled=True), "runtime requires an Airflow profile or custom image"),
        (
            ProjectRuntimeConfig(
                enabled=True,
                airflow_version=AirflowProfile.AIRFLOW_3_3_0,
                image="registry.example/airflow:latest",
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
def test_manifest_validation_precedence_and_messages_are_frozen(
    tmp_path: Path,
    config: ProjectRuntimeConfig,
    message: str,
) -> None:
    with pytest.raises(runtime.RuntimePhaseError, match=re.escape(message)):
        runtime.build_runtime_manifest(tmp_path, config, [], ["dags/**/*.py"], [])


def test_build_runtime_manifest_never_invokes_docker(tmp_path: Path) -> None:
    with patch("conformdag.runtime.subprocess.run") as mocked:
        runtime.build_runtime_manifest(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
        )

    mocked.assert_not_called()


def test_normalize_runtime_observations_sorts_by_policy_status_and_message() -> None:
    observations = [
        RuntimeObservation(policy_id="B", status=FindingStatus.PASS),
        RuntimeObservation(policy_id="A", status=FindingStatus.PASS),
        RuntimeObservation(policy_id="A", status=FindingStatus.ERROR, message="z"),
        RuntimeObservation(policy_id="A", status=FindingStatus.ERROR, message="a"),
    ]

    assert [
        (item.policy_id, item.status.value, item.message)
        for item in runtime.normalize_runtime_observations(observations)
    ] == [
        ("A", "ERROR", "a"),
        ("A", "ERROR", "z"),
        ("A", "PASS", None),
        ("B", "PASS", None),
    ]


def test_docker_runner_uses_the_exact_sandbox_argument_array(tmp_path: Path) -> None:
    manifest = _custom_manifest(tmp_path)
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        manifest_path = _manifest_mount_path(command)
        captured["manifest_path"] = manifest_path
        captured["manifest_bytes"] = manifest_path.read_text(encoding="utf-8")
        return _completed(stdout='{"observations": [{"policy_id": "AIR-DET-001", "status": "PASS"}]}')

    with patch("conformdag.runtime.subprocess.run", side_effect=fake_run) as mocked:
        observations = runtime.DockerRunner().run_manifest(manifest, CUSTOM_IMAGE, 30)

    command = cast(list[str], captured["command"])
    manifest_path = cast(Path, captured["manifest_path"])
    assert command == [
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
        f"type=bind,src={manifest_path},dst=/conformdag/runtime-manifest.json,readonly",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108 - boundary assertion
        CUSTOM_IMAGE,
        "--manifest",
        "/conformdag/runtime-manifest.json",
    ]
    assert _repository_mount_path(command) == tmp_path.resolve()
    assert not manifest_path.is_relative_to(tmp_path.resolve())
    assert captured["manifest_bytes"] == manifest.model_dump_json(indent=2) + "\n"
    assert captured["kwargs"] == {
        "capture_output": True,
        "text": True,
        "timeout": 30,
        "check": False,
        "shell": False,
    }
    assert mocked.call_count == 1
    assert [(item.policy_id, item.status.value) for item in observations] == [("AIR-DET-001", "PASS")]


@pytest.mark.parametrize(
    "payload",
    [
        '{"observations": [{"policy_id": "AIR-DET-001", "status": "PASS"}]}',
        '[{"policy_id": "AIR-DET-001", "status": "PASS"}]',
    ],
)
def test_run_manifest_accepts_dict_and_list_observation_payloads(tmp_path: Path, payload: str) -> None:
    manifest = _custom_manifest(tmp_path)

    with patch("conformdag.runtime.subprocess.run", return_value=_completed(stdout=payload)):
        observations = runtime.DockerRunner().run_manifest(manifest, CUSTOM_IMAGE, 30)

    assert [(item.policy_id, item.status.value) for item in observations] == [("AIR-DET-001", "PASS")]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not-json", "invalid runtime observation output: Expecting value"),
        ("{}", "invalid runtime observation output: 'observations'"),
        ('{"observations": [{"status": "PASS"}]}', "invalid runtime observation output:"),
        ('{"observations": [{"policy_id": "P", "status": "BOGUS"}]}', "invalid runtime observation output:"),
        ('{"observations": [{"policy_id": 7, "status": "PASS"}]}', "invalid runtime observation output:"),
    ],
)
def test_run_manifest_rejects_malformed_output(tmp_path: Path, payload: str, message: str) -> None:
    manifest = _custom_manifest(tmp_path)

    with (
        patch("conformdag.runtime.subprocess.run", return_value=_completed(stdout=payload)),
        pytest.raises(runtime.RuntimePhaseError, match=re.escape(message)),
    ):
        runtime.DockerRunner().run_manifest(manifest, CUSTOM_IMAGE, 30)


@pytest.mark.parametrize(
    ("stderr", "message"),
    [
        ("permission denied", "permission denied"),
        ("", "runtime container failed"),
    ],
)
def test_run_manifest_container_failure_uses_stderr_or_default(tmp_path: Path, stderr: str, message: str) -> None:
    manifest = _custom_manifest(tmp_path)

    with (
        patch(
            "conformdag.runtime.subprocess.run",
            return_value=_completed(stderr=stderr, returncode=1),
        ),
        pytest.raises(runtime.RuntimePhaseError, match=re.escape(message)),
    ):
        runtime.DockerRunner().run_manifest(manifest, CUSTOM_IMAGE, 30)


@pytest.mark.parametrize("staging", ["repository", "repository-child"])
def test_run_manifest_rejects_staging_inside_the_scanned_repository(tmp_path: Path, staging: str) -> None:
    manifest = _custom_manifest(tmp_path)
    target = tmp_path if staging == "repository" else tmp_path / "staging"

    def fake_temporary_directory(prefix: str = "") -> contextlib.AbstractContextManager[Path]:
        _ = prefix
        return contextlib.nullcontext(target)

    with (
        patch(
            "conformdag.runtime.tempfile.TemporaryDirectory",
            side_effect=fake_temporary_directory,
        ),
        pytest.raises(
            runtime.RuntimePhaseError,
            match="runtime manifest staging directory must be outside the scanned repository",
        ),
    ):
        runtime.DockerRunner().run_manifest(manifest, CUSTOM_IMAGE, 30)


def test_docker_runner_converts_os_and_timeout_failures() -> None:
    with (
        patch("conformdag.runtime.subprocess.run", side_effect=OSError("docker missing")),
        pytest.raises(runtime.RuntimePhaseError, match="Docker command failed: docker missing"),
    ):
        runtime.DockerRunner().run(["version"], 10)

    with (
        patch(
            "conformdag.runtime.subprocess.run",
            side_effect=subprocess.TimeoutExpired("docker", 10),
        ),
        pytest.raises(runtime.RuntimePhaseError, match="Docker command failed:"),
    ):
        runtime.DockerRunner().run(["version"], 10)


def test_require_daemon_uses_the_exact_command_and_timeout() -> None:
    with patch(
        "conformdag.runtime.subprocess.run",
        return_value=_completed(stdout="27.0.0"),
    ) as mocked:
        runtime.DockerRunner().require_daemon()

    assert mocked.call_args.args[0] == ["docker", "version", "--format", "{{.Server.Version}}"]
    assert mocked.call_args.kwargs["timeout"] == 10

    with (
        patch(
            "conformdag.runtime.subprocess.run",
            return_value=_completed(stderr="Cannot connect to Docker", returncode=1),
        ),
        pytest.raises(runtime.RuntimePhaseError, match="Cannot connect to Docker"),
    ):
        runtime.DockerRunner().require_daemon()

    with (
        patch("conformdag.runtime.subprocess.run", return_value=_completed(returncode=1)),
        pytest.raises(runtime.RuntimePhaseError, match="Docker daemon is unavailable"),
    ):
        runtime.DockerRunner().require_daemon()


@pytest.mark.parametrize(
    ("stderr", "returncode", "message"),
    [
        ("", 0, None),
        ("pull denied", 1, "pull denied"),
        ("", 1, f"failed to pull runtime image: {CUSTOM_IMAGE}"),
    ],
)
def test_pull_image_uses_the_exact_command_and_timeout(stderr: str, returncode: int, message: str | None) -> None:
    with patch(
        "conformdag.runtime.subprocess.run",
        return_value=_completed(stderr=stderr, returncode=returncode),
    ) as mocked:
        if message is None:
            runtime.DockerRunner().pull_image(CUSTOM_IMAGE)
        else:
            with pytest.raises(runtime.RuntimePhaseError, match=re.escape(message)):
                runtime.DockerRunner().pull_image(CUSTOM_IMAGE)

    assert mocked.call_args.args[0] == ["docker", "pull", CUSTOM_IMAGE]
    assert mocked.call_args.kwargs["timeout"] == 300


def test_resolve_digest_uses_the_exact_command_and_timeout() -> None:
    digest = "ghcr.io/parthmule28/conformdag/airflow-3.3.0@sha256:" + "c" * 64
    with patch(
        "conformdag.runtime.subprocess.run",
        return_value=_completed(stdout=digest + "\n"),
    ) as mocked:
        resolved = runtime.DockerRunner().resolve_digest(CUSTOM_IMAGE)

    assert resolved == digest
    assert mocked.call_args.args[0] == [
        "docker",
        "image",
        "inspect",
        "--format",
        "{{index .RepoDigests 0}}",
        CUSTOM_IMAGE,
    ]
    assert mocked.call_args.kwargs["timeout"] == 30


@pytest.mark.parametrize(
    ("stdout", "stderr", "returncode", "message"),
    [
        ("airflow:latest\n", "", 0, f"image has no immutable digest: {CUSTOM_IMAGE}"),
        ("", "inspect failed", 1, "inspect failed"),
        ("", "", 1, f"image has no immutable digest: {CUSTOM_IMAGE}"),
    ],
)
def test_resolve_digest_rejects_missing_or_failed_digests(
    stdout: str, stderr: str, returncode: int, message: str
) -> None:
    with (
        patch(
            "conformdag.runtime.subprocess.run",
            return_value=_completed(stdout=stdout, stderr=stderr, returncode=returncode),
        ),
        pytest.raises(runtime.RuntimePhaseError, match=re.escape(message)),
    ):
        runtime.DockerRunner().resolve_digest(CUSTOM_IMAGE)


def test_resolve_digest_preserves_substring_acceptance() -> None:
    permissive = "not-a-real @sha256: short value"
    with patch(
        "conformdag.runtime.subprocess.run",
        return_value=_completed(stdout=permissive + "\n"),
    ):
        assert runtime.DockerRunner().resolve_digest(CUSTOM_IMAGE) == permissive


def test_execute_runtime_custom_image_skips_pull_and_digest_resolution(tmp_path: Path) -> None:
    runner = runtime.DockerRunner()
    observations = [
        RuntimeObservation(policy_id="B", status=FindingStatus.PASS),
        RuntimeObservation(policy_id="A", status=FindingStatus.FAIL),
    ]

    with (
        patch.object(runner, "require_daemon") as require_daemon,
        patch.object(runner, "pull_image") as pull_image,
        patch.object(runner, "resolve_digest") as resolve_digest,
        patch.object(runner, "run_manifest", return_value=observations) as run_manifest,
    ):
        resolved_observations, digest = runtime.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, image=CUSTOM_IMAGE, timeout_seconds=17),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
            runner,
        )

    require_daemon.assert_called_once_with()
    pull_image.assert_not_called()
    resolve_digest.assert_not_called()
    assert digest == CUSTOM_IMAGE
    assert [(item.policy_id, item.status.value) for item in resolved_observations] == [
        ("A", "FAIL"),
        ("B", "PASS"),
    ]
    manifest = run_manifest.call_args.args[0]
    assert manifest.image == CUSTOM_IMAGE
    assert run_manifest.call_args.args[1] == CUSTOM_IMAGE
    assert run_manifest.call_args.kwargs["timeout_seconds"] == 17


def test_execute_runtime_supported_profile_pulls_and_requires_digest_equality(tmp_path: Path) -> None:
    runner = runtime.DockerRunner()

    with (
        patch.object(runner, "require_daemon") as require_daemon,
        patch.object(runner, "pull_image") as pull_image,
        patch.object(runner, "resolve_digest", return_value=PINNED_IMAGE) as resolve_digest,
        patch.object(runner, "run_manifest", return_value=[]) as run_manifest,
    ):
        observations, digest = runtime.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(
                enabled=True,
                airflow_version=AirflowProfile.AIRFLOW_3_3_0,
                timeout_seconds=23,
            ),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
            runner,
        )

    assert observations == []
    assert digest == PINNED_IMAGE
    require_daemon.assert_called_once_with()
    pull_image.assert_called_once_with(PINNED_IMAGE, timeout_seconds=23)
    resolve_digest.assert_called_once_with(PINNED_IMAGE)
    assert run_manifest.call_args.args[1] == PINNED_IMAGE
    assert run_manifest.call_args.args[0].image == PINNED_IMAGE
    assert run_manifest.call_args.kwargs["timeout_seconds"] == 23


def test_execute_runtime_rejects_an_unreviewed_supported_profile_digest(tmp_path: Path) -> None:
    runner = runtime.DockerRunner()
    unreviewed = "ghcr.io/parthmule28/conformdag/airflow-3.3.0@sha256:" + "0" * 64

    with (
        patch.object(runner, "require_daemon"),
        patch.object(runner, "pull_image"),
        patch.object(runner, "resolve_digest", return_value=unreviewed),
        patch.object(runner, "run_manifest") as run_manifest,
        pytest.raises(runtime.RuntimePhaseError, match="reviewed runtime profile identity"),
    ):
        runtime.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
            runner,
        )

    run_manifest.assert_not_called()


def test_execute_runtime_disabled_never_invokes_docker(tmp_path: Path) -> None:
    with (
        patch("conformdag.runtime.subprocess.run") as mocked,
        pytest.raises(runtime.RuntimePhaseError, match="runtime analysis is not enabled"),
    ):
        runtime.execute_runtime(
            tmp_path,
            ProjectRuntimeConfig(enabled=False),
            ["AIR-DET-001"],
            ["dags/**/*.py"],
            [],
        )

    mocked.assert_not_called()


def test_all_checked_in_schemas_are_byte_frozen() -> None:
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(Path("schemas").glob("*.json"))
    } == SCHEMA_HASHES


def test_runtime_release_script_contract() -> None:
    positive = subprocess.run(
        [sys.executable, "scripts/verify_runtime_release.py", REVIEWED_RELEASE],
        capture_output=True,
        text=True,
        check=False,
    )
    assert positive.returncode == 0
    assert f"runtime profiles reviewed for release {REVIEWED_RELEASE}" in positive.stdout

    negative = subprocess.run(
        [sys.executable, "scripts/verify_runtime_release.py", "v9.9.9-rc.999"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert negative.returncode == 1
    assert "refusing unreviewed release v9.9.9-rc.999" in negative.stderr
    assert REVIEWED_RELEASE in negative.stderr

    missing = subprocess.run(
        [sys.executable, "scripts/verify_runtime_release.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2
    assert "usage: verify_runtime_release.py" in missing.stderr


def test_runtime_observation_status_round_trip() -> None:
    for status in FindingStatus:
        observation = RuntimeObservation(policy_id="AIR-DET-001", status=status)
        assert observation.status is status
        assert RuntimeObservation.model_validate(observation.model_dump(mode="json")) == observation
