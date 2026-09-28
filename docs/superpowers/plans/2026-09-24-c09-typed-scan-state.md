# C09 Typed Scan State and Trigger Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.
> **Execution approach:** Native / single-session. Execute Tasks 1 → 4 sequentially. Do not use subagent-driven implementation; request a separate independent review after implementation.

**Goal:** Give platform scan lifecycle and trigger values one typed domain while preserving string storage and wire compatibility and enforcing exact-attempt heartbeat fencing.

**Architecture:** Add platform-owned `StrEnum` types and active/terminal groups in `platform/domain.py`. Keep SQLAlchemy columns as strings, converting through `.value` at persistence boundaries and using typed values in platform business logic and response contracts. Retain the existing atomic DB transition functions, validate legal running-transition targets, and require an attempt throughout the worker heartbeat call chain.

**Tech Stack:** Python 3.12 `enum.StrEnum`, SQLAlchemy 2, Pydantic 2, pytest, Ruff, Pyright, mise/uv.

**Spec:** `docs/superpowers/specs/2026-09-24-c09-typed-scan-state-design.md`

## Global Constraints

- Preserve `ScanRow.status` and `ScanRow.trigger` as SQLAlchemy `String` columns and `Mapped[str]` attributes.
- Preserve persisted and HTTP spellings exactly: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `dashboard`, and `demo`.
- Add no trigger values beyond existing `DASHBOARD` and `DEMO`.
- Keep scan-state mutation inside the conditional transition primitives in `platform/db.py`.
- Keep successful transition commit and lost-race rollback semantics.
- Heartbeat requires an exact attempt and matches both `RUNNING` status and the stored attempt.
- `transition_running_scan()` allows only `RUNNING -> QUEUED` with requeue, or `RUNNING -> SUCCEEDED/FAILED` without requeue.
- Do not add a migration, SQLAlchemy enum column, schema export, persistence package split, or runner-to-application delegation.
- Keep finding statuses such as `FAIL` and `ERROR` separate from scan status.
- Use `mise run setup` for isolated worktrees; run `mise run check` before opening the product PR.

## File Map

- Create `src/conformdag/platform/domain.py` for `ScanStatus`, `ScanTrigger`, `ACTIVE_SCAN_STATUSES`, and `TERMINAL_SCAN_STATUSES`.
- Modify `src/conformdag/platform/db.py` for typed status transitions, exact-attempt heartbeat, value conversion, and baseline/claim comparisons.
- Modify `src/conformdag/platform/app.py`, `runner.py`, and `worker.py` for typed status/trigger usage and response-boundary conversion.
- Modify `src/conformdag/platform/contracts.py` so scan-summary response statuses are `ScanStatus`; leave `FindingResponse.status` as a finding string.
- Modify `src/conformdag/platform/aggregates.py` and `demo.py` to consume the central status groups and trigger enum.
- Create `tests/test_platform_domain.py` for enum values/groups; extend `tests/test_platform.py` for persistence transitions, worker fencing, API serialization, aggregates, and demo persistence.
- Update `docs/consolidation/progress.md` to `review` only after the implementation head is CI-green and independently reviewed. The ledger cites that reviewed implementation SHA and CI; verify final ledger-head CI afterward.

## Review Focus

- A worker using an old attempt after reclaim cannot heartbeat or complete the new attempt; pin both outcomes in the stale-attempt platform test.
- An incompatible target/requeue pair cannot issue SQL or mutate a running row; parameterize every invalid pair in the transition test.
- A terminal scan cannot be cancelled or transitioned again; parameterize terminal status rows and verify they remain unchanged.
- Historical lowercase strings still parse into typed scan response contracts and serialize to the same JSON strings; test summary and overview payloads.
- Both real trigger sources persist unchanged and active/completed aggregates retain their current counts; assert `dashboard`/`demo` row values and the existing aggregate endpoints.

---

### Task 1: Define the platform scan-state domain

