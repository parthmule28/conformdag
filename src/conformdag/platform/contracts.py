"""Explicit wire contracts for the platform's finding, policy, and aggregate responses."""

from __future__ import annotations

from datetime import date, datetime
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
    artifact_available: bool


class TrendPoint(BaseModel):
    """One UTC-day trend bucket derived only from completed scans."""

    date: date
    completed_scan_count: int
    fail_finding_count: int
    error_finding_count: int
    suppressed_finding_count: int
    new_finding_count: int


class OverviewScan(BaseModel):
    """One recent scan summary on the overview surface."""

    scan_id: str
    repository_id: str
    repository_name: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    complete: bool | None
    gate_passed: bool | None


class OverviewResponse(BaseModel):
    """Read-only overview aggregates across registered repositories."""

    repository_count: int
    completed_scan_count: int
    active_scan_count: int
    current_failure_count: int
    current_error_count: int
    current_new_finding_count: int
    trends: list[TrendPoint]
    recent_scans: list[OverviewScan]


class RepositoryTrendsResponse(BaseModel):
    """Read-only daily trend points for one repository."""

    repository_id: str
    points: list[TrendPoint]


class PolicyVocabularyRequest(BaseModel):
    """Additive canonical vocabulary accepted by policy mutation requests."""

    deterministic_checks: list[str] | None = None
    configuration: dict[str, Any] | None = None


class PolicyVocabularyResponse(BaseModel):
    """Canonical policy vocabulary plus the beta compatibility projection."""

    deterministic_checks: list[str]
    configuration: dict[str, Any]
    check_kind: str
    check_config: dict[str, Any]


class GateUpsertRequest(BaseModel):
    """Payload for creating or replacing one quality gate in a pack."""

    rules: list[dict[str, Any]]


class GateResponse(BaseModel):
    """One quality gate as exposed by the gates API."""

    id: str
    rules: list[dict[str, Any]]
