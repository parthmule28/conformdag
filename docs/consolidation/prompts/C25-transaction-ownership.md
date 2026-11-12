# C25 — Document and Test Transaction Ownership

**Stage A source-audited design:** [C25 transaction architecture](../c25-transaction-architecture.md). **Canonical T0–T8 implementation contract:** [Issue #92](https://github.com/parthmule28/conformdag/issues/92). This backlog prompt is a summary; the exact Issue #92 plan takes precedence. Do not implement until Stage A documentation is merged/CI-green and the user separately authorizes Stage B.

## Role and objective

You are the Build agent for C25. Make transaction ownership explicit after the persistence split and prove failure atomicity for transitions, service operations, and multi-step mutations.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C24.
- `src/conformdag/platform/persistence/` or `platform/db.py`, platform services, runner, worker, and migrations; consume C09's `transition_scan_to_cancelled()` and `heartbeat_running_scan()` primitives and verify their transaction behavior against the pre-C09 inline cancellation path.
- `tests/test_platform.py` mutation/concurrency/failure cases and any Postgres fixtures.

## Current ownership and resulting owner

Some persistence primitives commit internally while route/service operations commit separately. Keep the bounded hybrid ownership: **only** `transition_running_scan`, `transition_scan_to_cancelled`, and `heartbeat_running_scan` own commit-on-win/rollback-on-loss; `claim_queued_scan` remains worker-commit-owned, as do worker retention and ordinary HTTP-service operations. Runner report/finding ingestion is committed atomically with its fenced status transition. PackService uses filesystem locks/atomic replacement and has no cross-resource DB transaction. Add deterministic failure-injection tests before any targeted changes.

## Interfaces

Document transaction behavior for `claim_queued_scan`, `transition_running_scan`, `transition_scan_to_cancelled`, `heartbeat_running_scan`, baseline selection, suppression creation, policy editing, and report ingestion. Keep signatures stable unless a new explicit transaction context is required.

## Expected files

- Modify: only the proven necessary persistence/worker/runner/service/route code and focused tests. Preserve the `platform.db` facade and unchanged five-owner topology. **ChatGPT**, not OpenCode, updates architecture and acceptance documents.
- Add focused failure-injection tests under `tests/platform/`; that test directory exists after C24.
- No new Alembic revisions, schema changes, generic UnitOfWork layer or cross-resource DB/filesystem transaction.

## Test-first sequence

1. Run T0 source and test baseline, recording caller→unit-of-work→commit/rollback ownership.
2. Add T1 caller-owned service tests with rollback after staged/flush operations and multi-repository failures.
3. Add T2/T3 one-winner transition and runner-ingestion atomicity tests, including stale/failed attempts.
4. Add T4/T5 worker claim/retention and policy-pack filesystem-boundary characterization. Preserve status/retention and file-write semantics.
5. Apply only demonstrated T6 fixes, T7 compatibility tests, then T8 full gates per Issue #92. If existing behavior already satisfies the contract, retain it; do not invent edits.

## Allowed changes

- Transaction boundary corrections, explicit context handling, documentation, and failure tests.

## Non-goals and prohibitions

- Do not make every function own a commit by default.
- Do not replace conditional transitions with in-memory checks.
- Do not hide rollback failures or parse error strings.
- Do not change the existing retention newest-*scan-row* policy, public API, migration/ORM structure, or scan attempts/fencing to make a transaction test pass.
- Do not claim policy YAML writes and SQL repository registration are jointly ACID.

## Verification matrix

- Failure injection and state transition tests.
- SQLite atomicity/injected failure and PostgreSQL SQL compilation/mock evidence, clearly identified. **C26** owns the mandatory real PostgreSQL CI/concurrency job; C25 may run live Postgres opportunistically when available.
- Default gate, coverage, schema, package, security and exact-head hosted CI. Explicitly verify no cross-DB/filesystem atomicity claim.

## Completion checklist and handoff

- [ ] Commit ownership is documented by operation.
- [ ] Multi-step failures leave no partial durable mutation.
- [ ] Atomic transition exceptions retain one-winner semantics.
- [ ] Commit with `fix: clarify platform transaction ownership`; open the PR without merging.
