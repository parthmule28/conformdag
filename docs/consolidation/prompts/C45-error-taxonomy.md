# C45 — Establish a Useful Error Taxonomy

## Role and objective

You are the Build agent for C45. Audit existing exceptions and introduce only typed error distinctions that callers actually need, replacing message parsing at CLI, HTTP, application, and future adapter boundaries.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C11–C13/C17.
- Existing errors in policy, semantic, runtime, platform, application, fixing, agent, and CLI code; all exception translation tests.

## Current ownership and resulting owner

The codebase has useful domain errors but also uses `ValueError`, `RuntimeError`, and message text in adapter decisions. After this PR, a small `ConformDAGError` hierarchy covers configuration/application distinctions where translation requires them; existing domain-specific errors remain when they carry useful semantics.

## Interfaces

Potential base types are `ConformDAGError`, `ConfigurationError`, and `ApplicationError`; add subclasses only when a distinct caller action exists. FastAPI maps service errors to 404/409/422; CLI maps configuration/application/incomplete outcomes without message matching.

## Expected files

- Create: `src/conformdag/application/errors.py` or extend it, plus focused error tests.
- Modify: policy/semantic/runtime/platform/services/CLI/FastAPI adapters and tests.
- Do not mechanically wrap every exception or change third-party exception behavior without translation need.

## Test-first sequence

1. Inventory exception branches and add tests for each adapter mapping.
2. Run current tests and identify message-parsing decisions.
3. Introduce the smallest hierarchy and replace string parsing with typed catches.
4. Run application/HTTP/CLI/provider/runtime/agent tests and default gate.

## Allowed changes

- Error classes, boundary translations, explicit catches, and regression tests.

## Non-goals and prohibitions

- Do not use bare `except Exception`.
- Do not expose secrets in exception text or logs.
- Do not erase useful original exception causes.

## Verification matrix

- Error mapping table tests, default gate, coverage, privacy checks, and packaged HTTP/CLI smoke.

## Completion checklist and handoff

- [ ] Typed errors exist only where caller behavior differs.
- [ ] No business branch parses human error text.
- [ ] Adapter mappings remain stable.
- [ ] Commit with `refactor: clarify application error taxonomy`; open the PR without merging.