**Files:**
- Create: `src/conformdag/platform/domain.py`
- Create: `tests/test_platform_domain.py`

**Interfaces:**
- Produces `ScanStatus(StrEnum)` with values `queued`, `running`, `succeeded`, `failed`, and `cancelled`.
- Produces `ScanTrigger(StrEnum)` with values `dashboard` and `demo`.
- Produces typed active and terminal status groups for aggregate and demo logic.

- [ ] **Step 1: Write domain value and group tests**

```python
from conformdag.platform.domain import ACTIVE_SCAN_STATUSES, TERMINAL_SCAN_STATUSES, ScanStatus, ScanTrigger


def test_scan_status_values_are_the_persisted_spellings() -> None:
    assert [status.value for status in ScanStatus] == ["queued", "running", "succeeded", "failed", "cancelled"]


def test_scan_trigger_values_include_only_existing_sources() -> None:
    assert [trigger.value for trigger in ScanTrigger] == ["dashboard", "demo"]


def test_active_and_terminal_status_groups_are_typed() -> None:
    assert ACTIVE_SCAN_STATUSES == frozenset({ScanStatus.QUEUED, ScanStatus.RUNNING})
    assert TERMINAL_SCAN_STATUSES == frozenset({ScanStatus.SUCCEEDED, ScanStatus.FAILED, ScanStatus.CANCELLED})
```

- [ ] **Step 2: Run the focused test and verify the missing module fails**

Run: `mise exec -- uv run pytest tests/test_platform_domain.py -q`
Expected: collection fails because `conformdag.platform.domain` does not exist yet.

- [ ] **Step 3: Add the enum domain**

Create the module with `from enum import StrEnum`, the five scan statuses and two existing triggers, and these exact typed groups:

```python
ACTIVE_SCAN_STATUSES: frozenset[ScanStatus] = frozenset({ScanStatus.QUEUED, ScanStatus.RUNNING})
TERMINAL_SCAN_STATUSES: frozenset[ScanStatus] = frozenset(
    {ScanStatus.SUCCEEDED, ScanStatus.FAILED, ScanStatus.CANCELLED}
)
```

- [ ] **Step 4: Run the domain test module**

Run: `mise exec -- uv run pytest tests/test_platform_domain.py -q`
Expected: all three domain tests pass.

- [ ] **Step 5: Run the repository gate before committing**

Run: `mise run check`
Expected: formatting, lint, Pyright, default tests, policy validation, and dependency inventory pass.

- [ ] **Step 6: Commit the domain unit**

```bash
git add src/conformdag/platform/domain.py tests/test_platform_domain.py
git commit -m "refactor: add typed platform scan domain"
```

### Task 2: Type and validate persistence transitions

**Files:**
- Modify: `src/conformdag/platform/db.py:233-345`
- Modify: `src/conformdag/platform/runner.py` scan-state reads and completion targets
- Modify: `src/conformdag/platform/worker.py` scan-state reads and heartbeat call chain
- Modify: `tests/test_platform.py` state-transition tests and imports

**Interfaces:**
- Consumes `ScanStatus`, `ACTIVE_SCAN_STATUSES`, and `TERMINAL_SCAN_STATUSES` from Task 1.
- Types `transition_running_scan(session: Session, scan_id: str, status: ScanStatus, error: str | None = None, *, requeue: bool = False, expected_attempt: int | None = None) -> bool`; adopts the existing `transition_scan_to_cancelled(session: Session, scan_id: str) -> bool`; and tightens the existing `heartbeat_running_scan(session: Session, scan_id: str, attempt: int) -> bool`.
- Produces worker helpers that require `claim_attempt: int`, and a runner that uses typed completion targets while passing the current production attempt.

- [ ] **Step 1: Add table-driven valid and invalid transition tests**

