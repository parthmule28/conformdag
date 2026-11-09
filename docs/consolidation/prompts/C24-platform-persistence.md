# C24 — Split Platform Persistence

**Stage A decision:** [C24 architecture](../c24-persistence-architecture.md). **Canonical implementation contract:** [Issue #88](https://github.com/parthmule28/conformdag/issues/88). Read both first. The issue holds exact T0–T8 instructions, and implementation requires user authorization.

## Role and objective

You are the Build agent for C24. Separate ORM models/migrations, scan transitions, baselines, and retention from `platform/db.py` while preserving Alembic ownership and SQL transaction semantics.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C09/C10/C21.
- Full `src/conformdag/platform/db.py`, Alembic `migrations/env.py` and revisions, `platform/runner.py`, `worker.py`, and service modules.
- `tests/test_platform.py` migration, state, baseline, retention, and persistence cases.

## Current ownership and resulting owner

`platform/db.py` owns ORM models, session/migration setup, state transitions, baseline selection, retention, and identifiers. After this PR, `platform/persistence/models.py`, `migrations.py`, `scans.py`, `baselines.py`, and `retention.py` own those groups; `platform/db.py` re-exports through at least one compatibility cycle. All three identifier helpers (`new_id`, `next_scan_id`, `new_suppression_id`) belong to `models.py`.

## Interfaces

Preserve `Base`, all `*Row` classes, `create_session_factory()`, transition functions, `eligible_baseline()`, retention helpers, and `new_id()` signatures through the facade. `create_session_factory()` is **bind-only** and does not run migrations; `initialize_session_factory()` runs Alembic first and then returns the bound factory. Schema creation remains Alembic-only; never use `Base.metadata.create_all()`.

## Expected files

- Create: `src/conformdag/platform/persistence/` modules and focused persistence tests.
- Modify: `platform/db.py` facade, Alembic env import and focused migration tests; change runner/worker/service imports only if required for proven compatibility.
- No schema revisions or behavior fixes belong in C24. Stop for a separate architecture decision if a migration bug is discovered.

## Test-first sequence

1. Add import-parity tests and run migration/state/baseline/retention tests against the current module.
2. Move ORM, migration, scan-transition, baseline, and retention groups one at a time.
3. Keep `db.py` re-exports and verify transaction/session factories.
4. Run SQLite persistence tests and the existing mocked Postgres advisory-lock regression. C26 owns the dedicated real Postgres concurrency suite; run it opportunistically if available, but never treat a mock or SQLite result as a real Postgres concurrency proof.
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
- Independent review verifies ORM, migration, scan-transition, baseline, identifier and retention ownership without changing transaction or Alembic semantics.
- Retarget the existing internal advisory-lock test patch from `platform.db.create_engine` to `platform.persistence.migrations.create_engine`, **and** the runner bind-only guard patch from `platform.db.run_migrations` to `platform.persistence.migrations.run_migrations`; retain assertions, prove both injected failures are exercised, and add facade parity assertions.
- Preserve legacy `platform.db` symbols and identity, the migration ini path after movement, wheel/sdist imports, and startup-versus-bind-only factory behavior.
- OpenCode implements code/tests only; ChatGPT owns documentation and acceptance evidence.

## Completion checklist and handoff

- [ ] ORM/migration/scan/baseline/retention ownership is explicit.
- [ ] `platform.db` compatibility imports work.
- [ ] Alembic remains the sole schema creator.
- [ ] Commit with `refactor: split platform persistence`; open the PR without merging.
