"""C28 T1 CLI contract captured before the module-to-package move."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import cast

import typer
from typer.core import TyperArgument, TyperCommand, TyperGroup, TyperOption
from typer.main import get_command
from typer.testing import CliRunner

from conformdag.cli import app

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "conformdag"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "cli-contract-baseline.json"
BASELINE_COMMIT = "036838b77dd0a1bec947fd8ecd7eb8906ee9f888"
BASELINE_SOURCE_SHA256 = "4f25708cc22d317b1afa50732ef5551fa6b18e35ab41bd0e4266459318c69636"
PROG_NAME = "conformdag"
HELP_WIDTH = 88
EXPECTED_CLI_MODULES = (
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

ROOT_COMMAND_ORDER = (
    "init",
    "doctor",
    "validate-policies",
    "list-policies",
    "explain",
    "scan",
    "fix",
    "version",
    "serve",
    "worker",
    "benchmark",
    "policy",
    "agent",
    "baseline",
    "pack",
)
VISIBLE_ROOT_COMMAND_ORDER = tuple(name for name in ROOT_COMMAND_ORDER if name != "explain")
SUBCOMMAND_ORDER = {
    "policy": ("show", "review", "explain", "reference", "hash", "new"),
    "agent": ("run", "policy-review"),
    "baseline": ("set",),
    "pack": ("pull",),
}

SIDE_EFFECT_GUARD_SCRIPT = """
import builtins
import importlib.abc
import importlib.util
import io
import os
import socket
import subprocess
import sys

blocked_roots = (
    "conformdag.platform", "sqlalchemy", "fastapi", "starlette",
    "uvicorn", "alembic", "psycopg",
)

def is_blocked(name):
    return any(name == root or name.startswith(root + ".") for root in blocked_roots)

class OptionalImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if is_blocked(fullname):
            raise AssertionError("optional platform import attempted: " + fullname)
        return None

sys.meta_path.insert(0, OptionalImportGuard())
original_import = builtins.__import__
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if is_blocked(name):
        raise AssertionError("optional platform import attempted: " + name)
    return original_import(name, globals, locals, fromlist, level)
builtins.__import__ = guarded_import

def blocked(operation):
    def deny(*args, **kwargs):
        raise AssertionError("unexpected side effect: " + operation)
    return deny

original_open = builtins.open
def guarded_open(file, mode="r", *args, **kwargs):
    if any(marker in mode for marker in ("w", "a", "x", "+")):
        raise AssertionError("file write attempted: open")
    return original_open(file, mode, *args, **kwargs)
builtins.open = guarded_open
original_io_open = io.open
def guarded_io_open(file, mode="r", *args, **kwargs):
    if any(marker in mode for marker in ("w", "a", "x", "+")):
        raise AssertionError("file write attempted: io.open")
    return original_io_open(file, mode, *args, **kwargs)
io.open = guarded_io_open
original_os_open = os.open
write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
def guarded_os_open(file, flags, mode=0o777, *, dir_fd=None):
    if flags & write_flags:
        raise AssertionError("file write attempted: os.open")
    return original_os_open(file, flags, mode, dir_fd=dir_fd)
os.open = guarded_os_open
for name in (
    "chmod", "chown", "ftruncate", "link", "makedirs", "mkdir", "mkfifo", "mknod",
    "remove", "rename", "replace", "rmdir", "symlink", "truncate", "unlink", "utime",
    "write", "writev",
):
    if hasattr(os, name):
        setattr(os, name, blocked("os." + name))

for name in ("run", "call", "check_call", "check_output", "Popen"):
    if hasattr(subprocess, name):
        setattr(subprocess, name, blocked("subprocess." + name))
for name in dir(os):
    if name in ("fork", "forkpty", "popen", "posix_spawn", "posix_spawnp", "startfile", "system") or name.startswith(
        ("exec", "spawn")
    ):
        setattr(os, name, blocked("os." + name))

for name in (
    "accept", "bind", "connect", "connect_ex", "listen", "recv", "recv_into",
    "recvfrom", "recvfrom_into", "send", "sendall", "sendto",
):
    setattr(socket.socket, name, blocked("socket." + name))
for name in (
    "create_connection", "getaddrinfo", "gethostbyaddr", "gethostbyname",
    "gethostbyname_ex",
):
    setattr(socket, name, blocked("socket." + name))

expected_root = os.environ.get("CONFORMDAG_EXPECTED_INSTALL_ROOT")
if expected_root:
    from pathlib import Path

    import conformdag

    expected_path = Path(expected_root).resolve()
    assert Path(sys.prefix).resolve() == expected_path
    assert Path(sys.prefix).resolve() != Path(sys.base_prefix).resolve()
    assert Path(conformdag.__file__).resolve().is_relative_to(expected_path)
    cli_spec = importlib.util.find_spec("conformdag.cli")
    assert cli_spec is not None and cli_spec.origin is not None
    assert Path(cli_spec.origin).resolve().is_relative_to(expected_path)

from typer.testing import CliRunner
from conformdag.cli import app

