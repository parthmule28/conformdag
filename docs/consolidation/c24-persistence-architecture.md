# C24 — Platform persistence ownership decision

**Status:** Stage A design selected on 2026-11-09; documentation PR awaiting review. **Not implemented.**

**Canonical implementation contract:** [Issue #88](https://github.com/parthmule28/conformdag/issues/88). This decision note records architecture and alternatives; the issue owns task sequencing, test gates and OpenCode instructions.

## Entry condition

C23 was formally accepted: documentation PR #87 merged at `09be237cce57583bea80331eda81d5df34b99a50`; exact-SHA push CI [42613125669](https://github.com/parthmule28/conformdag/actions/runs/42613125669) passed all six mandatory jobs. C23 issue #85 is closed. C24 code has not begun.

## Source evidence and problem

- `src/conformdag/platform/db.py` mixes ORM table definitions, JSON/JSONB metadata, UTC/ID helpers, Alembic orchestration and locks, SQLAlchemy session factories, conditional scan state transitions, baseline selection and retention.
- `src/conformdag/platform/migrations/env.py` imports `Base` from `platform.db`, and revisions 0001–0004 supply the schema. Migrations must remain the sole schema-creation path.
- `create_session_factory(url)` is a **bind-only** factory; `initialize_session_factory(url)` executes `run_migrations(url)` before binding. The original C24 backlog sentence claiming that `create_session_factory()` runs Alembic is obsolete and is corrected in this planning PR.
- `platform/worker.py` owns commit after a successful claim, while the existing three conditional transition helpers commit on success and roll back on losing the conditional update. Moving those transactions would be a behavior change reserved for C25.
- `tests/test_platform.py::test_postgres_migration_lock_uses_database_advisory_lock` patches `platform.db.create_engine`. The extracted implementation will look up `create_engine` in its owner module; the test must intentionally patch the owner, not rely on an ineffective facade patch.

## Selected boundary (five implementation owners)

| Module | Owns | Must not own |
| --- | --- | --- |
| `platform/persistence/models.py` | `Base`, `JSONVariant`, four `*Row` classes, indexes, `utcnow`, `new_id`, `next_scan_id`, `new_suppression_id` | Session startup, SQL mutations, service orchestration |
| `platform/persistence/migrations.py` | `PlatformError`, Alembic and locks, `migration_lock_path`, `run_migrations`, `create_session_factory`, `initialize_session_factory` | ORM registry duplication, domain transitions |
| `platform/persistence/scans.py` | `stale_running_cutoff`, queued/stale claims, fenced running/cancel/heartbeat updates | Policy/report evaluation or route logic |
| `platform/persistence/baselines.py` | `eligible_baseline` | Baseline assignment API/service logic |
| `platform/persistence/retention.py` | `count_scans`, retention target selection, report-artifact pruning | Row deletion, baseline eligibility, report interpretation |

`platform/persistence/__init__.py` remains minimal; it is **not** a second registry or a second facade. `platform/db.py` remains the **only legacy compatibility facade**, with explicit imports that preserve the previously defined symbols and exact function/class object identity. It does not implement any operation. For at least this compatibility cycle, existing consumers may keep `from conformdag.platform.db import ...`. No bulk consumer import churn is required.

**Identifiers:** `new_id` and both wrappers stay together in `models.py`. `new_id()` returns a UUID4 hexadecimal string; `next_scan_id()` and `new_suppression_id()` call that helper when invoked. No sixth `identifiers.py` owner or duplicate generator.

**Dependency direction:** `platform.db → persistence.{models,migrations,scans,baselines,retention}`; `scans`, `baselines`, and `retention` may import `models` and `platform.domain`; migration env imports `persistence.models.Base`. No owner imports the facade, and no core/application code acquires a platform/SQLAlchemy dependency. Service, worker and runner layers retain their distinct existing responsibilities.

## Frozen behavior contracts

1. **ORM and Alembic:** single `Base.metadata`; same table names, columns, defaults, nullability, indexes, FK cascades, SQLite JSON/Postgres JSONB types; revisions 0001–0004 unchanged; no `create_all`, autogeneration or new migrations. Update only the Alembic env's `Base` import; resolve `alembic.ini` and `migrations/` from the unchanged platform package directory after relocating the helper.
2. **Factory and migration locking:** `create_session_factory` binds only; `initialize_session_factory` migrates once then binds; preserve SQLite file lock on the database volume, `threading.Lock`, PostgreSQL advisory lock/unlock with the same key and `NullPool`, credentials/DSN handling, startup vs runner ownership, and failure behavior.
3. **State/fencing:** preserve `FOR UPDATE SKIP LOCKED`, queued/stale reclaim order and attempt limits; conditional UPDATE + rowcount; exact success commit/failure rollback in transitions; attempts, cancellation winner, stale-runner refusal, heartbeat, timestamps, retry and error strings. No transaction ownership redesign.
4. **Baseline/retention:** a baseline must belong to the same repo, succeed and be complete; retention retains at least the newest artifact even for `keep=0`, preserves deterministic ties, clears only `report_json` and retains normalized findings/fingerprints.
5. **Compatibility:** same `platform.db` defined class/functions, signatures, exception type, results and import object identity; unchanged report JSON, HTTP contract, frozen C18/C19 fingerprints, wheel/sdist imports, and package metadata. Legacy serialized references via `conformdag.platform.db.*` must continue resolving to owner-defined classes.

## Explicit patch-seam decision

Existing internal tests that monkeypatch `platform.db.create_engine` for migration locking must instead patch `platform.persistence.migrations.create_engine`, because the function's global lookup moves. Keep read/import compatibility of intentional facade exports; do **not** add a dynamic dispatch layer solely to preserve this incidental test patch target. Add an exact facade alias assertion. If T0 discovers actual supported external monkeypatch integration on `platform.db.create_engine` or other incidental imports, **stop for architecture review** rather than changing observable behavior without permission.

## Alternatives evaluated

| Alternative | Trade-off | Decision |
| --- | --- | --- |
| Leave ORM and migrations in `db.py`, move only behavior | Less movement but ownership remains mixed; facade cannot become an explicit boundary | Reject |
| Add `identifiers.py` and/or a separate session owner | More granular yet adds modules and import edges for tiny functions in a movement-only slice | Reject; revisit only with evidence |
| Five cohesive owners behind `db.py` facade | Isolates distinct persistence responsibilities and matches C24 backlog; requires careful path, import and test parity | **Select** |

## Acceptance and residual risks

Use Issue #88's sequential T0–T8 RED/GREEN plan. Key gates are metadata/schema parity, empty-database Alembic upgrade and supported migration replay, import/pickle/wheel parity, SQLite transition and retention regressions, mocked advisory lock, frozen fingerprints, strict Pyright zero, >=90% coverage, security scans and six hosted CI jobs. Test results must be **measured**, never asserted in advance.

**Residual risk:** the existing SQLite suite and mocked PostgreSQL advisory-lock test do **not** prove PostgreSQL concurrent one-winner/`SKIP LOCKED` semantics. The dedicated real-Postgres suite is C26; C24 must record the coverage limitation and avoid making unverified concurrency claims. C25 owns changes to commit/rollback boundaries.

**Authority and gates:** ChatGPT owns architecture, planning, documentation and independent review. OpenCode owns implementation code and implementation-specific tests only, using a single agent and one unmerged implementation PR. The user retains merge authority. This planning document and its PR do **not** authorize C24 implementation or a merge. On completion of the implementation and separate acceptance gates, a later acceptance documentation PR may record C24 as accepted.
