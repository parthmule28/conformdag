"""Explicit wire contracts for the platform's finding and scan-summary responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FindingResponse(BaseModel):
    """One normalized finding as exposed by the findings API."""

    policy_id: str
    policy_version: str
    status: str
    severity: str
    file_path: str | None
    start_line: int | None
    end_line: int | None
    fingerprint: str
    explanation: str | None
    remediation: str | None
    fix: dict[str, Any] | None
    suppressed: bool
    baseline_status: str | None


class ScanSummaryResponse(BaseModel):
    """One scan history entry plus the additive completion and gate fields."""

    scan_id: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    result_fingerprint: str | None
    complete: bool | None
    gate_passed: bool | None
