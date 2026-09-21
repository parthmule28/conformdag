"""Authoritative check catalogue and compatibility views."""

from conformdag.checks.registry import (
    AUTOFIX_KINDS,
    CHECK_CONFIGURATION_KINDS,
    CHECK_EVALUATORS,
    CHECK_SPECS,
    LEGACY_POLICY_CHECKS,
    LEGACY_POLICY_CONFIGURATION_KINDS,
    LEGACY_POLICY_EVALUATORS,
    MANUAL_KINDS,
    PROPOSED_ONLY_KINDS,
    CheckSpec,
    Fixability,
    check_spec,
)

__all__ = [
    "AUTOFIX_KINDS",
    "CHECK_CONFIGURATION_KINDS",
    "CHECK_EVALUATORS",
    "CHECK_SPECS",
    "LEGACY_POLICY_CHECKS",
    "LEGACY_POLICY_CONFIGURATION_KINDS",
    "LEGACY_POLICY_EVALUATORS",
    "MANUAL_KINDS",
    "PROPOSED_ONLY_KINDS",
    "CheckSpec",
    "Fixability",
    "check_spec",
]
