"""Reject obvious secrets and raw semantic I/O in generated project artifacts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)['\"]?\s*[:=]\s*['\"]?[^<'\"\s]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}"),
)
RAW_SEMANTIC_FIELDS = ("system_prompt", "raw_prompt", "raw_response")
RAW_SEMANTIC_FIELD_PATTERN = re.compile(r"""["'](?:system_prompt|raw_prompt|raw_response)["']\s*:""")
DEFAULT_PATHS = (Path("benchmarks"), Path(".conformdag"), Path("reports"), Path("logs"))


def iter_files(paths: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(candidate for candidate in path.rglob("*") if candidate.is_file())
    return sorted(files)


def inspect_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    issues: list[str] = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if "[REDACTED]" not in match.group(0):
                line = text.count("\n", 0, match.start()) + 1
                issues.append(f"{path}:{line}: possible credential material")
    for match in RAW_SEMANTIC_FIELD_PATTERN.finditer(text):
        field = next(field for field in RAW_SEMANTIC_FIELDS if field in match.group(0))
        line = text.count("\n", 0, match.start()) + 1
        issues.append(f"{path}:{line}: raw semantic field {field!r} is persisted")
    return issues


def main() -> int:
    paths = tuple(Path(argument) for argument in sys.argv[1:]) or DEFAULT_PATHS
    issues = [issue for path in iter_files(paths) for issue in inspect_file(path)]
    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 1
    print("artifact privacy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