help_result = CliRunner().invoke(
    app,
    ["--help"],
    prog_name="conformdag",
    terminal_width=88,
    color=False,
)
if help_result.exit_code != 0:
    raise AssertionError(help_result.stderr)
sys.stdout.write(help_result.stdout)

contract_path = os.environ.get("CONFORMDAG_CONTRACT_TEST_PATH")
if contract_path:
    import runpy

    contract = runpy.run_path(contract_path)
    baseline = contract["_load_baseline"]()
    actual = contract["_capture_contract"]()
    assert actual["tree"] == baseline["tree"]
    assert actual["help"] == baseline["help"]

if expected_root:
    import importlib
    from pathlib import Path

    import conformdag.cli as cli
    from importlib.metadata import PackageNotFoundError, distribution

    for name in ("alembic", "fastapi", "psycopg", "sqlalchemy", "uvicorn"):
        try:
            distribution(name)
        except PackageNotFoundError:
            continue
        raise AssertionError("optional platform distribution installed: " + name)
    console_entry = next(
        (
            entry
            for entry in distribution("conformdag").entry_points
            if entry.group == "console_scripts" and entry.name == "conformdag"
        ),
        None,
    )
    assert console_entry is not None and console_entry.value == "conformdag.cli:app"

    package_root = Path(cli.__file__).resolve().parent
    assert Path(cli.__file__).name == "__init__.py"
    assert (package_root / "app.py").is_file()
    assert not (Path(conformdag.__file__).resolve().parent / "cli.py").exists()
    app_module = importlib.import_module("conformdag.cli.app")
    assert Path(app_module.__file__).resolve().is_relative_to(Path(expected_root).resolve())
    assert cli.app is app_module.app
    for name in ("scan", "policy"):
        module = importlib.import_module("conformdag.cli." + name)
        assert getattr(cli, name) is module

unexpected = sorted(name for name in sys.modules if is_blocked(name))
if unexpected:
    raise AssertionError("optional platform modules loaded: " + ", ".join(unexpected))
