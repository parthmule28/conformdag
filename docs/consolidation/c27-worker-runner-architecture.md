# C27 — Worker/Runner lifecycle and application ownership architecture

**Status: Stage A DESIGN PROPOSAL ONLY. C27 Stage B implementation is NOT AUTHORIZED.** This document is the ChatGPT-owned, source-audited design for [Issue #100](https://github.com/parthmule28/conformdag/issues/100), the canonical WR01–WR12 acceptance and T0–T8 plan. Independent Stage A PR review, separate user merge authorization, and **seven** green exact-merge-SHA `main` jobs must precede any separately authorized OpenCode implementation. C28 is not authorized.

**Exact accepted baseline:** `main@ff12049d5f671a896a0ced6365c6259f449187ba`. C26 is formally accepted: [Issue #96](https://github.com/parthmule28/conformdag/issues/96) closed after [Stage C PR #99](https://github.com/parthmule28/conformdag/pull/99) merged and [post-merge CI #43594331554](https://github.com/parthmule28/conformdag/actions/runs/43594331554) passed **seven** required jobs on this exact SHA. C27 depends on C10, C24, C25 and C26.

## 1. Source-audited responsibility inventory

| Code surface | Current verified owner/behavior | C27 decision |
| --- | --- | --- |
| `platform/worker.py` | `run_worker` handles SIGINT/SIGTERM drain and idle polling; `run_worker_once` claims, commits, launches child, decides retry/budget and triggers retention. `execute_claimed_scan` owns subprocess argv/env, bounded poll, heartbeat, cancellation and TERM→KILL. `RunnerOutcome` is a worker-side frozen dataclass for child supervision. | Keep as the sole process-lifecycle owner; prioritize missing focused tests/correlation over broad rewrite. |
| `platform/runner.py` | `execute_scan` validates claimed status/attempt, converts repository config, eligible baseline and active suppressions to canonical application inputs, invokes `conformdag.application.execute_scan`, ingests canonical report/findings, and uses fenced `transition_running_scan`. | Keep as the claimed application-execution/persistence adapter; no process supervision or second scan engine. |
| `platform/persistence/scans.py` | PostgreSQL `FOR UPDATE SKIP LOCKED` claims and stale reclaim; exact-attempt heartbeat; status/attempt conditional transitions with **winning session commit / losing session rollback**. Caller commits claims. | Remain sole state-machine and transaction authority; no speculative SQL modifications. |
| `platform/logging.py` | `JsonFormatter` sanitizes message and extras through shared credential redaction. Current worker/runner lifecycle events include `scan_id` but not consistently claim `attempt`. | Extend safe lifecycle event extras with numeric attempt; preserve event names and redaction. |
| Tests | `tests/test_platform.py` covers child argv/DSN privacy, heartbeat, timeout, SIGTERM/KILL, cancellation, drain, error/redaction, application parity and stale attempts. C25 tests in `tests/platform/test_{worker,runner,transition}_transactions.py` cover commit/rollback. C26 `test_postgres.py` proves 20 real Postgres scenarios in the always-on CI service. | Reuse all existing evidence; add only missing deterministic tests and, where justified, narrow true Postgres assertions. |

**Finding:** Most architectural responsibilities were already separated by C10/C24–C26. C27 must **not** fabricate a second execution protocol or relocate existing state transitions. The concrete remaining gaps are explicit ownership/correlation contracts, focused child-supervision characterization, and ensuring later refactors cannot weaken fencing/retention.

## 2. Interface and compatibility decision

Retain these callable surfaces and behavioral contracts unless ChatGPT approves a specific proven defect:

- `conformdag.platform.worker`: `WorkerSettings` and its environment names/defaults/validation; frozen `RunnerOutcome(error: str, retryable: bool, cancelled: bool)`; `execute_claimed_scan(session_factory, dsn, scan_id, settings, claim_attempt)`; `run_worker_once`, `run_worker`, `request_shutdown`, `install_signal_handlers`. Preserve monkeypatch seams used by existing tests and demo/runtime callers.
- Runner invocation: `sys.executable -m conformdag.platform.runner --scan-id <id> --claim-attempt <number>` with `CONFORMDAG_PLATFORM_DSN` in child **environment**, not argv. Keep `python -m` entrypoint, `--dsn` direct manual compatibility and `runner.execute_scan(scan_id, dsn, claim_attempt=None)` for direct/test callers.
- Runner's current integer return behavior and worker's existing mapping remain: `0` normal or already-cancelled, `1` handled execution failure, `2` rejected/unclaimable or missing-repository condition. The worker's **retryable** result remains tied to launch/timeout or signal termination, not newly invented JSON stdout or changed protocol.
- The application scan workflow is authoritative for evaluation/gates/suppressions; runner only adapts repository/platform data into its canonical inputs. `worker_parse_cache()` is a historically named runner-side *application adapter*, not worker process policy; preserve it as an import/monkeypatch seam unless a demonstrated issue forces review.
- Log events `scan_claimed`, `scan_finished`, `scan_started` and `scan_completed` gain `extra={scan_id, attempt}` consistently in both tiers; additional safe context is additive. Do not rename events or inject credentials, source, DSNs or raw stderr. Preserve `redact_credentials` for failures and relay.

**No scope for:** new orchestration frameworks, a runner JSON-IPC service, another `ScanReport` model or evaluator, schema/Alembic changes, changing HTTP request/response contracts, changing process command-line protocol, changing C25 atomic winners/losers, or combining C44 observability and C56 large stress work into C27.

## 3. Transaction and process timelines to preserve

```text
worker: claim queued/stale (SQL SKIP LOCKED) ── caller commits
         │
         ├─ child python -m runner (--scan-id, --claim-attempt; DSN in env)
         │        │
         │        ├─ verify RUNNING + claimed attempt, repository
         │        ├─ configuration + baseline/suppressions → application.execute_scan
         │        └─ ingest canonical ScanReport + fenced SQL transition
         │                ├─ winner → commit all staged ingestion
         │                └─ loser  → rollback all staged ingestion
         │
         ├─ bounded communicate/heartbeat/cancel/TERM→KILL
         ├─ if still RUNNING and same attempt: retry or terminal-fail
         ├─ if already terminal/cancelled/newer attempt: do not overwrite
         └─ retention trigger/commit (failure does not undo prior terminal commit)
```

Retain current `poll_seconds`, `idle_seconds >= 2 * poll_seconds`, worker timeout and `_CANCEL_GRACE_SECONDS` semantics. Lost heartbeat ownership stops child. The worker's shutdown request drains the in-flight scan; it does not silently cancel/requeue a healthy running child. The runner never decides retries or retention. A PostgreSQL row lock and conditional transition, **not sleep duration**, decides cancellation/attempt winners.

## 4. Acceptance test plan

[Canonical Issue #100](https://github.com/parthmule28/conformdag/issues/100) supplies WR01–WR12 exact assertions and T0–T8 sequencing. Focused acceptance grouping:

| Test group | Expected proof |
| --- | --- |
| Worker lifecycle WR01–WR07 | Claim commit before child launch; fixed argv + DSN environment; launch/timeout/exit/failure and attempt-budget classification; heartbeat using fresh session, cancellation/TERM→KILL, graceful drain, after-terminal retention with C25 rollback isolation. |
| Runner/application WR08–WR10 | Valid RUNNING + expected attempt; delegated one canonical application scan; configuration, suppression and baseline parity; complete/incomplete/error mappings; whole-session atomic fenced ingestion and rollback for stale/cancelled losers. |
| Correlation and privacy WR11 | Both worker/runner lifecycle events include scan ID and numeric attempt, preserving names, error redaction, no raw DSN in argv/logs, safe exception diagnostics. |
| Integrated gate WR12 | `mise run check`, coverage >=90%, Pyright 0, security/privacy/schema/build, local `mise run test:postgres` twice when safe local service available, `mise run test:runtime` and Docker smoke, **seven mandatory GitHub CI jobs**; PG17 test suite repeated twice in hosted CI and final C26-owned database/backend cleanup zero. |

C26's 20 PostgreSQL tests already validate critical claim/cancel/fencing cases, so an extra repeated high-volume stress harness would duplicate **C56**. Add a narrow PostgreSQL test only for a newly justified process/runner DB interaction not already evidenced. Existing local `tests/test_platform.py` child tests use some timing assertions; additions should prefer barriers/events or observable PostgreSQL lock state, using deadlines only to fail safely.

## 5. Implementation handoff and stop policy

Following **separate explicit Stage B user authorization**, OpenCode Sol may use bounded Luna Max subagents with **one writer per worktree**. T0: exact merge baseline and all patch seams; T1: ownership/worker logging RED tests; T2: child supervision RED tests; T3: minimal worker GREEN cleanup; T4: runner validation/parity/transaction + logging RED/GREEN; T5: C25 + C26 real PostgreSQL twice, add narrow proof if needed; T6: no behavior drift/security review; T7: full commands and hosted seven-job CI; T8: return **one unmerged implementation PR**, exact SHA, WR01–WR12 evidence, no acceptance declaration.

ChatGPT independently reviews every change and exact-head CI. **Each PR merge requires explicit user permission**, followed by seven green exact-merge-SHA main jobs. Stage C acceptance documentation belongs to ChatGPT and also requires a separately authorized docs PR, its own post-merge seven-job CI, and formal issue closure. C28 is not automatically authorized.

**Stop for architecture review** if a test demonstrates a real defect demanding changes to persistence conditional commit/rollback, retryable classification, worker's cancellation/timeout/grace boundary, report semantics, new schema/migrations, or external protocol. Do not use resets/force-push/destructive cleanup, discard unrelated work or expose passwords in logs.

## 6. Rejected alternatives

| Alternative | Why rejected for C27 |
| --- | --- |
| Put retry/polling into `runner.py` | Conflates process supervisor and application adapter; breaks isolation. |
| Move SQL conditional transitions into worker/runner | Reverses accepted C24–C26 state-machine owner and transaction evidence. |
| Introduce new runner RPC/IPC JSON protocol and outcome enum | No demonstrated gap; adds compatibility/failure surface and duplicate outcome model. |
| Rewrite application scanning in runner | Violates C10's single execution workflow and fingerprint/report parity. |
| Add high-volume worker stress infrastructure here | Owned by C56; C27 needs bounded focused proof and inherited C26 real PostgreSQL suite. |