"""Wheel and sdist installation contracts for the ConformDAG CLI package."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_TEST_PATH = Path(__file__).resolve().with_name("test_cli_contract.py")
BASELINE_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "cli-contract-baseline.json"
CLI_MODULE_FILES = (
    "__init__.py",
    "app.py",
    "common.py",
    "scan.py",
    "fix.py",
    "policy.py",
    "pack.py",
    "agent.py",
    "platform.py",
    "benchmark.py",
    "utility.py",
)
PLATFORM_PACKAGES = ("alembic", "fastapi", "psycopg", "sqlalchemy", "uvicorn")


@dataclass(frozen=True)
class DistributionArtifacts:
    wheel: Path
    sdist: Path


def _child_environment() -> dict[str, str]:
    excluded = {
        "COVERAGE_PROCESS_START",
        "PYTHONHOME",
        "PYTHONPATH",
        "UV_PROJECT_ENVIRONMENT",
        "VIRTUAL_ENV",
    }
    return {key: value for key, value in os.environ.items() if not key.startswith("COV_CORE_") and key not in excluded}


def _artifact_path(artifacts: DistributionArtifacts, kind: str) -> Path:
    if kind == "wheel":
        return artifacts.wheel
    if kind == "sdist":
        return artifacts.sdist
    raise ValueError(f"unsupported distribution kind: {kind}")


def _baseline_help() -> dict[tuple[str, ...], str]:
    fixture = cast(dict[str, object], json.loads(BASELINE_FIXTURE_PATH.read_text(encoding="utf-8")))
    entries = cast(list[dict[str, object]], fixture["help"])
    return {tuple(cast(list[str], entry["path"])): cast(str, entry["output"]) for entry in entries}


def _run_console(
    executable: Path,
    arguments: tuple[str, ...],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(name="distribution_artifacts", scope="module")
def distribution_artifacts_fixture(tmp_path_factory: pytest.TempPathFactory) -> DistributionArtifacts:
    dist_dir = tmp_path_factory.mktemp("c28-cli-dist")
    build = subprocess.run(
        ["uv", "build", "--offline", "--sdist", "--wheel", "--out-dir", str(dist_dir)],
        cwd=REPO_ROOT,
        env=_child_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheels = list(dist_dir.glob("conformdag-*.whl"))
    sdists = list(dist_dir.glob("conformdag-*.tar.gz"))
    assert len(wheels) == 1
    assert len(sdists) == 1
    return DistributionArtifacts(wheel=wheels[0], sdist=sdists[0])


@pytest.mark.parametrize("kind", ("wheel", "sdist"), ids=("wheel", "sdist"))
def test_distributions_contain_only_the_cli_package_layout(
    distribution_artifacts: DistributionArtifacts,
    kind: str,
) -> None:
    expected_files = {f"conformdag/cli/{name}" for name in CLI_MODULE_FILES}
    artifact = _artifact_path(distribution_artifacts, kind)
    if kind == "wheel":
        with zipfile.ZipFile(artifact) as archive:
            members = set(archive.namelist())
        missing = sorted(expected_files - members)
        old_module_present = "conformdag/cli.py" in members
    else:
        with tarfile.open(artifact, "r:gz") as archive:
            members = {member.name for member in archive.getmembers()}
        missing = sorted(
            expected
            for expected in expected_files
            if not any(member.endswith("/src/" + expected) for member in members)
        )
        old_module_present = any(member.endswith("/src/conformdag/cli.py") for member in members)

    problems: list[str] = []
    if missing:
        problems.append("missing CLI package members: " + ", ".join(missing))
    if old_module_present:
        problems.append("the competing conformdag/cli.py module is still packaged")
    assert not problems, "; ".join(problems)


@pytest.mark.parametrize("kind", ("wheel", "sdist"), ids=("wheel", "sdist"))
def test_isolated_install_exposes_the_cli_contract_and_console_script(
    distribution_artifacts: DistributionArtifacts,
    tmp_path: Path,
    kind: str,
) -> None:
    assert not tmp_path.resolve().is_relative_to(REPO_ROOT)
    artifact = _artifact_path(distribution_artifacts, kind)
    environment = _child_environment()
    venv_dir = tmp_path / f"isolated-{kind}"

    create_venv = subprocess.run(
        ["uv", "venv", "--offline", "--python", sys.executable, str(venv_dir)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert create_venv.returncode == 0, create_venv.stdout + create_venv.stderr
    pyvenv_config = (venv_dir / "pyvenv.cfg").read_text(encoding="utf-8").lower()
    assert "include-system-site-packages = false" in pyvenv_config

    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    sync_environment = environment.copy()
    sync_environment["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    sync = subprocess.run(
        [
            "uv",
            "sync",
            "--offline",
            "--locked",
            "--project",
            str(REPO_ROOT),
            "--python",
            sys.executable,
            "--no-install-project",
            "--no-install-workspace",
            "--no-dev",
        ],
        cwd=tmp_path,
        env=sync_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sync.returncode == 0, sync.stdout + sync.stderr
    install = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "--no-deps",
            str(artifact),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    scripts_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    console_script = scripts_dir / ("conformdag.exe" if os.name == "nt" else "conformdag")
    assert console_script.is_file()
    console_environment = environment.copy()
    console_environment.update(
        {
            "COLUMNS": "88",
            "NO_COLOR": "1",
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TERM": "dumb",
        }
    )

    expected_help = _baseline_help()
    help_routes = ((), ("policy",), ("agent",), ("baseline",), ("pack",))
    for route in help_routes:
        result = _run_console(
            console_script,
            (*route, "--help"),
            cwd=tmp_path,
            environment=console_environment,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stderr == ""
        assert result.stdout.replace("\r\n", "\n").replace("\r", "\n") == expected_help[route]

    project = cast(dict[str, object], tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")))
    project_metadata = cast(dict[str, object], project["project"])
    expected_version = cast(str, project_metadata["version"])
    version = _run_console(console_script, ("version",), cwd=tmp_path, environment=console_environment)
    assert version.returncode == 0, version.stdout + version.stderr
    assert version.stdout == expected_version + "\n"
    assert version.stderr == ""

    reference = _run_console(
        console_script,
        ("policy", "reference", "outcomes", "--format", "json"),
        cwd=tmp_path,
        environment=console_environment,
    )
    assert reference.returncode == 0, reference.stdout + reference.stderr
    assert reference.stderr == ""
    reference_payload = json.loads(reference.stdout)
    assert isinstance(reference_payload, dict) and "outcomes" in reference_payload

    contract_helpers = runpy.run_path(str(CONTRACT_TEST_PATH))
    guard_script = cast(str, contract_helpers["SIDE_EFFECT_GUARD_SCRIPT"])
    guarded_environment = console_environment.copy()
    guarded_environment["CONFORMDAG_EXPECTED_INSTALL_ROOT"] = str(venv_dir)
    guarded_environment["CONFORMDAG_CONTRACT_TEST_PATH"] = str(CONTRACT_TEST_PATH)
    guarded = subprocess.run(
        [str(python), "-I", "-B", "-c", guard_script],
        cwd=tmp_path,
        env=guarded_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert guarded.returncode == 0, guarded.stdout + guarded.stderr
    assert guarded.stderr == ""
    assert "Usage: conformdag" in guarded.stdout
