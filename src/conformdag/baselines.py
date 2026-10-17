"""Canonical immutable baseline identities shared by core and adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from conformdag.models import ScanReport


@dataclass(frozen=True)
class Baseline:
    """An immutable snapshot of finding fingerprints used as a baseline."""

    fingerprints: frozenset[str]


def baseline_from_report(report: ScanReport) -> Baseline:
    """Create a baseline from every finding in a report, including suppressed findings."""
    return Baseline(frozenset(finding.fingerprint for finding in report.findings))


def baseline_from_fingerprints(fingerprints: Iterable[str]) -> Baseline:
    """Create an immutable snapshot from an iterable of existing fingerprints."""
    return Baseline(frozenset(fingerprints))
