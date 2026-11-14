# C26 — Real PostgreSQL integration architecture

**Status: Stage A and Stage B MERGED; Stage C formal acceptance PROPOSED and conditional.** C26 is **not formally accepted** until this Stage C documentation-only PR is independently reviewed, merged with separate explicit user permission, and its own exact-merge-SHA `main` CI passes **all seven required jobs**. [Issue #96](https://github.com/parthmule28/conformdag/issues/96) remains open until those gates pass.

**Historical design baseline:** `main@7072d900509851a880f96a32734c18f10d25edaa` after accepted C25. [Issue #96](https://github.com/parthmule28/conformdag/issues/96) remains canonical for PG01–PG11 and T0–T8. The accepted Stage A architecture is retained below; Stage B implementation evidence and Stage C conditions are recorded next.


## Stage A/B implementation and independent acceptance evidence

- **Stage A:** ChatGPT-authored [design-only PR #97](https://github.com/parthmule28/conformdag/pull/97) independently reviewed at head `1bb572f1307b6cf5f2c5f52bbbf9ff7ccd56154a`, merged under explicit user authorization as `bfe21d15f89d88ea8f3f6999756f7353c260a940`. [Pre-merge CI #43284901205](https://github.com/parthmule28/conformdag/actions/runs/43284901205) and [post-merge `main` CI #43286809924](https://github.com/parthmule28/conformdag/actions/runs/43286809924) passed all **six** then-required jobs on their exact SHAs.
- **Stage B authorization:** Separately and explicitly granted by the user in [Issue #96](https://github.com/parthmule28/conformdag/issues/96); OpenCode implementation only, one unmerged PR, with ChatGPT retaining design/documentation/review/merges.
- **Stage B implementation:** [PR #98](https://github.com/parthmule28/conformdag/pull/98) added the real PostgreSQL 17 marked test suite and safety harness, CI service and offline regression guards; **seven files changed**, **no production code, migration revision, public/schema contract, dependency or planning-document changes**. PostgreSQL marker and explicit `mise run test:postgres`; local default test and coverage exclude `postgres`, preserving offline developer checks.
- **Independent review and correction:** ChatGPT reviewed initial head `bf0acb6e79462fb2207d8eeeba8338b51083c75e`; one Important credential-boundary issue CI-01 required removing `github.token` as PostgreSQL password. OpenCode corrected only CI workflow and offline regression test on the same PR. ChatGPT independently re-reviewed the final head `2ec6a46d55c632f11e134b4c28d81caeafb8e84e`, recorded [passing review #5904243101](https://github.com/parthmule28/conformdag/pull/98#pullrequestreview-5904243101), **no remaining blocking findings**. No formal GitHub `APPROVE` event was possible because the connected identity authored the PR; review is recorded as `COMMENT`.
- **Exact-head PR CI:** [Run #43592422084](https://github.com/parthmule28/conformdag/actions/runs/43592422084) completed **seven of seven mandatory jobs green**, including **20 live PostgreSQL tests twice**, zero residual owned databases/backends, hosted **1,209 passed, 2 skipped, 39 deselected**, 93.06% coverage, strict Pyright 0, build, pip-audit, Gitleaks, 19 Airflow 3.3.0 runtime tests and real Docker smoke. OpenCode separately reported local 1,211 passing tests, 93.30% coverage and two PostgreSQL passes; raw local output was not independently retrieved.
- **Authorized Stage B merge:** User explicitly authorized merging PR #98 **at exact head** `2ec6a46d55c632f11e134b4c28d81caeafb8e84e`; exact-head guarded merge created `45fb232ac6f8d668affb8b46481d7ca81ed83a77` on `main`.
- **Stage B exact-merge-SHA acceptance gate:** [Post-merge `main` run #43593019959](https://github.com/parthmule28/conformdag/actions/runs/43593019959) **passed all seven required jobs** on `45fb232ac6f8d668affb8b46481d7ca81ed83a77`. Independently inspected logs: hosted **1,209 passed, 2 skipped, 39 deselected**, **93.06% coverage**, **0 Pyright errors**, wheel/sdist built, pip-audit no known vulnerabilities, Gitleaks no leaks; PostgreSQL **20 live tests passed twice** with **zero residual test databases or matching backends**; Airflow 3.3.0 **19 tests and actual Docker smoke passed**. Optional semantic-provider smoke skipped as configured.
- **Remaining limits:** These are bounded PostgreSQL 17 integration/locking checks, not performance/load/HA proof. Cleanup protections rely on guarded localhost ephemeral CI/test service and ownership checks; local Docker is not part of the ordinary `mise run check`. Existing C25 semantic caveats remain: newest **scan row** protection may retain a null artifact, and policy YAML filesystem writes are not jointly ACID with SQL.
## 1. Architecture decision

**Add a dedicated, mandatory real PostgreSQL integration job.** Match production's existing `postgres:17-alpine` service in [`deploy/docker-compose.yml`](../../deploy/docker-compose.yml); use already installed SQLAlchemy 2.x, psycopg 3 and Alembic. Keep the Python 3.12 platform and all existing six CI jobs. Add **one seventh mandatory `PostgreSQL integration` CI job**, while retaining the optional semantic smoke as opt-in.

Before C26, default tests used SQLite and `tests/platform/test_persistence_contract.py` compiled `FOR UPDATE SKIP LOCKED` without live PostgreSQL concurrency evidence. C25 added SQLite atomicity/runner tests but not independent PostgreSQL backends. C26 addresses that specific evidence gap with a dedicated real PostgreSQL 17 suite; it does not replace fast SQLite tests.

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

**Stage A complete:** ChatGPT-authored architecture [PR #97](https://github.com/parthmule28/conformdag/pull/97) independently reviewed, merged with explicit user permission and six green exact-merge-SHA `main` jobs (evidence above).

**Stage B complete:** Following separate user authorization, OpenCode's GPT-6.1 Sol and bounded GPT-6 Luna Max implementation/review subagents produced implementation PR #98, independently reviewed by ChatGPT and merged only after exact-head user authorization. All **seven** mandatory jobs passed on both PR head and exact Stage B merge SHA (evidence above).

**Stage C formal acceptance gate (pending):** ChatGPT writes and independently reviews this documentation-only acceptance PR. The user must **separately authorize merging that exact docs-PR head**; **seven** exact-docs-merge-SHA `main` jobs must then pass before Issue #96 can be closed and C26 formally accepted. The implementation PR #98 merge **does not authorize this docs merge**. C27 remains unauthorized. OpenCode does not own research, architecture, planning docs, acceptance, progress ledger or any merge.
