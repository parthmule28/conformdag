# C15 — Centralize Security Redaction

## Role and objective

You are the Build agent for C15. Establish one credential-name and credential-value redaction implementation and migrate analysis evidence, semantic context/cache, and agent verification to it without weakening trust boundaries.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C05/C10.
- Secret-like logic in `src/conformdag/analysis.py`, `src/conformdag/evaluator.py`, `src/conformdag/semantic.py`, `src/conformdag/semantic_evaluator.py`, and `src/conformdag/agent/verifier.py`.
- `src/conformdag/models.py` evidence/cache fields and all relevant tests in `tests/test_analysis.py`, `test_evaluator.py`, `test_semantic.py`, and `test_agent.py`.

## Current ownership and resulting owner

Multiple modules define secret markers and regexes. After this PR, `src/conformdag/security/redaction.py` owns `CREDENTIAL_NAME_MARKERS`, `CREDENTIAL_PATTERNS`, `credential_name_like()`, and `redact_credentials()`. Check-specific evidence may wrap it with bounded-length logic; policy-configured `SensitiveLoggingConfig.secret_patterns` remains separate policy configuration.

## Interfaces

```python
def credential_name_like(name: str) -> bool: ...
def redact_credentials(text: str) -> str: ...
def redact_evidence(text: str, max_chars: int = 240) -> str: ...
```

Redaction must cover password/passwd/token/secret/api_key/api-key/apikey/credential forms, quoted/unquoted values, colon/equal separators, benign words, and idempotence.

## Expected files

- Create: `src/conformdag/security/__init__.py`, `security/redaction.py`, and `tests/security/test_redaction.py`.
- Modify: `analysis.py` or `analysis/airflow.py` after C04, `evaluator`/checks, `semantic.py`, `semantic_evaluator.py`, `agent/verifier.py`, and existing regression tests.
- Do not move semantic package files; C22 owns that decomposition.

## Test-first sequence

1. Add central redaction tests for all marker/pattern/separator/quote/idempotence cases and prove raw values are absent from output.
2. Run the security tests and existing evidence/cache/verifier tests before migration.
3. Implement the central primitive and replace duplicate constants/functions with imports or thin wrappers.
4. Add regression tests proving semantic cache and agent evidence never retain raw credentials.
5. Run security, semantic, evaluator, analysis, agent, `mise run check`, coverage, and privacy checks.

## Allowed changes

- Central redaction module, imports, thin bounded-evidence wrappers, and regression tests.

## Non-goals and prohibitions

- Do not merge provider validation, policy secret patterns, or log filtering into one vague abstraction.
- Do not log or snapshot raw secrets in tests.
- Do not broaden semantic context or alter provider authorization.

## Verification matrix

- `tests/security/test_redaction.py` and all migrated suites.
- `mise run privacy`/artifact privacy script where present, plus `mise run check` and coverage.
- Independent privacy review of cache, evidence, logs, and agent verifier paths.

## Completion checklist and handoff

- [ ] One canonical redaction implementation exists.
- [ ] Semantic cache and agent evidence use it.
- [ ] Policy-specific secret patterns remain distinguishable.
- [ ] Commit with `fix: centralize credential redaction`; open the PR without merging.
