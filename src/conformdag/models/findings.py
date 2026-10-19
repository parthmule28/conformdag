"""Findings model values."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveInt

from .common import Confidence, ConformModel, EnforcementType, FindingStatus, Severity
from .semantic import SemanticAuditEvidence
from .semantic import empty_audit_evidence as _empty_audit_evidence


class FindingEvidence(ConformModel):
    text: str
    start_line: PositiveInt | None = None
    end_line: PositiveInt | None = None
    code_hash: str | None = None


class FindingLocation(ConformModel):
    file: Path | None = None
    start_line: PositiveInt | None = None
    end_line: PositiveInt | None = None


class RemediationAction(StrEnum):
    ADD_KWARG = "add-kwarg"
    SET_KWARG = "set-kwarg"
    ADD_OWNER = "add-owner"
    ADD_TAGS = "add-tags"
    MOVE_STATEMENT = "move-statement"
    MANUAL = "manual"


class RemediationTarget(ConformModel):
    line: PositiveInt
    column: NonNegativeInt = 0
    enclosing: str | None = None
    node: Literal["dag-call", "task-call", "statement"] = "statement"


class RemediationPayload(ConformModel):
    fix_kind: str
    action: RemediationAction
    kwarg: str | None = None
    target: RemediationTarget | None = None
    value: str | None = None
    hint: str | None = None


class Suppression(ConformModel):
    fingerprint: str
    policy_id: str
    reason: str
    owner: str
    created_at: datetime
    expires_at: datetime


class Finding(ConformModel):
    policy_id: str
    policy_version: str
    status: FindingStatus
    severity: Severity
    enforcement: EnforcementType
    location: FindingLocation = Field(default_factory=FindingLocation)
    evidence: FindingEvidence | None = None
    explanation: str | None = None
    remediation: str | None = None
    confidence: Confidence | None = None
    fix: RemediationPayload | None = None
    audit_evidence: list[SemanticAuditEvidence] = Field(default_factory=_empty_audit_evidence)
    fingerprint: str
    blocking: bool = False
    suppressed: bool = False
    suppression: Suppression | None = None
