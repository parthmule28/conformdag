"""Deterministic, privacy-preserving semantic evidence context."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from conformdag.security.redaction import CREDENTIAL_PATTERNS, redact_credentials

DEFAULT_SECRET_PATTERNS = CREDENTIAL_PATTERNS


@dataclass(frozen=True)
class SemanticContext:
    text: str
    context_hash: str
    included_files: tuple[str, ...]
    omitted_files: tuple[str, ...]


def redact_text(text: str, patterns: Iterable[str] = DEFAULT_SECRET_PATTERNS) -> str:
    """Enforce canonical credential protection before additive caller patterns."""
    result = redact_credentials(text)
    for pattern in patterns:
        if pattern in DEFAULT_SECRET_PATTERNS:
            continue
        compiled = re.compile(pattern)
        result = compiled.sub("[REDACTED]", result)
    return result


def build_context(
    policy_text: str,
    source_slices: Mapping[str, str],
    runtime_observations: Sequence[str] = (),
    max_input_tokens: int = 32_000,
    secret_patterns: Iterable[str] = DEFAULT_SECRET_PATTERNS,
) -> SemanticContext:
    """Select deterministic, redacted evidence under an approximate token budget."""
    budget = max_input_tokens * 4
    sections = ["[POLICY]\n" + redact_text(policy_text, secret_patterns)]
    included: list[str] = []
    omitted: list[str] = []
    for path in sorted(source_slices):
        section = f"[SOURCE {path}]\n{redact_text(source_slices[path], secret_patterns)}"
        if sum(len(item) + 1 for item in sections) + len(section) <= budget:
            sections.append(section)
            included.append(path)
        else:
            omitted.append(path)
    if runtime_observations:
        runtime = "[RUNTIME]\n" + "\n".join(redact_text(item, secret_patterns) for item in runtime_observations)
        if sum(len(item) + 1 for item in sections) + len(runtime) <= budget:
            sections.append(runtime)
        else:
            omitted.append("<runtime-observations>")
    text = "\n\n".join(sections)
    return SemanticContext(
        text=text,
        context_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        included_files=tuple(included),
        omitted_files=tuple(omitted),
    )
