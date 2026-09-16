"""Ruff AIR adapter: compose Ruff violations into ConformDAG findings.

Ruff is invoked once per scan as a subprocess with JSON output. Violations
map into the same finding and suppression machinery as every other
deterministic check; Ruff never writes to source files.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

RUNNER_TIMEOUT_SECONDS = 120.0


def ruff_binary() -> str | None:
    """Return the resolved Ruff binary path, or None when unavailable."""
    return shutil.which("ruff")


def run_ruff(repository_root: Path, rules: list[str]) -> list[dict[str, Any]] | None:
    """Run Ruff without source fixes and return its JSON violations.

    ``None`` represents an unavailable, failed, timed-out, or malformed
    invocation so the scan can report a nonfatal structured issue.
    """
    binary = ruff_binary()
    if binary is None:
        return None
    try:
        process = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                binary,
                "check",
                "--select",
                ",".join(rules),
                "--output-format",
                "json",
                "--no-fix",
                str(repository_root),
            ],
            capture_output=True,
            text=True,
            timeout=RUNNER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode not in (0, 1):
        return None
    try:
        parsed: object = json.loads(process.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    items = cast(list[object], parsed)
    if not all(isinstance(item, dict) for item in items):
        return None
    return [cast(dict[str, Any], item) for item in items]
