# C26 — Add the Real PostgreSQL Integration Suite

## Role and objective

You are the Build agent for C26. Add a dedicated real-Postgres test job for production persistence semantics that SQLite cannot prove. Keep the default suite fast and separate from the marked integration suite.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C24–C25.
- Alembic configuration/migrations, persistence transition functions, worker/runner, Compose/CI files, and current platform fixtures.
- `tests/test_platform.py` concurrency/state/retention/migration cases.

## Current ownership and resulting owner

The default tests use SQLite for speed, while production uses PostgreSQL and `SELECT ... FOR UPDATE SKIP LOCKED`. After this PR, `tests/platform/` or a marked integration module owns real Postgres semantics and CI runs a dedicated service job.

## Interfaces

Use a `postgres` pytest marker and a test DSN supplied through environment/CI. The suite must exercise `create_session_factory()` and real Alembic migrations, not a parallel schema setup.

## Expected files

- Create/modify: `tests/platform/test_postgres.py` or the established platform test split, `tests/conftest.py` fixtures, `pyproject.toml` marker, CI workflow, and Compose/service configuration.
- Modify: no production persistence behavior unless a test proves a real defect.
- Do not make Postgres mandatory for the default local `mise run check` unless the repository already requires Docker for that command.

## Test-first sequence

1. Add marked tests for empty-DB migration, concurrent claim one-winner behavior, `SKIP LOCKED`, stale reclaim, attempt fencing, cancellation/runner races, migration lock, suppression uniqueness, retention order, baseline lookup, and JSON report round-trip.
2. Run the suite against a local Postgres service and confirm it fails when no service is present with a clear skip/error policy.
3. Add CI service setup and fixture cleanup; keep test data isolated per test.
4. Run repeated integration jobs and inspect for timing flakes.
5. Run default `mise run check` plus the dedicated Postgres job.

## Allowed changes

- Marked fixtures, CI service job, integration tests, and production fixes proven by those tests.

## Non-goals and prohibitions

- Do not replace production SQL with SQLite-compatible branches.
- Do not weaken locking or use sleeps as correctness proof.
- Do not hide failed infrastructure by marking all tests skipped.

## Verification matrix

- `pytest -m postgres` against real Postgres.
- Default suite remains green without Docker.
- Migration, concurrency, cancellation, retention, baseline, and JSON evidence.
- Independent review of one-winner and fencing assertions.

## Completion checklist and handoff

- [ ] Real Postgres tests cover production-critical semantics.
- [ ] CI service lifecycle is deterministic.
- [ ] Default local gate remains appropriately scoped.
- [ ] Commit with `test: add postgres integration coverage`; open the PR without merging.
