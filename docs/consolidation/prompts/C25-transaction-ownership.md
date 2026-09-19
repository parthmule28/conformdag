# C25 — Document and Test Transaction Ownership

## Role and objective

You are the Build agent for C25. Make transaction ownership explicit after the persistence split and prove failure atomicity for transitions, service operations, and multi-step mutations.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C24.
- `src/conformdag/platform/persistence/` or `platform/db.py`, platform services, runner, worker, and migrations; consume C09's `transition_scan_to_cancelled()` and `heartbeat_running_scan()` primitives and verify their transaction behavior against the pre-C09 inline cancellation path.
- `tests/test_platform.py` mutation/concurrency/failure cases and any Postgres fixtures.

## Current ownership and resulting owner

Some persistence primitives commit internally while route/service operations also commit. After this PR, transition primitives explicitly own atomic winner/fencing commits; application/service operations prefer caller-owned transactions for grouped changes, with documented exceptions.

## Interfaces

Document transaction behavior for `claim_queued_scan`, `transition_running_scan`, `transition_scan_to_cancelled`, `heartbeat_running_scan`, baseline selection, suppression creation, policy editing, and report ingestion. Keep signatures stable unless a new explicit transaction context is required.

## Expected files

- Modify: persistence transition/service modules, `docs/architecture.md` or `docs/consolidation/architecture-rules.md`, and focused tests.
- Create: failure-injection tests under `tests/platform/` if C33 has landed; otherwise add a focused test module beside current tests.
- Do not add a database migration for documentation-only ownership changes.

## Test-first sequence

1. Add failure-injection cases proving no partial repository/scan/suppression/policy mutation persists.
2. Add transition tests proving one-winner claim and cancellation/heartbeat fencing.
3. Run tests against current behavior and identify accidental internal commits.
4. Refine transaction boundaries and document the exception for atomic transitions.
5. Run SQLite suite, Postgres integration when available, `mise run check`, and coverage.

## Allowed changes

- Transaction boundary corrections, explicit context handling, documentation, and failure tests.

## Non-goals and prohibitions

- Do not make every function own a commit by default.
- Do not replace conditional transitions with in-memory checks.
- Do not hide rollback failures or parse error strings.

## Verification matrix

- Failure injection and state transition tests.
- Real Postgres transaction/concurrency tests.
- Default gate and coverage.

## Completion checklist and handoff

- [ ] Commit ownership is documented by operation.
- [ ] Multi-step failures leave no partial durable mutation.
- [ ] Atomic transition exceptions retain one-winner semantics.
- [ ] Commit with `fix: clarify platform transaction ownership`; open the PR without merging.
