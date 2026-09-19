# C24 — Split Platform Persistence

## Role and objective

You are the Build agent for C24. Separate ORM models/migrations, scan transitions, baselines, and retention from `platform/db.py` while preserving Alembic ownership and SQL transaction semantics.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C09/C10/C21.
- Full `src/conformdag/platform/db.py`, Alembic `migrations/env.py` and revisions, `platform/runner.py`, `worker.py`, and service modules.
- `tests/test_platform.py` migration, state, baseline, retention, and persistence cases.

## Current ownership and resulting owner

`platform/db.py` owns ORM models, session/migration setup, state transitions, baseline selection, retention, and identifiers. After this PR, `platform/persistence/models.py`, `migrations.py`, `scans.py`, `baselines.py`, and `retention.py` own those groups; `platform/db.py` re-exports for one compatibility cycle.

## Interfaces

Preserve `Base`, all `*Row` classes, `create_session_factory()`, transition functions, `eligible_baseline()`, retention helpers, and `new_id()` signatures through the facade. `create_session_factory()` continues to run Alembic and never metadata `create_all()`.

## Expected files

- Create: `src/conformdag/platform/persistence/` modules and focused persistence tests.
- Modify: `platform/db.py` facade, runner/worker/services imports, and migration tests.
- Do not change schema without a separately reviewed Alembic revision; this slice is a movement unless a proven migration bug is found.

## Test-first sequence

1. Add import-parity tests and run migration/state/baseline/retention tests against the current module.
2. Move ORM, migration, scan-transition, baseline, and retention groups one at a time.
3. Keep `db.py` re-exports and verify transaction/session factories.
4. Run SQLite persistence tests, then real Postgres migration/concurrency tests when C26 is available.
5. Run `mise run check`, coverage, and schema/package smoke.

## Allowed changes

- Cohesive persistence module movement, facade exports, imports, and tests.

## Non-goals and prohibitions

- Do not use `Base.metadata.create_all()`.
- Do not move persistence logic into application or route modules.
- Do not alter transition/fencing semantics or silently change transaction ownership.

## Verification matrix

- Existing migration/state/baseline/retention suites.
- Alembic upgrade-from-empty and downgrade/upgrade compatibility where supported.
- `mise run check`, coverage, and Postgres gate.
- Independent review must verify that ORM, migration, scan-transition, baseline, and retention ownership is separated without changing transaction or Alembic semantics.

## Completion checklist and handoff

- [ ] ORM/migration/scan/baseline/retention ownership is explicit.
- [ ] `platform.db` compatibility imports work.
- [ ] Alembic remains the sole schema creator.
- [ ] Commit with `refactor: split platform persistence`; open the PR without merging.
