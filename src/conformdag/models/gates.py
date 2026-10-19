"""Declarative quality-gate model values."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt

from .common import ConformModel, Severity


class NoNewFindingsRule(ConformModel):
    """Rule: no failing findings that are absent from the baseline scan."""

    type: Literal["no-new-findings"] = "no-new-findings"


class MaxSeverityRule(ConformModel):
    """Rule: no failing findings at or above the given severity."""

    type: Literal["max-severity"] = "max-severity"
    severity: Severity


class MaxFindingsRule(ConformModel):
    """Rule: fewer than ``count`` failing findings (a report with none always passes)."""

    type: Literal["max-findings"] = "max-findings"
    count: NonNegativeInt


class AlwaysBlockRule(ConformModel):
    """Rule: the listed policy ids always block, even when otherwise gated out."""

    type: Literal["always-block"] = "always-block"
    policy_ids: list[str] = Field(min_length=1)


class FailureRateRule(ConformModel):
    """Rule: failing findings below ``max_percent`` percent of all findings."""

    type: Literal["failure-rate"] = "failure-rate"
    max_percent: float = Field(ge=0.0, le=100.0)


GateRule = Annotated[
    NoNewFindingsRule | MaxSeverityRule | MaxFindingsRule | AlwaysBlockRule | FailureRateRule,
    Field(discriminator="type"),
]


class QualityGate(ConformModel):
    """One org-defined pass/fail decision over a scan's findings."""

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    rules: list[GateRule] = Field(min_length=1)


class GateRuleResult(ConformModel):
    """The outcome of one rule during gate evaluation."""

    rule_type: str
    passed: bool
    detail: str
    matching_findings: NonNegativeInt = 0


class GateResult(ConformModel):
    """The outcome of one gate: every rule must pass for the gate to pass."""

    gate_id: str
    passed: bool
    rules: list[GateRuleResult]
