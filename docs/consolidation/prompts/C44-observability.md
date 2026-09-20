# C44 — Normalize Observability and Privacy Fields

## Role and objective

You are the Build agent for C44. Define consistent scan/worker/request event fields and correlation identity without logging secrets, raw source, semantic I/O, or credentials.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C10/C12/C27.
- `src/conformdag/platform/logging.py`, app middleware, worker/runner logging, application scan metadata, semantic provider/cache, and runtime code.
- Logging/privacy tests and `docs/security.md` if present.

## Current ownership and resulting owner

Logging fields vary between HTTP, worker, runner, and scan phases. After this PR, documented event vocabulary uses `event`, `scan_id`, `repository_id`, `attempt`, `status`, and `duration_ms`; HTTP keeps request IDs, while worker/runner correlate with scan ID plus attempt.

## Interfaces

Keep structured logging adapters and public report metadata separate. Define event names/field helpers only where repetition is real; do not build a tracing framework.

## Expected files

- Modify: `src/conformdag/platform/logging.py`, `app.py`/routes, `worker.py`, `runner.py`, application/runtime/semantic adapters, tests, and security docs.
- Create focused observability/privacy tests if current coverage does not assert field presence/absence.

## Test-first sequence

1. Capture current structured events and add tests for correlation fields and secret/raw-content absence.
2. Run logging, platform, semantic, runtime, and worker tests.
3. Normalize fields at explicit boundaries and document event vocabulary.
4. Run privacy/artifact checks, default gate, and relevant integration smoke.

## Allowed changes

- Event/field naming, structured logging helpers, redaction integration, tests, and docs.

## Non-goals and prohibitions

- Do not log API keys, admin tokens, DSN credentials, raw prompts/provider payloads, or source by default.
- Do not add distributed tracing or external telemetry dependencies.

## Verification matrix

- Logging/privacy tests, `mise run privacy`, default gate, platform/worker/runtime/semantic tests.

## Completion checklist and handoff

- [ ] Correlation identity is consistent.
- [ ] Sensitive fields are absent or redacted.
- [ ] Event vocabulary is documented and bounded.
- [ ] Commit with `fix: normalize platform observability`; open the PR without merging.