There are 10 target/requeue combinations: 3 valid and 7 invalid. Parameterize valid pairs as `(ScanStatus.QUEUED, True)`, `(ScanStatus.SUCCEEDED, False)`, and `(ScanStatus.FAILED, False)`. Each valid case must return `True`, store the target's `.value`, and leave `finished_at` unset only for requeue. Parameterize all seven invalid pairs as `(ScanStatus.QUEUED, False)`, `(ScanStatus.SUCCEEDED, True)`, `(ScanStatus.FAILED, True)`, `(ScanStatus.RUNNING, False)`, `(ScanStatus.RUNNING, True)`, `(ScanStatus.CANCELLED, False)`, and `(ScanStatus.CANCELLED, True)`. Every invalid case must raise `ValueError` before SQL is issued and leave the row `running`.

Use this test body for the valid cases:

```python
@pytest.mark.parametrize(
    ("target", "requeue"),
    [
        (ScanStatus.QUEUED, True),
        (ScanStatus.SUCCEEDED, False),
        (ScanStatus.FAILED, False),
    ],
)
def test_running_scan_accepts_valid_transition_targets(
    platform_env: str, target: ScanStatus, requeue: bool
) -> None:
    factory = initialize_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path="."))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="running", attempts=1))
        session.commit()

    with factory() as session:
        assert transition_running_scan(session, "scan1", target, requeue=requeue, expected_attempt=1) is True

    scan = only_scan(platform_env)
    assert scan.status == target.value
    assert (scan.finished_at is None) is requeue
```

```python
@pytest.mark.parametrize(
    ("target", "requeue"),
    [
        (ScanStatus.QUEUED, False),
        (ScanStatus.SUCCEEDED, True),
        (ScanStatus.FAILED, True),
        (ScanStatus.RUNNING, False),
        (ScanStatus.RUNNING, True),
        (ScanStatus.CANCELLED, False),
        (ScanStatus.CANCELLED, True),
    ],
)
def test_running_scan_rejects_incompatible_transition_targets(
    platform_env: str, target: ScanStatus, requeue: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = initialize_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path="."))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="running", attempts=1))
        session.commit()

    with factory() as session:
        def fail_on_execute(*_args: Any, **_kwargs: Any) -> NoReturn:
            pytest.fail("invalid transition must be rejected before SQL")

        monkeypatch.setattr(session, "execute", fail_on_execute)
        with pytest.raises(ValueError):
            transition_running_scan(session, "scan1", target, requeue=requeue, expected_attempt=1)

    assert only_scan(platform_env).status == "running"
```

- [ ] **Step 2: Run the transition tests and verify the new restrictions fail**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "running_scan_accepts_valid_transition_targets or running_scan_rejects_incompatible_transition_targets" -q`
Expected: valid cases pass; invalid cases fail because the current primitive accepts incompatible target/requeue pairs.

- [ ] **Step 3: Add terminal-state and exact-attempt fencing coverage**

Add `test_terminal_scan_cannot_be_cancelled_or_transitioned`, parameterized over `ScanStatus.SUCCEEDED`, `ScanStatus.FAILED`, and `ScanStatus.CANCELLED`. For each status, seed a terminal row and assert `transition_scan_to_cancelled()` returns `False` and a call to `transition_running_scan()` with target `ScanStatus.FAILED` and `expected_attempt=1` returns `False`. Rewrite `test_stale_worker_claim_cannot_refresh_or_finish_reclaimed_scan` to seed a stale running scan at attempt `1` (for example, with `seed_stale_running_scan()`), call `claim_queued_scan()` with `stale_running_cutoff(600)` and `max_attempts=3`, assert the claimed row is now attempt `2`, and commit. Then assert heartbeat with attempt `1` returns `False`, transition with `expected_attempt=1` returns `False`, and heartbeat with attempt `2` returns `True`.

Add `test_cancel_transition_loser_rolls_back_pending_changes` to pin rollback after another caller wins cancellation:

```python
def test_cancel_transition_loser_rolls_back_pending_changes(platform_env: str) -> None:
    factory = initialize_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path="."))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="running", attempts=1))
        session.commit()

    with factory() as session:
        assert transition_scan_to_cancelled(session, "scan1") is True

    with factory() as session:
        scan = session.get(ScanRow, "scan1")
        assert scan is not None
        scan.error = "stale worker result"
        assert transition_scan_to_cancelled(session, "scan1") is False

    scan = only_scan(platform_env)
    assert scan.status == ScanStatus.CANCELLED.value
    assert scan.error is None
