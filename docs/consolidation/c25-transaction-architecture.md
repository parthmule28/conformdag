# C25 — Transaction ownership decision

**Status:** Stage A architecture proposed on 2026-11-12; **implementation not authorized**. The canonical exact T0–T8 build contract is [Issue #92](https://github.com/parthmule28/conformdag/issues/92). This record captures the reasoning, ownership matrix, and non-goals; do not implement from this note alone.

**Baseline:** C24 is formally accepted on `main@6c192eee61113c65821a5e9273317c9b06d685d6`; [Issue #88](https://github.com/parthmule28/conformdag/issues/88) closed after Stage C acceptance. C24 created five persistence owner modules and the existing `platform.db` compatibility facade. No C25 source changes exist in this documentation-only design.

## Decision: bounded hybrid transaction ownership

**Retain two explicit commit patterns.** (1) `persistence.scans` keeps the three approved conditional UPDATE transition primitives as commit-on-win / rollback-on-loss, because status arbitration and attempt fencing must be atomic. (2) ordinary persistence/service functions never commit; their caller (worker, runner, HTTP route) defines the unit of work. A failing test may justify a targeted correction, but the goal is not a universal transaction helper or a second scan mutation path.

| Responsibility / owner | Who commits on success? | On failure / important guard |
| --- | --- | --- |
| `claim_queued_scan` in `persistence.scans` | `worker.run_worker_once`; includes exhausting the stale-claim attempt budget when no scan is returned | Claim function never commits; preserve `SKIP LOCKED`, statuses, attempts and ordering |
| `transition_running_scan` | Transition helper itself commits **all staged work in its session** on a matching conditional update | Helper rolls back on no winner. This is intentional for `runner._ingest`'s report+findings changes; do not use it with unrelated pending writes |
| `transition_scan_to_cancelled` | Helper itself | Conditional queued/running predicate; cancellation remains one winner, never overwrites terminal |
| `heartbeat_running_scan` | Helper itself | Match running status **and exact attempt**; rollback on mismatch |
| `runner._ingest` | No independent commit; `transition_running_scan` commits staged report, findings and completion status together | A cancelled/stale attempt must not retain partially ingested findings/report; ingestion error must roll back |
| `worker._apply_retention` | Worker commits after staging artifact pruning | Separate maintenance transaction from prior completion commit; preserve findings, newest scan row and retention ordering |
| `services.repositories`, `services.scans.queue_scan`, `services.baselines` | Caller HTTP route | Service may `flush` or stage but does not commit; failed batch registration must not save a subset |
| `services.suppressions` | Caller HTTP route | Service `flush` may raise uniqueness conflict; caller must roll back before further use and preserve error mapping |
| `PackService` / `policy_editing` | Not a database transaction: file lock + atomic replace | File mutations are a separate durability boundary; no cross-resource transaction with workspace repository registration |

## Why this design

The runner already stages report/finding deletion and inserts before invoking the fenced completion primitive, which commits or rolls back its session. Moving that commit to a separate caller without proof risks turning cancellation into a non-atomic report/status sequence. Conversely, placing commits inside `register_repository`, `queue_scan`, `set_baseline` or suppression services would break caller-owned multi-step atomicity. Worker claim and retention have separate existing commits for distinct lifecycle phases.

## Source evidence

- `src/conformdag/platform/persistence/scans.py`: queued/stale claims have no `commit`; all three conditional `UPDATE` helpers call `commit` after a matching rowcount and `rollback` otherwise.
- `src/conformdag/platform/runner.py`: `_ingest` deletes prior finding rows, stages report fields and adds new findings; `execute_scan` calls the transition afterward.
- `src/conformdag/platform/worker.py`: `run_worker_once` commits claims, handles retries/terminal transitions, then `_apply_retention` commits separately.
- `src/conformdag/platform/routes/{repositories,scans,suppressions}.py` commits service-created repositories, workspace batches, scan queue requests, baseline and suppression changes; `services/repositories.py` and `services/suppressions.py` may call `session.flush()` and surface conflicts.
- `src/conformdag/platform/packs.py` holds a filesystem lock around policy pack edits; it is not SQL transaction coordination. `routes/repositories.py` registers workspace packs before the database batch commit.

## Scope / safety decisions

- **Test first; change only where proven.** Characterize current outcomes and inject failures at boundaries before altering transaction ownership. Successful characterization is not automatically a production code change request.
- Preserve C09 typed state transitions, cancellation/stale-attempt fencing, C24 five-owner topology, the legacy facade, Alembic revisions, report JSON/fingerprints, API statuses, suppression uniqueness and retention semantics.
- SQLite and mocked PostgreSQL advisory tests are useful but do not prove real `FOR UPDATE SKIP LOCKED` concurrency. The mandatory dedicated PostgreSQL suite is **C26**. In C25 a live PostgreSQL run is optional when available, not an unconditional local/CI gate.
- The existing retention code protects the newest **scan row** even when it contains no report. Do not silently reinterpret it as newest non-null artifact retention.
- Workspace pack registration and the database repository batch are **not** one cross-resource ACID transaction. Do not promise rollback of already registered pack metadata after a database failure.
- No blanket `session.begin` refactor, generic UnitOfWork abstraction, new migration, dependency, endpoint or schema change. A real behavior change must be evidenced and reviewed.

## Alternatives rejected

| Alternative | Why rejected now |
| --- | --- |
| Every service commits internally | Breaks multi-step atomicity and makes callers unable to choose a unit of work |
| All transitions become caller-commit-only | Risks weakening cancellation/attempt fencing and runner's report+status atomicity |
| One generic UnitOfWork across database and policy YAML files | Invents a cross-resource guarantee absent from the product and expands C25 beyond its purpose |
| Add mandatory real PostgreSQL suite to C25 | C26 explicitly owns the dedicated integration infrastructure; keep C25 scoped while disclosing its limits |

## Review and execution gates

Follow [Issue #92](https://github.com/parthmule28/conformdag/issues/92) for sequential T0–T8 tests, failure injections and exact stop conditions. Full `mise run check`, coverage >=90%, schema/import/packaging/security regression and six required hosted CI jobs remain mandatory. Preserve compatibility and record all measured evidence, not assumed behavior.

**Ownership:** ChatGPT writes architecture, planning/ledger/acceptance documents and independently reviews changes. OpenCode GPT-6.1 Sol orchestrates bounded GPT-6 Luna Max subagents only after separate Stage B authorization, with one exclusive code writer per worktree and read-only parallel reviewers. Implementation/test PR must remain unmerged. No C26 automatically. The Stage A documentation PR must itself be independently reviewed, user-authorized, merged, and green on exact-merge-SHA `main` CI before C25 implementation is authorized.
