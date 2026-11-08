"""Legacy compatibility shim re-exporting the semantic evaluator owner.

The implementation lives in :mod:`conformdag.semantic.evaluator`. This module
preserves the historical ``conformdag.semantic_evaluator`` import path and its
implicit wildcard bindings; do not add evaluator logic here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from conformdag.models import (
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    Policy,
    SemanticAuditEvidence,
    SemanticRequest,
    SemanticResponse,
)
from conformdag.policy import policy_contract_hash, policy_enforcement_hash
from conformdag.security.redaction import redact_credentials, redact_evidence
from conformdag.semantic.context import SemanticContext, redact_text
from conformdag.semantic.evaluator import (
    POLICY_INSTRUCTIONS,
    SemanticEvaluationResult,
    SemanticProvider,
    build_semantic_request,
    evaluate_semantic_policies,
    run_semantic_evaluation,
    select_semantic_policies,
    semantic_finding,
)
from conformdag.semantic.prompts import DEFAULT_PROMPT_TEMPLATE
from conformdag.semantic.provider import SemanticProviderError

__all__ = [
    "annotations",
    "hashlib",
    "json",
    "re",
    "Sequence",
    "dataclass",
    "Path",
    "Protocol",
    "EnforcementType",
    "Finding",
    "FindingEvidence",
    "FindingLocation",
    "FindingStatus",
    "Policy",
    "SemanticAuditEvidence",
    "SemanticRequest",
    "SemanticResponse",
    "policy_contract_hash",
    "policy_enforcement_hash",
    "redact_credentials",
    "redact_evidence",
    "DEFAULT_PROMPT_TEMPLATE",
    "SemanticContext",
    "SemanticProviderError",
    "redact_text",
    "POLICY_INSTRUCTIONS",
    "SemanticProvider",
    "SemanticEvaluationResult",
    "select_semantic_policies",
    "build_semantic_request",
    "semantic_finding",
    "run_semantic_evaluation",
    "evaluate_semantic_policies",
]