```

- [ ] **Step 4: Run the terminal and fencing tests before implementation**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "terminal_scan or stale_worker_claim or cancel_transition" -q`
Expected: terminal-state and cancellation winner/rollback assertions pass against the current primitives, while the stale-worker test fails because the current heartbeat does not accept a required positional attempt.

- [ ] **Step 5: Implement typed DB transitions**

Import domain values in `db.py`. Keep `ScanRow.status` and `ScanRow.trigger` declarations and defaults as strings. Use `.value` for SQL comparisons and assignments. Type `transition_running_scan()` with `ScanStatus`; validate the target/requeue matrix before `session.execute()`. Change `heartbeat_running_scan()` to require positional `attempt: int` and include `ScanRow.attempts == attempt` with the `RUNNING` predicate. Preserve commit on an updated row and rollback when no row matches. In `worker.py`, require `claim_attempt: int` in `execute_claimed_scan()` and `_refresh_heartbeat()` and pass the attempt through to the primitive. Update all direct `execute_claimed_scan()` tests—`test_worker_refreshes_claim_heartbeat`, `test_worker_does_not_put_dsn_in_runner_argv`, and `test_cancellation_terminates_child_during_execution`—to pass the attempt stored on the seeded row (set up an attempt value where necessary). In `runner.py`, use `ScanStatus` for cancellation/current-state comparisons and transition targets, preserving exact-attempt completion predicates.

- [ ] **Step 6: Run persistence transition tests**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "running_scan or abandoned_scan or abandoned_running_scan or stale_worker_claim or cancel_transition or baseline_eligibility or worker or runner" -q`
Expected: legal transitions pass; invalid targets raise before SQL; terminal and stale-attempt transitions lose cleanly.

- [ ] **Step 7: Run the repository gate before committing**

Run: `mise run check`
Expected: formatting, lint, Pyright, default tests, policy validation, and dependency inventory pass after DB and worker/runner interfaces are updated together.

- [ ] **Step 8: Commit persistence and fencing changes**

```bash
git add src/conformdag/platform/db.py src/conformdag/platform/runner.py src/conformdag/platform/worker.py tests/test_platform.py
git commit -m "refactor: type platform scan transitions"
```

### Task 3: Convert route, response, aggregate, and demo boundaries

**Files:**
- Modify: `src/conformdag/platform/app.py`
- Modify: `src/conformdag/platform/contracts.py`
- Modify: `src/conformdag/platform/aggregates.py`
- Modify: `src/conformdag/platform/demo.py`
- Modify: `tests/test_platform.py` API, aggregate, and demo tests

**Interfaces:**
- Consumes typed DB functions and runner/worker state from Task 2.
- Produces API response contracts whose scan `status` fields are `ScanStatus`, with unchanged JSON values.
- Produces route, aggregate, and demo boundaries that convert typed domain values to unchanged SQL strings.

- [ ] **Step 1: Add boundary regression assertions**

Extend `test_register_and_trigger_scan_lifecycle` to assert the created row stores status `queued` and trigger `dashboard`, and endpoint JSON remains `queued`. Add a direct response-contract test showing persisted lowercase strings become typed enum fields while JSON serialization stays unchanged:

```python
from datetime import UTC, datetime

from conformdag.platform.contracts import OverviewScan, ScanSummaryResponse
from conformdag.platform.domain import ScanStatus


