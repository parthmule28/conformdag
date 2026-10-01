"""Canonical, dependency-free credential redaction primitives."""

from __future__ import annotations

import re

CREDENTIAL_NAME_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "credential",
)

CREDENTIAL_PATTERNS: tuple[str, ...] = (
    r"(?P<key_quote>['\"]?)(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)(?P=key_quote)\s*[:=]\s*"
    r"(?P<value>\[REDACTED\]|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;}\]\)]+)",
    r"(?i)(?P<prefix>\bBearer\s+)(?P<value>[A-Za-z0-9._~+/=-]+)",
    r"(?i)(?P<prefix>\b[a-z][a-z0-9+.-]*://[^:/@\s]+:)(?P<value>[^@/\s]+)(?P<suffix>@)",
)

_REDACTED = "[REDACTED]"
_ASSIGNMENT_PATTERN = re.compile(CREDENTIAL_PATTERNS[0])
_BEARER_PATTERN = re.compile(CREDENTIAL_PATTERNS[1])
_URI_AUTHORITY_PATTERN = re.compile(CREDENTIAL_PATTERNS[2])
_SIMPLE_CREDENTIAL_MARKERS = frozenset(CREDENTIAL_NAME_MARKERS) - {"api_key"}


def _identifier_components(name: str) -> list[str]:
    camel_boundaries = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    acronym_boundaries = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", camel_boundaries)
    return [component.casefold() for component in re.split(r"[^A-Za-z0-9]+", acronym_boundaries) if component]


def credential_name_like(name: str) -> bool:
    """Return whether an identifier contains a credential-holder component."""
    components = _identifier_components(name)
    if any(component in _SIMPLE_CREDENTIAL_MARKERS for component in components):
        return True
    return any(
        f"{first}_{second}" in CREDENTIAL_NAME_MARKERS
        for first, second in zip(components, components[1:], strict=False)
    )


def _replace_assignment(match: re.Match[str]) -> str:
    if not credential_name_like(match.group("name")):
        return match.group(0)

    value = match.group("value")
    quote = value[0] if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0] else ""
    unquoted_value = value[1:-1] if quote else value
    if unquoted_value == _REDACTED:
        return match.group(0)

    replacement = f"{quote}{_REDACTED}{quote}" if quote else _REDACTED
    return f"{match.group(0)[: match.start('value') - match.start()]}{replacement}"


def _replace_value(match: re.Match[str]) -> str:
    value = match.group("value")
    if value == _REDACTED:
        return match.group(0)
    return f"{match.group('prefix')}{_REDACTED}{match.groupdict().get('suffix', '')}"


def redact_credentials(text: str) -> str:
    """Redact credential values in assignment, bearer, and URI text forms."""
    redacted = _ASSIGNMENT_PATTERN.sub(_replace_assignment, text)
    redacted = _BEARER_PATTERN.sub(_replace_value, redacted)
    redacted = _URI_AUTHORITY_PATTERN.sub(_replace_value, redacted)
    return redacted


def redact_evidence(text: str, max_chars: int = 240) -> str:
    """Redact credential values before bounding evidence text."""
    return redact_credentials(text)[:max_chars]
