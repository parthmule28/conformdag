"""Stable public facade for canonical scan-report operations."""

from conformdag.gates import has_blocking_failures

from .html import render_html
from .normalize import normalize_report
from .sarif import render_sarif
from .suppressions import apply_suppressions

__all__ = [
    "apply_suppressions",
    "normalize_report",
    "render_sarif",
    "render_html",
    "has_blocking_failures",
]
