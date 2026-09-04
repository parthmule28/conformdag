"""Deterministic fix engine: codemods, verify-by-rescan, and optional apply."""

from __future__ import annotations

from conformdag.fixing.engine import (
    FilePatch,
    FixOutcome,
    NotFixable,
    ProposedMove,
    ResidualFailure,
    run_fix,
)

__all__ = [
    "FilePatch",
    "FixOutcome",
    "NotFixable",
    "ProposedMove",
    "ResidualFailure",
    "run_fix",
]
