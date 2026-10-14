"""Canonical policy contract and enforcement hashes."""

from __future__ import annotations

import hashlib
import json

from conformdag.models import Policy


def _policy_hash(payload: object) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def policy_contract_hash(policy: Policy) -> str:
    """Hash the policy contract independently from its enforcement machinery."""
    return _policy_hash(
        {
            "id": policy.id,
            "title": policy.title,
            "severity": policy.severity.value,
            "scope": policy.scope.model_dump(mode="json"),
            "invariant": policy.invariant,
            "safe_path": policy.safe_path,
            "exceptions": policy.exceptions.model_dump(mode="json"),
            "configuration": policy.configuration.model_dump(mode="json"),
        }
    )


def policy_enforcement_hash(policy: Policy) -> str:
    """Hash the enforcement contract used to execute or prompt a policy."""
    return _policy_hash(policy.enforcement.model_dump(mode="json"))
