"""Repository-relative Python source discovery and symlink policy."""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

from conformdag.analysis.models import ParseIssue, ParseIssueCode, SourceFile

DEFAULT_EXCLUDES = ("**/.venv/**", "**/.git/**", "**/vendor/**", "**/generated/**")

NON_FATAL_DISCOVERY_ISSUES = frozenset(
    {
        ParseIssueCode.SYMLINK_EXCLUDED,
        ParseIssueCode.EXTERNAL_SYMLINK_EXCLUDED,
        ParseIssueCode.BROKEN_SYMLINK_EXCLUDED,
        ParseIssueCode.SYMLINK_RESOLUTION_ERROR,
    }
)


def _normalize_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


@lru_cache(maxsize=256)
def _exclude_regex(pattern: str) -> re.Pattern[str]:
    """Compile a repository-relative glob with explicit ``**`` semantics."""
    normalized = _normalize_relative_path(pattern)
    expression: list[str] = []
    index = 0
    while index < len(normalized):
        if normalized.startswith("**/", index):
            expression.append("(?:.*/)?")
            index += 3
        elif normalized.startswith("/**", index):
            expression.append("(?:/.*)?")
            index += 3
        elif normalized.startswith("**", index):
            expression.append(".*")
            index += 2
        elif normalized[index] == "*":
            expression.append("[^/]*")
            index += 1
        elif normalized[index] == "?":
            expression.append("[^/]")
            index += 1
        else:
            expression.append(re.escape(normalized[index]))
            index += 1
    return re.compile("^" + "".join(expression) + "$")


def matches_exclude(relative_path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """Match normalized repository-relative paths with recursive glob semantics."""
    candidate = _normalize_relative_path(relative_path)
    return any(_exclude_regex(_normalize_relative_path(pattern)).fullmatch(candidate) for pattern in patterns)


def _contains_symlink(candidate: Path, root: Path) -> bool:
    try:
        relative_parts = candidate.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _append_discovery_issue(
    issues: list[ParseIssue],
    seen: set[tuple[str, ParseIssueCode]],
    path: str,
    message: str,
    code: ParseIssueCode,
) -> None:
    key = (path, code)
    if key in seen:
        return
    seen.add(key)
    issues.append(ParseIssue(path, message, code=code))


def discover_python_files(
    repository_root: Path,
    include: list[str],
    exclude: list[str] | None = None,
    follow_internal_symlinks: bool = False,
) -> tuple[list[SourceFile], list[ParseIssue]]:
    """Discover normalized Python inputs without following symlinks by default."""
    root = repository_root.resolve()
    excluded = tuple(DEFAULT_EXCLUDES) + tuple(exclude or [])
    selected: dict[str, Path] = {}
    issues: list[ParseIssue] = []
    issue_keys: set[tuple[str, ParseIssueCode]] = set()
    for pattern in include:
        for candidate in root.glob(pattern):
            try:
                relative = candidate.relative_to(root).as_posix()
            except ValueError:
                continue
            if matches_exclude(relative, excluded):
                continue
            contains_symlink = _contains_symlink(candidate, root)
            try:
                resolved = candidate.resolve(strict=False)
            except (OSError, RuntimeError) as exc:
                _append_discovery_issue(
                    issues,
                    issue_keys,
                    relative,
                    f"symlink target could not be resolved: {exc}",
                    ParseIssueCode.SYMLINK_RESOLUTION_ERROR,
                )
                continue
            try:
                resolved.relative_to(root)
            except ValueError:
                if contains_symlink:
                    _append_discovery_issue(
                        issues,
                        issue_keys,
                        relative,
                        "symlink target is outside the repository root",
                        ParseIssueCode.EXTERNAL_SYMLINK_EXCLUDED,
                    )
                continue
            if contains_symlink:
                if not follow_internal_symlinks:
                    _append_discovery_issue(
                        issues,
                        issue_keys,
                        relative,
                        "symlink excluded by scan configuration",
                        ParseIssueCode.SYMLINK_EXCLUDED,
                    )
                    continue
                if not resolved.exists():
                    _append_discovery_issue(
                        issues,
                        issue_keys,
                        relative,
                        "symlink target does not exist",
                        ParseIssueCode.BROKEN_SYMLINK_EXCLUDED,
                    )
                    continue
            if not candidate.is_file():
                continue
            selected[relative] = candidate

    files: list[SourceFile] = []
    for relative, candidate in sorted(selected.items()):
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(ParseIssue(relative, f"unreadable source: {exc}", code=ParseIssueCode.READ_ERROR))
            continue
        files.append(
            SourceFile(
                path=candidate,
                relative_path=relative,
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
    return files, issues
