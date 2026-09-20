# C09 — Typed Scan State and Trigger Domain

## Role and objective

You are the Build agent for C09. Replace ad-hoc scan status and trigger strings in production business logic with typed values and table-driven transition tests, while keeping SQLAlchemy string storage and the current dashboard trigger behavior.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C01.
- `src/conformdag/platform/db.py` current functions `claim_queued_scan`, `transition_running_scan`, and `eligible_baseline`; `src/conformdag/platform/app.py:cancel_scan` currently mutates cancellation inline; `worker.py` and `runner.py` currently read cancellation directly, and no heartbeat primitive exists yet.
- `src/conformdag/platform/app.py`, `runner.py`, `worker.py`, `platform/contracts.py`, and migrations.
- `tests/test_platform.py` state, cancellation, reclaim, and baseline cases, plus the new heartbeat cases created by this slice.

## Current ownership and resulting owner

Production code compares literals such as `"queued"`, `"running"`, and `"cancelled"` across routes, worker, runner, and persistence. After this PR, `src/conformdag/platform/domain.py` owns `ScanStatus` and `ScanTrigger`; approved transition primitives remain the only state mutation owners.

## Interfaces

```python
class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanTrigger(StrEnum):
    DASHBOARD = "dashboard"
```

Do not add `MCP` or `SCHEDULE` before those features exist. SQLAlchemy columns may continue storing string values through enum `.value` conversion.

The slice must also introduce the missing fenced primitives `transition_scan_to_cancelled(session, scan_id) -> bool` and `heartbeat_running_scan(session, scan_id, attempt) -> bool`, with conditional status/attempt predicates and the same atomic transaction discipline as `transition_running_scan()`.

## Expected files

- Create: `src/conformdag/platform/domain.py` and focused state tests if a new test module is useful.
- Modify: `src/conformdag/platform/db.py`, `app.py`, `runner.py`, `worker.py`, and `contracts.py` to use typed comparisons and conversion at boundaries.
- Do not move persistence functions; C24 owns that package split.

## Test-first sequence

1. Add table-driven tests for valid transitions, invalid terminal transitions, cancellation races, stale reclaim, and trigger serialization.
2. Run focused platform state tests and confirm business logic still relies on raw strings.
3. Add enums and convert production comparisons/mutations while preserving stored values and HTTP JSON.
4. Run all platform state/API/worker/runner tests, `mise run check`, and coverage.

## Allowed changes

- Typed enum definitions, boundary conversions, transition tests, and literal replacement.
- Small helper functions that make invalid transitions explicit.

## Non-goals and prohibitions

- Do not add future trigger values speculatively.
- Do not let routes or worker mutate status outside the existing transition primitives.
- Do not change migration storage or API spelling.

## Verification matrix

- Table-driven transition and serialization tests.
- Full platform/default suite.
- Postgres transition tests when available; C26 owns the dedicated suite.
- Review all raw status comparisons with a repository search.

## Completion checklist and handoff

- [ ] No production business logic depends on untyped status spellings.
- [ ] Existing database rows and wire responses remain readable.
- [ ] Cancellation and fencing semantics remain intact.
- [ ] Independent review checks the new cancellation/heartbeat transition primitives, one-winner semantics, and late-result fencing.
- [ ] Commit with `refactor: type platform scan state`; open the PR without merging.