def test_scan_response_contracts_keep_lowercase_json_statuses() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    summary = ScanSummaryResponse.model_validate(
        {
            "scan_id": "scan1",
            "status": "queued",
            "created_at": created_at,
            "finished_at": None,
            "result_fingerprint": None,
            "complete": None,
            "gate_passed": None,
            "artifact_available": False,
        }
    )
    recent = OverviewScan.model_validate(
        {
            "scan_id": "scan2",
            "repository_id": "repo1",
            "repository_name": "r",
            "status": "succeeded",
            "created_at": created_at,
            "finished_at": created_at,
            "complete": True,
            "gate_passed": True,
        }
    )

    assert summary.status is ScanStatus.QUEUED
    assert summary.model_dump(mode="json")["status"] == "queued"
    assert recent.status is ScanStatus.SUCCEEDED
    assert recent.model_dump(mode="json")["status"] == "succeeded"
```

Keep `FindingResponse.status` checks on `FAIL`/`ERROR` unchanged.

Also assert that `test_demo_seed_creates_baseline_and_later_gate_failure` observes trigger `demo` on both seeded scans, `test_demo_worker_processes_interactive_scans_after_seed` observes `dashboard` on the user-triggered scan, and the existing overview test retains its active/completed counts across every scan status.

- [ ] **Step 2: Run the focused API tests**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "register_and_trigger_scan_lifecycle or scan_response_contracts_keep_lowercase_json_statuses or scan_status or overview or finding_payload or demo_seed_creates_baseline or demo_worker_processes_interactive_scans" -q`
Expected: persisted trigger and existing response assertions pass; enum identity assertions fail until scan response contracts are typed.

- [ ] **Step 3: Convert route and response-contract state values**

Use `ScanStatus` and `ScanTrigger` in `app.py`; persist `.value` and return status `.value` where route dictionaries are built. Type only `ScanSummaryResponse.status` and `OverviewScan.status` as `ScanStatus`. At route/model construction, explicitly coerce persisted statuses with `ScanStatus(row.status)`.

In `aggregates.py`, use `ScanStatus.SUCCEEDED.value` for successful-scan SQL filters and the central active/terminal groups for status sets. When a central enum group feeds a SQL `.in_(...)` predicate, pass its members' `.value` strings (for example, `tuple(status.value for status in ACTIVE_SCAN_STATUSES)`); do not rely on `StrEnum` being a `str` subclass. Coerce statuses when building `OverviewScan`.

In `demo.py`, make `_scan_state(session_factory: sessionmaker[Session], scan_id: str) -> tuple[ScanStatus, bool | None, str | None] | None` coerce persisted status. Type `_complete_scan(session_factory: sessionmaker[Session], dsn: str, scan_id: str, *, expected_status: ScanStatus, expected_complete: bool) -> None`, change all four expected outcomes to `ScanStatus.SUCCEEDED` / `ScanStatus.FAILED`, use central status groups for terminal checks, and persist enum `.value` for scan status and trigger. Do not change `FindingResponse.status`.

