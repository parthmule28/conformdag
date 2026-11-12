# C26 — Add the Real PostgreSQL Integration Suite

**Status: Stage A architecture proposed; C26 Stage B is NOT authorized.**

**Approved design candidate:** [C26 PostgreSQL architecture](../c26-postgres-architecture.md).
**Canonical, exact PG01–PG11 acceptance and T0–T8 sequential contract:** [Issue #96](https://github.com/parthmule28/conformdag/issues/96). Issue #96 takes precedence over this backlog summary once Stage A is merged. OpenCode must not start implementation until ChatGPT completes Stage A and the user explicitly authorizes Stage B.

## Implementer scope (after authorization only)

OpenCode GPT-6.1 Sol orchestrates bounded GPT-6 Luna Max implementation/read-only review subagents; only one writer per worktree. **Implementation only:** new marked PostgreSQL tests and safe fixtures, necessary pytest/mise settings and dedicated CI service job, bounded fixes *only* for reproduced defects with a ChatGPT architecture decision. No OpenCode research, architecture, planning docs, issue/ADR updates, progress ledger, acceptance or merges. ChatGPT owns all of those.

## Required reads

- `AGENTS.md`, consolidation architecture-rules/progress, C24 and accepted C25 architecture and Issue #92.
- `src/conformdag/platform/persistence/{models,migrations,scans,baselines,retention}.py`, migrations 0001–0004, worker/runner, platform.db compatibility facade.
- `tests/platform` including C24/C25 test modules, `tests/test_platform.py`, `tests/conftest.py`, `deploy/docker-compose.yml`, `.github/workflows/ci.yml`, `mise.toml`, `pyproject.toml`.
- [C26 design](../c26-postgres-architecture.md) and [Issue #96](https://github.com/parthmule28/conformdag/issues/96) for full requirements.

## Selected design

- **PostgreSQL 17 real service**, matching existing deployment `postgres:17-alpine`, with explicit GitHub Actions service health check. No new psycopg dependency: existing `[platform]` extra already contains psycopg 3.
- Mark tests `postgres`; default `mise run check` and coverage **deselect** both `runtime` and `postgres`; new `mise run test:postgres` and **seventh mandatory CI job** execute all PostgreSQL tests. Explicit PG test command must fail clearly if DSN missing/unhealthy; no false-green skips.
- `CONFORMDAG_TEST_POSTGRES_DSN` is for a disposable, guarded test-only maintenance database; each test scenario owns a uniquely named `conformdag_c26_*` DB, created/dropped with safe quoting and no potentially destructive cleanup of unknown/shared databases. Migrate with Alembic only; `create_session_factory` is bind-only.
- Real independent PostgreSQL sessions, explicit events/handshakes and short timeout only as deadlock safety. Test actual `FOR UPDATE SKIP LOCKED`, one-winner claim, attempt fences, cancellation and runner ingestion, session-level advisory migration lock, suppressions unique constraint, baseline/retention and JSONB round-trip. Preserve C25 semantics.
- No production Compose/schema/DDL/transaction redesign absent tested defect and ChatGPT approval. C27 remains a separate milestone.

## Sequential T0–T8 (Issue #96 supplies granular assertions)

1. T0: verify exact accepted C25 main and baseline CI/local checks; no existing worktree changes.
2. T1: strict marker, fail-closed DSN, disposable per-test PostgreSQL fixtures, local `test:postgres`, default gate exclusion.
3. T2: Alembic real PostgreSQL migration/head/indexes and advisory locking (including independent sessions/processes).
4. T3: two-connection claims and `SKIP LOCKED`, stale reclaim, retry/attempt exhaustion.
5. T4: exact-attempt fencing, heartbeat and cancellation-versus-ingestion races.
6. T5: unique suppressions, baseline eligibility, deterministic retention/newest-scan-row caveat, real nested JSONB.
7. T6: only demonstrated minimal production fixes after ChatGPT architecture review, otherwise test/CI-only.
8. T7: CI PostgreSQL service job + repeat suite to detect flakes, preserve six existing mandatory jobs and runtime separation.
9. T8: full `mise run check`, coverage >=90%, strict Pyright 0, schemas, security, wheel/sdist and **seven** exact-head mandatory CI jobs; one **UNMERGED** implementation PR.

## Blocking rules

- No implementation before separately authorized Stage B.
- No silent `pytest.skip` on broken PostgreSQL service; no shared database mutation, no leaked secrets/DSN.
- No SQL compilation/mock/SQLite-only race tests as substitute for real Postgres; no `time.sleep` as correctness proof.
- No changes to `FOR UPDATE SKIP LOCKED`, transition winner logic, migration owner, C25 caller-commit boundaries, output/fingerprint/HTTP schemas or retention policy without independent design approval.
- Do not merge own PR or start C27; report reproducible implementation evidence to ChatGPT for independent review and formal Stage C acceptance.
