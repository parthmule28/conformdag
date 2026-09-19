"""Ruff AIR adapter: compose Ruff violations into ConformDAG findings.

Ruff is invoked once per scan as a subprocess with JSON output. Violations
map into the same finding and suppression machinery as every other
deterministic check; Ruff never writes to source files.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

RUNNER_TIMEOUT_SECONDS = 120.0
_RUFF_SELECTOR_PATTERN = re.compile(r"^[A-Z]+(?:[0-9]{1,3})?$")
_RUFF_CODE_PATTERN = re.compile(r"^([A-Z]+)([0-9]{3})$")


def ruff_binary() -> str | None:
    """Return the resolved Ruff binary path, or None when unavailable."""
    return shutil.which("ruff")


def validate_ruff_selector(selector: str) -> str:
    """Normalize one exact, family, or bounded-prefix Ruff selector."""
    normalized = selector.strip().upper()
    if not _RUFF_SELECTOR_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid Ruff selector {selector!r}")
    return normalized


def validate_ruff_selectors(selectors: list[str]) -> list[str]:
    """Normalize a non-empty list of Ruff selectors."""
    if not selectors:
        raise ValueError("at least one Ruff selector is required")
    return [validate_ruff_selector(selector) for selector in selectors]


def ruff_rule_matches(code: str, selector: str) -> bool:
    """Return whether a Ruff code matches an exact, family, or numeric prefix.

    A selector containing three digits is exact (``AIR002``). An alphabetic
    selector selects one rule family (``AIR``), while one or two digits after
    the family select a bounded numeric prefix (``AIR0`` or ``AIR00``).
    """
    normalized_selector = validate_ruff_selector(selector)
    normalized_code = code.strip().upper()
    code_parts = _RUFF_CODE_PATTERN.fullmatch(normalized_code)
    if code_parts is None:
        return normalized_code == normalized_selector
    if normalized_selector.isalpha():
        return code_parts.group(1) == normalized_selector
    selector_parts = re.fullmatch(r"([A-Z]+)([0-9]{1,3})", normalized_selector)
    if selector_parts is None:
        return False
    family, digits = selector_parts.groups()
    if code_parts.group(1) != family:
        return False
    return len(digits) < 3 and code_parts.group(2).startswith(digits) or normalized_code == normalized_selector


def _validated_source_paths(repository_root: Path, source_files: Sequence[Path]) -> list[str] | None:
    root = repository_root.resolve()
    validated: list[str] = []
    seen: set[Path] = set()
    for source_file in source_files:
        try:
            resolved = source_file.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            return None
        if not resolved.is_file() or resolved in seen:
            if not resolved.is_file():
                return None
            continue
        seen.add(resolved)
        validated.append(str(resolved))
    return validated


def run_ruff(repository_root: Path, rules: list[str], source_files: Sequence[Path]) -> list[dict[str, Any]] | None:
    """Run Ruff without source fixes and return its JSON violations.

    ``None`` represents an unavailable, failed, timed-out, or malformed
    invocation so the scan can report a nonfatal structured issue.
    """
    binary = ruff_binary()
    if binary is None:
        return None
    normalized_rules = validate_ruff_selectors(rules)
    validated_paths = _validated_source_paths(repository_root, source_files)
    if validated_paths is None:
        return None
    if not validated_paths:
        return []
    try:
        process = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                binary,
                "check",
                "--isolated",
                "--no-respect-gitignore",
                "--no-cache",
                "--select",
                ",".join(normalized_rules),
                "--output-format",
                "json",
                "--no-fix",
                *validated_paths,
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
        parsed: object = json.loads(process.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    items = cast(list[object], parsed)
    if not all(isinstance(item, dict) for item in items):
        return None
    return [cast(dict[str, Any], item) for item in items]
