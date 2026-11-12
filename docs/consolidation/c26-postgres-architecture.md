# C26 — Real PostgreSQL integration architecture

**Status: Stage A design proposal only. C26 Stage B implementation is NOT authorized.**

**Source-audited baseline:** `main@7072d900509851a880f96a32734c18f10d25edaa` after formally accepted C25. [Canonical issue #96](https://github.com/parthmule28/conformdag/issues/96) owns the complete PG01–PG11 acceptance matrix, sequential T0–T8 implementation contract, stop conditions and authority gates. This document records the decisions and rationale; OpenCode must not interpret the design PR as Stage B authorization.

## 1. Architecture decision

**Add a dedicated, mandatory real PostgreSQL integration job.** Match production's existing `postgres:17-alpine` service in [`deploy/docker-compose.yml`](../../deploy/docker-compose.yml); use already installed SQLAlchemy 2.x, psycopg 3 and Alembic. Keep the Python 3.12 platform and all existing six CI jobs. Add **one seventh mandatory `PostgreSQL integration` CI job**, while retaining the optional semantic smoke as opt-in.

Today the default tests use SQLite, and `tests/platform/test_persistence_contract.py` only compiles `FOR UPDATE SKIP LOCKED` for the PostgreSQL dialect. C25 added real SQLite atomicity and runner tests but explicitly did not prove PostgreSQL row locking, attempts and independent backend concurrency. This is the remaining C26 trust gap.

PostgreSQL's `SKIP LOCKED` is documented specifically as useful for queue-like tables, with the warning that it gives an inconsistent general query view. [PostgreSQL SELECT documentation](https://www.postgresql.org/docs/17/sql-select.html). GitHub Actions officially supports a health-checked PostgreSQL service container on Linux runners: [GitHub PostgreSQL service tutorial](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).

## 2. Ownership and dependencies

| Layer | Owns in C26 | Avoid |
| --- | --- | --- |
| `tests/platform/test_postgres.py` | Real PostgreSQL assertions: migration, claim contention, fencing, cancellation, baseline, uniqueness, retention, JSONB | Replacement scan transition implementation; ORM duplication |
| `tests/platform/conftest.py` (or equivalent focused fixture module) | DSN validation, **disposable DB** per test, independent Sessions/backends, cleanup and explicit readiness failure | Broad `pytest.skip` for broken CI or permission failures |
| `pyproject.toml` | Strict `postgres` marker | Changing the default pytest configuration to require PostgreSQL |
| `mise.toml` | `test:postgres` (explicit) and `not runtime and not postgres` in normal local test and coverage tasks | Making `mise run check` depend on Docker |
| `.github/workflows/ci.yml` | Dedicated Ubuntu job with a PostgreSQL 17 service, health checks and explicit DSN, always required | Weakening the six existing gates; treating Postgres check as opt-in |
| `src/conformdag/platform/persistence/*` | **Unchanged unless a demonstrated real-Postgres defect needs an approved minimal fix** | New schema/migrations, different state machine, another Base, service-commit default |

**No additional runtime dependency is selected.** `psycopg[binary]` is already in the `[platform]` extra; use the existing SQLAlchemy engine and Alembic entry points. Do not alter production Compose services to provide test dependencies unless a concrete incompatibility is demonstrated.

## 3. Execution profiles

| Profile | Command/behavior | PostgreSQL requirement |
| --- | --- | --- |
| Default developer gate | `mise run check` → pytest `-m 'not runtime and not postgres'` | None, remains offline/local |
| Default coverage | `mise run test:coverage` → same exclusion + >=90% | None |
| Airflow runtime | `mise run test:runtime` → `pytest -m runtime` | Existing Docker/Airflow requirements only |
| PostgreSQL integration | `mise run test:postgres` → `pytest -m postgres` | **Required and live**; missing/unsafe/unavailable DSN must fail visibly |
| CI | Existing six mandatory jobs **plus** always-on PostgreSQL job | Ephemeral PostgreSQL 17 service on Linux runner; every mandatory job must pass on reviewed SHA |

Register `postgres` under pytest strict markers. Use `CONFORMDAG_TEST_POSTGRES_DSN` as a **dedicated test-maintenance connection**, distinct from `CONFORMDAG_PLATFORM_DSN` and production credentials. Exact DSN documentation must redact password and host details in logs. Explicitly missing DSN must fail targeted command instead of turning a hard requirement into a silent skip. Default check deselects the marker, so a developer without Docker remains supported.

## 4. Isolation and cleanup decision

Prefer a **fresh uniquely named database** per independent test scenario (`conformdag_c26_<random-id>`) created through a dedicated admin/maintenance connection with `CREATEDB`; migrations operate only inside that disposable database. DDL for creating/dropping databases uses properly quoted SQL identifiers, not interpolated user-controlled names. Require an explicit local/CI disposable PostgreSQL host (loopback or validated dedicated service), never a remote or shared production host.

Cleanup disposes engines, ends worker threads/connections, and removes only database names that the current fixture actually created and whose prefix validates. Cleanup errors must **fail** rather than be hidden; do not force-delete unknown databases. Never drop or alter the DSN's own maintenance database, and never call `Base.metadata.create_all`. PostgreSQL migrations must be applied by `initialize_session_factory` / `run_migrations` using the same revisions 0001–0004 and single `Base` as production.

A transaction rollback per test is **not enough** to isolate migration and lock tests, because lock lifetime, concurrent connections, migration DDL and committed claims cross transaction/session boundaries. Unique test databases avoid cross-test contamination and make each scenario independently repeatable.

## 5. Deterministic concurrency contract

The suite must exercise actual **two or more independent PostgreSQL backends** and the production operations. Synchronize with explicit `threading.Event`, `Barrier` or process handshakes: hold a row lock in transaction A, signal acquisition, invoke consumer B, assert B's result while A's transaction remains open, then release A. Use narrowly bounded `statement_timeout`/lock timeouts only to fail safely if a test deadlocks; elapsed wall time is **never** proof of `SKIP LOCKED` or one-winner behavior.

**Claim tests:** exactly one queued eligible row means at most one claimant; with two queued rows, a locked oldest one must not block another claimant's progress to the second row. Abandoned-running selection occurs **before** queued selection and has no explicit internal ordering; do not accidentally codify an invented abandoned ordering. Worker owns claim commit even when exhausted attempt budget causes `claim_queued_scan` to return `None`.

**Fencing tests:** conditional `UPDATE` must respect status and expected attempt. A winning cancellation must block a stale runner from persisting new report, fingerprint or findings; a newer claim must fence old heartbeat/completion. Assert final durable state through an **independent reader**. The three approved transition helpers own commit-on-win / rollback-on-loss for their entire session; do not move the commit outside without ChatGPT review.

**Advisory migration lock:** `persistence.migrations._migration_lock(url)` uses `pg_advisory_lock(hashtext(:lock_key))` on a `NullPool`-managed connection; unlike row locks, PostgreSQL session-level advisory locks persist across transaction rollback until explicitly released or session ends. An independent connection's `pg_try_advisory_lock` must report failure while held, then succeed after normal and exceptional release. For two simultaneous first boots, use separate processes or genuinely independent backend sessions; the module's in-process `_MIGRATION_THREAD_LOCK` alone is not PostgreSQL evidence. [PostgreSQL explicit locking](https://www.postgresql.org/docs/17/explicit-locking.html).

## 6. Functional evidence and frozen invariants

Use the detailed [PG01–PG11 matrix in Issue #96](https://github.com/parthmule28/conformdag/issues/96) to cover: Alembic empty DB and 0003→head; advisory lock; one-winner claim; `SKIP LOCKED`; stale attempt reclaim and budget; exact-attempt heartbeat; cancellation/runner report-atomicity race; suppression uniqueness; baseline eligibility; retention deterministic ordering with newest **scan row** protection; nested real JSONB report/fix values; cleanup and repeated test execution.

Preserve C25's caller-owned services, conditional-transition ownership and `runner._ingest`'s same-session report/finding+status commit. `create_session_factory` is **bind-only**, `initialize_session_factory` runs Alembic. JSONB must be used through existing `JSONVariant`; no changed report JSON/fingerprint semantics. Preserve `platform.db` facade, four Alembic revisions, API response shapes, schema checks, offline-default behavior, and normalized findings after retention pruning.

**Known limits remain:** C26 proves bounded PostgreSQL integration behavior, **not** throughput, production high availability or distributed lease correctness beyond asserted races. Retention preserves newest *scan row* (which may contain no report). Policy pack YAML filesystem edits and SQL mutations are **not** jointly ACID. If a failing Postgres test reveals a production defect, OpenCode reports a minimal reproduction and proposed fix for ChatGPT architecture review before changing production behavior.

## 7. Alternatives rejected

| Alternative | Reason |
| --- | --- |
| Retain SQLite + SQL string compilation only | Cannot prove PostgreSQL row locks, advisory locks, JSONB or concurrent sessions |
| Use mocks for `SKIP LOCKED` | Artificial outcomes can pass without executing real PostgreSQL row locking |
| Add Postgres to every local test | Breaks fast offline default and macOS/developer parity |
| Reuse shared test tables in production database | Unsafe mutations/cleanup and unpredictable concurrent-suite interference |
| Reimplement state transitions for Postgres tests | Tests a second code path, not the production behavior |
| Alter production Docker Compose just for CI | Unnecessary; independent GitHub Actions service can mirror PostgreSQL 17 without affecting deploy |

## 8. Stages and authority

**Stage A:** ChatGPT owns this decision, [Issue #96](https://github.com/parthmule28/conformdag/issues/96), linked backlog prompt and documentation-only PR. Independent review, explicit user permission to merge Stage A, and all **currently six** required exact-merge-SHA main CI jobs must pass **before Stage B may be authorized**.

**Stage B:** only after separate explicit user authorization, OpenCode's GPT-6.1 Sol orchestrates bounded GPT-6 Luna Max implementation and read-only review subagents with **one active writer per worktree**. T0–T8 sequential evidence and one **unmerged** implementation PR. After the new job lands, **seven** mandatory CI jobs must pass on PR head and after an individually user-authorized merge.

**Stage C:** ChatGPT independently reviews implementation, writes acceptance and progress documentation, obtains separate Stage C docs-PR merge authorization, confirms seven green exact-SHA post-merge main CI jobs, then closes Issue #96. C27 is not automatically authorized. OpenCode does not own research, architecture, planning docs, acceptance, progress ledger or any merge.