- [ ] **Step 4: Run route, aggregate, and demo tests**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "register_and_trigger_scan_lifecycle or scan_response_contracts_keep_lowercase_json_statuses or scan_status or overview or finding_payload or demo_seed_creates_baseline or demo_worker_processes_interactive_scans" -q`
Expected: selected tests pass, both existing trigger values persist unchanged, aggregates keep their counts, and scan status JSON strings are unchanged.

- [ ] **Step 5: Run the repository gate before committing**

Run: `mise run check`
Expected: formatting, lint, Pyright, default tests, policy validation, and dependency inventory pass after all production boundaries use the domain.

- [ ] **Step 6: Commit the final C09 implementation slice with the required subject**

```bash
git add src/conformdag/platform/app.py src/conformdag/platform/contracts.py src/conformdag/platform/aggregates.py src/conformdag/platform/demo.py tests/test_platform.py
git commit -m "refactor: type platform scan state"
```

### Task 4: Focused verification, audit, coverage, and review handoff

**Files:**
- Update: `docs/consolidation/progress.md` in a docs-only follow-up after the implementation head is CI-green and independently reviewed

**Interfaces:**
- Consumes all C09 implementation tasks.
- Produces a review-ready C09 implementation PR and later a ledger row with reproducible evidence.

- [ ] **Step 1: Run focused state and fencing tests**

Run: `mise exec -- uv run pytest tests/test_platform_domain.py -q` and `mise exec -- uv run pytest tests/test_platform.py -k "running_scan or abandoned_scan or abandoned_running_scan or stale_worker_claim or terminal_scan or cancel_transition or baseline_eligibility" -q`.
Expected: enum/group tests, transition legality, terminal no-ops, cancellation winner, attempt fencing, reclaim, and baseline behavior pass.

- [ ] **Step 2: Run focused API and serialization tests**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "register_and_trigger_scan_lifecycle or scan_response_contracts_keep_lowercase_json_statuses or scan_status or overview or finding_payload" -q`.
Expected: stored lowercase values become typed scan-status contracts and serialize to the same lowercase strings; finding statuses remain unchanged.

- [ ] **Step 3: Audit production scan-state and trigger literals**

Run from the repository root:

```bash
grep -REn "[\"'](queued|running|succeeded|failed|cancelled|dashboard|demo)[\"']" src/conformdag/platform --include='*.py'
```

Review every result. Raw values are allowed in the enum declarations in `platform/domain.py`, intentional `ScanRow` string defaults in `db.py`, and migration defaults. Non-status metadata keys or labels (for example the worker event key `finished_extra["cancelled"]` and static mount name `"dashboard"`) and diagnostic text may also contain these words. Scan-state terms must not remain in business comparisons, assignments, aggregate groups, route logic, worker/runner logic, or demo flow. Finding statuses such as `FAIL` and `ERROR` are outside this audit and outside C09.

- [ ] **Step 4: Run required repository gates**

Run each command from the repository root and retain its output:

```bash
mise run check
mise run test:coverage
mise run schema --check
git diff --check
```

Expected: default gate passes; coverage meets the repository's 90% threshold; schema check reports no drift; whitespace check exits zero.

- [ ] **Step 5: Push the implementation head and wait for its CI**

Before pushing, confirm migrations and ORM types/defaults are unchanged; `FindingResponse.status` is unchanged; HTTP status values remain lowercase strings; transition target validation runs before SQL; and stale-attempt tests cover heartbeat and completion. Push the implementation branch and open its PR against `main` without merging. Record the implementation head SHA and its CI run. Wait for all required CI jobs for that exact SHA to pass before requesting independent review.

- [ ] **Step 6: Complete independent review and re-verify any corrected head**

Request an independent review of the CI-green implementation head, focused on transition legality, cancellation one-winner behavior, heartbeat exact-attempt fencing, late-result fencing, and the raw-literal audit. Fix Critical or Important findings. For every correction, rerun the focused state/API tests and `mise run check`, `mise run test:coverage`, `mise run schema --check`, and `git diff --check`; commit and push the corrected implementation head. Wait for CI on that corrected SHA, then have the independent reviewer re-review that exact head. Repeat the correction/verification/review cycle until no Critical or Important findings remain. If review requires no code changes, the original implementation head remains the reviewed head.

- [ ] **Step 7: Update the ledger, verify the new PR head, and stop unmerged**

Only after independent review accepts a verified implementation head and its matching CI passes, update the C09 ledger row to `review`. Cite the exact reviewed implementation SHA and its CI run, along with local gate, coverage, schema, and whitespace evidence. Do not describe that CI as final-PR-head CI and do not put the ledger commit's own SHA in the row. Commit and push the ledger update as a separate docs-only commit on the implementation PR. This creates a new PR head: wait for all required CI jobs on that head, verify the exact final PR-head SHA and run, and record that evidence in the handoff (not in the ledger). Leave the implementation PR open and unmerged; the human retains merge authority.
