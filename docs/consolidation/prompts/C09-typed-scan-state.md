# C09 — Typed Scan State and Trigger Domain

## Role and objective

You are the Build agent for C09. Replace ad-hoc scan status and trigger strings in production business logic with typed values and table-driven transition tests. Adopt and type the existing fenced transition primitives, require heartbeat attempt fencing, and preserve SQLAlchemy string storage plus the existing dashboard and demo trigger behavior.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, C01, and the approved C09 design spec.
- `src/conformdag/platform/db.py` current functions `claim_queued_scan`, `transition_running_scan`, `transition_scan_to_cancelled`, `heartbeat_running_scan`, and `eligible_baseline`.
- `src/conformdag/platform/app.py`, `runner.py`, `worker.py`, `aggregates.py`, `demo.py`, `contracts.py`, and migrations. Cancellation and heartbeat primitives already exist on the current base; the app calls the cancellation primitive, while raw scan-state comparisons remain in production paths. Heartbeat currently permits an omitted attempt and must be tightened.
- `tests/test_platform.py` state, cancellation, reclaim, baseline, worker, runner, and API serialization cases.

## Current ownership and resulting owner

Production code compares literals such as `"queued"`, `"running"`, and `"cancelled"` across routes, worker, runner, aggregates, demo setup, and persistence. After this PR, `src/conformdag/platform/domain.py` owns `ScanStatus`, `ScanTrigger`, and the active/terminal status groups. `db.py` remains the only owner of scan-state mutations through its fenced transition primitives; routes, worker, and runner do not mutate status directly.

## Interfaces

```python
from enum import StrEnum


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanTrigger(StrEnum):
    DASHBOARD = "dashboard"
    DEMO = "demo"
```

`DEMO` is an existing persisted trigger, not a speculative value. Do not add `MCP` or `SCHEDULE` before those features exist. Define `ACTIVE_SCAN_STATUSES` as `{ScanStatus.QUEUED, ScanStatus.RUNNING}` and `TERMINAL_SCAN_STATUSES` as `{ScanStatus.SUCCEEDED, ScanStatus.FAILED, ScanStatus.CANCELLED}` in the domain module. SQLAlchemy columns remain string-valued (`Mapped[str]`, `String`) and receive enum `.value` conversions. Response models may type scan status as `ScanStatus`; HTTP JSON must retain the same lowercase strings. Finding-status fields such as `FindingResponse.status` remain outside this domain.

The current base already has `transition_scan_to_cancelled(session, scan_id) -> bool` and `heartbeat_running_scan(...)`; adopt and type them rather than recreating them. Keep cancellation conditional on queued/running status, with one-winner atomic commit/rollback semantics. Tighten heartbeat to `heartbeat_running_scan(session, scan_id, attempt: int) -> bool` and condition it on both running status and the exact attempt. Make the worker heartbeat call chain require and pass that attempt.

Type `transition_running_scan()` with a `ScanStatus` target and enforce these outcomes: `RUNNING -> QUEUED` only when `requeue=True`, `RUNNING -> SUCCEEDED` and `RUNNING -> FAILED` only when `requeue=False`. Reject incompatible target/requeue combinations with `ValueError` before issuing SQL. `CANCELLED` remains exclusively owned by `transition_scan_to_cancelled()`; `RUNNING` is never a transition target. Existing terminal rows remain unmodifiable by the running transition predicate.

## Expected files

- Create: `src/conformdag/platform/domain.py` and focused state tests if a new test module is useful.
- Modify: `src/conformdag/platform/db.py`, `app.py`, `runner.py`, `worker.py`, `contracts.py`, `aggregates.py`, and `demo.py` to use typed comparisons and explicit value conversion at boundaries.
- Do not move persistence functions; C24 owns that package split.
- Do not modify migrations, ORM string column types/defaults, or generated schemas; the schema exporter does not include these platform contract models.

## Test-first sequence

1. Add table-driven tests for enum values/groups, valid running transitions, incompatible target/requeue pairs, terminal-state no-ops, cancellation races, stale reclaim, exact-attempt heartbeat/completion fencing, trigger persistence, and unchanged API serialization.
2. Run focused state/API/worker/runner tests and confirm the new contract tests fail against the current raw-string/optional-heartbeat implementation.
3. Add enums and convert production comparisons/mutations while preserving stored values and HTTP JSON; tighten the heartbeat call chain to require an attempt.
4. Run focused platform state/API/worker/runner tests, a scoped raw-literal audit, `mise run check`, `mise run test:coverage`, `mise run schema --check`, and `git diff --check`.

## Allowed changes

- Typed enum definitions, boundary conversions, transition tests, and literal replacement.
- Central active/terminal status groups and small validation helpers that make invalid transitions explicit.

## Non-goals and prohibitions

- Do not add future trigger values speculatively.
- Do not let routes, worker, or runner mutate status outside the existing transition primitives.
- Do not change migration storage or API spelling.
- Do not convert `FindingResponse.status` or finding statuses into scan-state values.
- Do not move runner orchestration into `application.scan`; C10 owns that change.

## Verification matrix

- Table-driven transition and serialization tests.
- Full platform/default suite.
- Coverage gate and `mise run schema --check`; platform contract models are not exported by the checked-in schema generator, so no schema regeneration is expected.
- Postgres transition tests when available; C26 owns the dedicated suite.
- Review production scan-state/trigger literals with a scoped repository search; intentional `ScanRow` string defaults and migration defaults remain compatibility strings, non-status metadata keys/labels are false positives, and finding statuses are out of scope.

## Completion checklist and handoff

- [ ] No production scan-state or trigger business logic depends on untyped spellings; only intentional storage/migration defaults retain raw values.
- [ ] Existing database rows and wire responses remain readable.
- [ ] Cancellation remains one-winner and heartbeat/completion reject stale attempts.
- [ ] `transition_running_scan()` rejects invalid target/requeue combinations before issuing SQL.
- [ ] Independent review checks the new cancellation/heartbeat transition primitives, one-winner semantics, and late-result fencing.
- [ ] Commit with `refactor: type platform scan state`; open the PR without merging.
