"""Policy-pack helpers and compatibility facade.

This facade preserves established ``conformdag.policy`` imports (introduced
in C16). Reevaluate removal only through the C30 compatibility audit; the
canonical implementations live in their respective policy submodules.
"""

from __future__ import annotations

from conformdag.policy.hashes import policy_contract_hash, policy_enforcement_hash
from conformdag.policy.loading import (
    PolicyValidationError,
    load_policy_pack,
    load_suppressions,
    resolve_configured_policy_pack,
    resolve_policy_pack_path,
    select_policy_pack,
)
from conformdag.policy.provenance import resolve_source_document, validate_policy_provenance
from conformdag.policy.validation import active_policies, validate_policy_pack

__all__ = [
    "PolicyValidationError",
    "active_policies",
    "load_policy_pack",
    "load_suppressions",
    "policy_contract_hash",
    "policy_enforcement_hash",
    "resolve_configured_policy_pack",
    "resolve_policy_pack_path",
    "resolve_source_document",
    "select_policy_pack",
    "validate_policy_pack",
    "validate_policy_provenance",
]
