# C27 — Clean Worker and Runner Responsibilities

**Status: Stage A DESIGN PROPOSED; Stage B implementation NOT AUTHORIZED.** This is the historical backlog handoff summary. [C27 architecture](../c27-worker-runner-architecture.md) records the ChatGPT-owned decision and rationale; [canonical Issue #100](https://github.com/parthmule28/conformdag/issues/100) owns the exact **WR01–WR12** acceptance matrix, **T0–T8** implementation sequencing, evidence and authority gates. A Stage A PR merge does not authorize OpenCode implementation.

## Objective and existing state

Establish independently testable ownership: **worker owns process lifecycle**, **runner owns one claimed scan's application invocation, canonical ingestion and fenced completion**, and persistence **owns SQL state transitions**. Current source is already substantially aligned after C10/C24–C26. Avoid an artificial rewrite; close the actual lifecycle-test and attempt-correlation gaps with minimal behavior-preserving changes.

## Required reads

- `AGENTS.md`, consolidation architecture rules and progress ledger, C10 and accepted C24–C26 architecture, C27 architecture and Issue #100.
- `src/conformdag/platform/{worker,runner,logging,domain}.py`, `platform/persistence/{scans,models,retention}.py`, `platform/db.py`, application scan/configuration and platform API service call sites.
- `tests/test_platform.py` worker/runner lifecycle and report-parity cases, `tests/platform/test_{worker,runner,transition}_transactions.py`, `tests/platform/test_postgres.py`, `tests/platform/test_postgres_harness.py`, real Docker/Airflow runtime checks.

## Ownership and interface decisions

| Owner | Owns | Must not own |
| --- | --- | --- |
| Worker | Claim (caller commit), subprocess fixed argv/env, bounded polling and heartbeat, cancellation/termination, retries and attempt budget, graceful drain, retention trigger, redacted child stderr | Application scan/evaluator/gate/report construction or duplicate SQL transition rules |
| Runner | Validate current claimed scan + optional attempt, application workflow parameters (profile/baseline/suppressions/cache), `ScanReport`/findings ingestion, fenced terminal completion, existing `python -m` entry point | Subprocess launch/polling/heartbeat/retry and retention |
| Persistence | `FOR UPDATE SKIP LOCKED`, attempt-fenced heartbeat and state changes, winning whole-session commit/losing rollback, artifact pruning queries | Scan evaluation or OS process supervision |

Preserve `WorkerSettings`, worker-side `RunnerOutcome`, `run_worker_once`, `execute_claimed_scan`, `runner.execute_scan(scan_id, dsn, claim_attempt=None)`, runner `--scan-id`/`--claim-attempt` command, `CONFORMDAG_PLATFORM_DSN` child environment and observed integer exit mappings. Maintain C10 application report/fingerprint parity. **Do not introduce new interprocess protocol, new evaluation engine, new ORM owner or new runtime dependency.**

**Concrete C27 change:** worker and runner lifecycle JSON events (`scan_claimed`, `scan_finished`, `scan_started`, `scan_completed`) consistently include `scan_id` and numeric `attempt`; redaction remains canonical for stderr/errors/extra fields. Add focused deterministic lifecycle and security regression tests rather than duplicating existing C25/C26 cases. A narrowly tested helper extraction is allowed; behavior changes require ChatGPT architecture disposition.

## Implementation T0–T8, only after separately authorized Stage B

1. **T0:** confirm the exact accepted Stage A merge SHA and seven-job `main` CI, clean worktree, baseline worker/runner interfaces, monkeypatch seams, tested C25/C26 invariants.
2. **T1:** test-first missing WR01/WR02/WR11 worker ownership and structured scan-ID/attempt/privacy assertions.
3. **T2:** test-first WR03–WR05 deterministic child launch, argv/env, timeout, cancellation, TERM/KILL/reaping, heartbeat, lost lease and drain cases.
4. **T3:** implement the smallest worker-only cleanup required by evidence; preserve `RunnerOutcome`, callbacks and transaction timing.
5. **T4:** test-first WR08–WR10 runner preconditions, application delegation/baseline/suppression/cache parity, successful/incomplete/failed/cancelled/stale execution and attempt-tagged logs; implement smallest runner-side changes.
6. **T5:** rerun C25 transaction/failure-atomicity suites, C26 PostgreSQL 17 suite twice and justified narrow real-DB tests; do not absorb C56 repeated stress.
7. **T6:** inspect imports, public exits/CLI/DSN privacy, legacy patch seams, fingerprint/report/API/schema parity and redaction; stop for ChatGPT on behavior/architecture drift.
8. **T7:** full `mise run check`, coverage >=90%, strict Pyright 0, `mise run test:postgres` twice where available, runtime and real Docker smoke, schema/inventory/privacy/build/security and all seven required CI jobs.
9. **T8:** provide exact SHA, WR01–WR12 evidence, commands/counts, cleanup, limitations; open **one unmerged** implementation PR for ChatGPT independent review.

## Non-goals and merge/acceptance gates

- Worker must not evaluate policies or gates; runner must not launch/retry child processes or implement a second scan path.
- Do not change C24–C26 claims, attempts, fencing, cancellation winner/rollback, retry classification, retention, request/response schemas, fingerprints, Alembic migrations, or application semantics without a demonstrated issue and ChatGPT architecture approval.
- Preserve idle/heartbeat and timeout/grace bounds, in-flight shutdown drain and child stderr redaction; a slept interval cannot prove a race winner.
- Do not modify planning/ADR/progress or acceptance documentation as implementation agent. No PR self-merge. User explicitly authorizes each PR merge; ChatGPT verifies seven exact-head and post-merge CI jobs before advancing.
- No C28 implementation authorization. Stage C documentation/acceptance stays ChatGPT-owned and separately user-authorized.