"""


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, (tuple, list)):
        items = cast(list[object] | tuple[object, ...], value)
        return [_json_value(item) for item in items]
    if isinstance(value, dict):
        entries = cast(dict[object, object], value)
        return {str(key): _json_value(item) for key, item in entries.items()}
    return str(value)


def _parameter_snapshot(parameter_value: object) -> dict[str, object]:
    parameter = cast(TyperOption | TyperArgument, parameter_value)
    metadata_names = (
        "name",
        "opts",
        "secondary_opts",
        "required",
        "default",
        "nargs",
        "multiple",
        "metavar",
        "envvar",
        "expose_value",
        "is_eager",
        "help",
        "hidden",
        "show_default",
        "show_choices",
        "show_envvar",
        "is_flag",
        "is_bool_flag",
        "count",
        "prompt",
        "confirmation_prompt",
        "prompt_required",
        "hide_input",
        "allow_from_autoenv",
        "rich_help_panel",
        "_depr_flag_value",
        "flag_value",
        "deprecated",
    )
    type_settings = cast(dict[str, object], vars(parameter.type))
    callback = getattr(parameter, "callback", None)
    custom_shell_complete = getattr(parameter, "_custom_shell_complete", None)
    return {
        "kind": "option" if isinstance(parameter, TyperOption) else "argument",
        **{name: _json_value(getattr(parameter, name, None)) for name in metadata_names},
        "callback_name": callback.__name__ if callback is not None else None,
        "custom_shell_complete_name": custom_shell_complete.__name__ if custom_shell_complete is not None else None,
        "type": {
            "class": type(parameter.type).__name__,
            "name": parameter.type.name,
            "settings": _json_value(type_settings),
        },
    }


def _command_snapshot(command_value: object, path: tuple[str, ...] = ()) -> dict[str, object]:
    command = cast(TyperCommand | TyperGroup, command_value)
    callback = command.callback
    node: dict[str, object] = {
        "path": list(path),
        "kind": "group" if isinstance(command, TyperGroup) else "command",
        "callback": callback.__name__ if callback is not None else None,
        "help": command.help,
        "short_help": command.short_help,
        "hidden": command.hidden,
        "deprecated": _json_value(command.deprecated),
        "params": [_parameter_snapshot(parameter) for parameter in command.params],
        "children": [],
    }
    if isinstance(command, TyperGroup):
        children = [
            _command_snapshot(cast(TyperCommand | TyperGroup, child), (*path, name))
            for name, child in command.commands.items()
        ]
        node["children"] = children
    return node


def _help_snapshot(command_value: object, path: tuple[str, ...] = ()) -> list[dict[str, object]]:
    command = cast(TyperCommand | TyperGroup, command_value)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [*path, "--help"],
        prog_name=PROG_NAME,
        terminal_width=HELP_WIDTH,
        color=False,
        env={"COLUMNS": str(HELP_WIDTH), "NO_COLOR": "1", "PYTHONUTF8": "1"},
    )
    assert result.exit_code == 0, result.stderr
    assert result.stderr == ""
    entries: list[dict[str, object]] = [
        {
            "path": list(path),
            "output": result.stdout.replace("\r\n", "\n").replace("\r", "\n"),
        }
    ]
    if isinstance(command, TyperGroup):
        for name, child in command.commands.items():
            entries.extend(_help_snapshot(cast(TyperCommand | TyperGroup, child), (*path, name)))
    return entries


def _capture_contract() -> dict[str, object]:
    root = cast(TyperGroup, get_command(app))
    assert isinstance(root, TyperGroup)
    return {
        "tree": _command_snapshot(root),
        "help": _help_snapshot(root),
    }


def _load_baseline() -> dict[str, object]:
    fixture = cast(dict[str, object], json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))
    baseline = cast(dict[str, object], fixture["baseline"])
    assert baseline["commit"] == BASELINE_COMMIT
    assert baseline["source_sha256"] == BASELINE_SOURCE_SHA256
    return fixture


def _assert_unique_registrations(
    typer_app: typer.Typer,
    click_group: TyperGroup,
) -> None:
    group_count = sum(isinstance(command, TyperGroup) for command in click_group.commands.values())
    command_count = len(click_group.commands) - group_count
    assert len(typer_app.registered_commands) == command_count
    assert len(typer_app.registered_groups) == group_count
    for group_info in typer_app.registered_groups:
        assert group_info.name is not None
        child = click_group.commands[group_info.name]
        assert isinstance(child, TyperGroup)
        assert group_info.typer_instance is not None
        _assert_unique_registrations(group_info.typer_instance, child)


def test_source_import_and_console_script_target_are_unchanged() -> None:
    assert isinstance(app, typer.Typer)
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'conformdag = "conformdag.cli:app"' in pyproject


def test_full_command_tree_and_parameter_metadata_match_baseline() -> None:
    fixture = _load_baseline()
    actual = _capture_contract()
    assert actual["tree"] == fixture["tree"]

    root = cast(TyperGroup, get_command(app))
    assert isinstance(root, TyperGroup)
    assert tuple(root.commands) == ROOT_COMMAND_ORDER
    assert tuple(name for name, command in root.commands.items() if not command.hidden) == VISIBLE_ROOT_COMMAND_ORDER
    assert tuple(name for name, command in root.commands.items() if isinstance(command, TyperGroup)) == tuple(
        SUBCOMMAND_ORDER
    )
    for group_name, expected_names in SUBCOMMAND_ORDER.items():
        child = root.commands[group_name]
        assert isinstance(child, TyperGroup)
        assert tuple(child.commands) == expected_names

    explain = root.commands["explain"]
    assert not isinstance(explain, TyperGroup)
    assert explain.hidden is True
    policy = root.commands["policy"]
    assert isinstance(policy, TyperGroup)
    assert policy.commands["explain"].hidden is False
    _assert_unique_registrations(app, root)


def test_snapshot_records_callback_names_without_module_paths() -> None:
    fixture = _load_baseline()
    tree = cast(dict[str, object], fixture["tree"])
    assert tree["callback"] is None
    callbacks = [node["callback"] for node in _walk_nodes(tree) if node["callback"] is not None]
    assert callbacks
    assert all(isinstance(callback, str) and "." not in callback for callback in callbacks)


def _walk_nodes(node: dict[str, object]) -> list[dict[str, object]]:
    children = cast(list[dict[str, object]], node["children"])
    return [node, *(descendant for child in children for descendant in _walk_nodes(child))]


def test_normalized_help_for_every_command_and_group_matches_baseline() -> None:
    fixture = _load_baseline()
    actual = _capture_contract()
    assert actual["help"] == fixture["help"]


def test_cli_is_one_package_with_the_canonical_app_module() -> None:
    spec = importlib.util.find_spec("conformdag.cli")
    assert spec is not None
    assert spec.origin is not None
    assert Path(spec.origin).resolve() == PACKAGE_ROOT / "cli" / "__init__.py"
    assert spec.submodule_search_locations is not None
    assert not (PACKAGE_ROOT / "cli.py").exists()
    package_root = PACKAGE_ROOT / "cli"
    assert all((package_root / name).is_file() for name in EXPECTED_CLI_MODULES)

    package = importlib.import_module("conformdag.cli")
    app_module = importlib.import_module("conformdag.cli.app")
    assert package.app is app_module.app
    assert package.app is app


def test_scan_and_policy_package_attributes_are_modules_not_callbacks() -> None:
    package = importlib.import_module("conformdag.cli")
    for name in ("scan", "policy"):
        module = importlib.import_module(f"conformdag.cli.{name}")
        assert isinstance(module, ModuleType)
        assert getattr(package, name) is module


def test_package_import_and_root_help_are_side_effect_free() -> None:
    guard_script = SIDE_EFFECT_GUARD_SCRIPT
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPO_ROOT / "src"), environment.get("PYTHONPATH", "")))
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", guard_script],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert "Usage: conformdag" in completed.stdout
