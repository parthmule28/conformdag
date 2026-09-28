# C09 Typed Scan State and Trigger Domain

## Purpose

Give the platform one typed vocabulary for scan lifecycle states and trigger sources, and keep scan-state mutations behind explicit conditional transition primitives. Preserve the existing database and API contracts while making worker ownership attempt-fenced.

## Live-tree findings

The current platform stores scan status and trigger in SQLAlchemy `String` columns. Production logic compares raw status strings across persistence, routes, runner, worker, aggregates, and demo setup. The main branch already contains `transition_scan_to_cancelled()` and `heartbeat_running_scan()`; cancellation routes call the former, while heartbeat currently permits an omitted expected attempt. The dashboard writes trigger `dashboard`, and demo setup writes trigger `demo`.

The C09 prompt is updated to reflect these facts. C09 types and strengthens the existing ownership boundaries; it does not recreate the primitives or move runner orchestration into the application workflow.

## Domain vocabulary

Create `src/conformdag/platform/domain.py` with string enums:

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

The domain module also owns typed `ACTIVE_SCAN_STATUSES` (`QUEUED`, `RUNNING`) and `TERMINAL_SCAN_STATUSES` (`SUCCEEDED`, `FAILED`, `CANCELLED`) groups. `DEMO` is an existing persisted value. No future trigger such as MCP or schedule is added.

## State transitions and fencing

`db.py` remains the sole owner of scan-state mutations. Existing conditional updates and transaction behavior remain atomic: a successful transition commits and a lost race rolls back.

- Claiming a queued scan changes it to `RUNNING`; reclaiming a stale running scan increments its attempt, and an exhausted attempt budget marks it `FAILED`.
- `transition_running_scan()` accepts a `ScanStatus` target and only permits `RUNNING -> QUEUED` with `requeue=True`, or `RUNNING -> SUCCEEDED` / `RUNNING -> FAILED` with `requeue=False`. Incompatible target/requeue combinations raise `ValueError` before issuing SQL. `RUNNING` and `CANCELLED` are not targets of this primitive.
- `transition_scan_to_cancelled()` stays the only cancellation mutation. It conditionally changes a queued or running scan to `CANCELLED`, commits for one winner, and rolls back for a lost race. Cancellation is scan-wide and does not take a worker attempt.
- `heartbeat_running_scan(session, scan_id, attempt)` requires an attempt and refreshes `claimed_at` only when both status is `RUNNING` and the stored attempt matches exactly.
- Worker heartbeat callers require and pass the claimed attempt. A stale worker cannot refresh ownership after a reclaim. Production completion calls pass the exact expected attempt so late results cannot finish a newer attempt.
- `eligible_baseline()` accepts only a same-repository, complete `SUCCEEDED` scan.

Routes, runner, worker, aggregates, and demo setup consume the domain types; they do not directly mutate scan status outside the transition functions.

## Compatibility boundaries

- `ScanRow.status` and `ScanRow.trigger` remain `Mapped[str]` backed by SQLAlchemy `String` columns. The existing migration and string defaults do not change.
- Convert domain values with `.value` at SQL/storage boundaries and coerce persisted values to `ScanStatus` where typed business logic or response contracts require it.
- Type `ScanSummaryResponse.status` and `OverviewScan.status` as `ScanStatus`. FastAPI JSON continues to emit the same lowercase string values.
- The trigger values remain exactly `dashboard` and `demo`; no trigger field is added to an API response.
- `FindingResponse.status` and finding values such as `FAIL` and `ERROR` are a separate domain and are unchanged.
- The platform contract models are not exported by the checked-in schema generator. Do not regenerate schemas; run `mise run schema --check` to confirm no unrelated schema drift.

## Scope

Create `src/conformdag/platform/domain.py`. Modify `db.py`, `app.py`, `runner.py`, `worker.py`, `contracts.py`, `aggregates.py`, and `demo.py` to use typed values and explicit conversions. Add or extend focused tests in `tests/test_platform.py` or a dedicated platform state test module. Update the C09 prompt to match the live tree and this approved design.

No migration or ORM column conversion, persistence package split, runner-to-application delegation, new trigger source, or finding-status change is included. Runner delegation remains C10; persistence package movement remains C24.

## Verification

Tests will cover:

1. Exact enum values and active/terminal groups.
2. Valid state transitions, incompatible target/requeue pairs, and no mutation of terminal rows.
3. One-winner cancellation and rollback after a lost cancellation race.
4. Stale reclaim followed by rejection of the old attempt's heartbeat and completion.
5. Both existing triggers at the string-storage boundary and unchanged scan-status JSON serialization.
6. Baseline eligibility for only complete successful scans.

The implementation gate is focused platform state/API/worker/runner tests, a scoped audit of production scan-state/trigger literals (excluding intentional ORM/migration defaults, non-status metadata keys/labels, and unrelated finding statuses), `mise run check`, `mise run test:coverage`, `mise run schema --check`, and `git diff --check`. PostgreSQL transition tests run when configured; the dedicated Postgres suite belongs to C26. Independent review must inspect transition legality, cancellation winner semantics, heartbeat fencing, and late-result fencing.
