"""Structured edit specs, span application, and unified diff rendering."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff


@dataclass(frozen=True, order=True)
class EditSpan:
    """A zero-width insertion or range replacement at exact source coordinates.

    Attributes:
        start_line: 1-based start line of the edited range.
        start_col: 0-based start column of the edited range.
        end_line: 1-based end line of the edited range (exclusive when zero-width).
        end_col: 0-based end column of the edited range.
        replacement: Source text inserted over the range.
    """

    start_line: int
    start_col: int
    end_line: int
    end_col: int
    replacement: str


def _offset(lines: list[str], line: int, col: int) -> int:
    if line < 1 or line > len(lines):
        raise ValueError(f"edit span line {line} outside source")
    return sum(len(text) for text in lines[: line - 1]) + col


def apply_spans(source: str, spans: list[EditSpan]) -> str:
    """Apply non-overlapping edit spans to source, highest position first.

    Args:
        source: The complete original file content.
        spans: Structured edit specs computed against ``source`` coordinates.

    Returns:
        The new file content with every span applied.

    Raises:
        ValueError: If any span references a line outside the source or two
            spans overlap.
    """
    ordered = sorted(spans)
    for left, right in zip(ordered, ordered[1:], strict=False):
        if (right.start_line, right.start_col) < (left.end_line, left.end_col):
            raise ValueError("overlapping edit spans")
    lines = source.splitlines(keepends=True)
    result = source
    for span in reversed(ordered):
        start = _offset(lines, span.start_line, span.start_col)
        end = _offset(lines, span.end_line, span.end_col)
        result = result[:start] + span.replacement + result[end:]
    return result


def render_unified_diff(path: str, original: str, updated: str) -> str:
    """Render a deterministic unified diff for one file.

    Args:
        path: Repository-relative path used in the diff headers.
        original: The file content before the edit.
        updated: The file content after the edit.

    Returns:
        A unified diff with ``a/<path>`` and ``b/<path>`` headers.
    """
    return "".join(
        unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
