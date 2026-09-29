# C11 Outcome Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify any canonical `ScanReport` consistently and map that result to existing CLI and platform contracts.

**Architecture:** A pure application classifier reads only report fields and the neutral gate-layer blocking primitive. CLI and runner independently translate its enum into their respective exit/status representations; neither adds classification to `ScanExecutionResult`.

**Tech Stack:** Python 3.12, StrEnum, Pydantic models, Typer, SQLAlchemy, pytest, mise.

**Spec:** `docs/superpowers/specs/2026-09-29-c11-outcome-classification-design.md`

## Global Constraints

- Preserve `ScanReport` serialization, gate rules, finding-blocking semantics, `ScanExecutionResult`, and the single scan pipeline.
- No Typer, FastAPI, SQLAlchemy, MCP, or platform imports in application code.
- CLI outcomes: success 0, policy failure 1, invalid input 2 (preflight only), incomplete 3.
- Platform outcomes: success/policy failure `SUCCEEDED`, incomplete `FAILED`; preserve ingestion, error text, fencing, and subprocess return values.
- Do not merge the PR; update only the C11 ledger row with actual evidence.

## Review Focus

- Inconsistent `complete=False` without fatal issue must classify incomplete (Task 1).
- Inconsistent `complete=True` with fatal issue must classify incomplete (Task 1).
- Passing gate plus blocking finding must remain success, but runtime FAIL must still fail policy (Task 1; CLI Task 2).
- Suppressed blocking findings and nonblocking semantic failures must not fail legacy no-gate classification (Task 1).
- Late cancellation or stale attempt must not be overwritten by classification or ingestion (Task 3).

---

### Task 1: Pure application outcome contract

**Files:** Create `src/conformdag/application/outcomes.py`, `tests/application/test_outcomes.py`; modify `src/conformdag/application/__init__.py`.

**Interfaces:** Consumes `ScanReport`, `FindingStatus`, `gates.blocking_findings(report)`. Produces `ExecutionOutcome(StrEnum)` with values `success`, `policy_failure`, `incomplete`, and `classify_report(report: ScanReport) -> ExecutionOutcome`, both re-exported in `application.__all__`.

- [ ] **Step 1: Write the failing tests.** Parameterize `test_classify_report` using a minimal `RunMetadata`/`ScanReport` fixture and report copies; assert expected enum for complete empty report, failed gate, passing gate + blocking finding, passing gate + runtime FAIL, no-gate blocking finding, suppressed blocking finding, nonblocking semantic FAIL, runtime FAIL without gate, `complete=False` without fatal issue, and `complete=True` with fatal issue. Assert the public facade exports the exact function/enum and JSON round-tripped report produces the same outcome.
- [ ] **Step 2: Confirm RED.** Run `mise exec -- uv run pytest tests/application/test_outcomes.py -x --tb=short`; expect import failure for absent classifier.
- [ ] **Step 3: Implement minimal contract.** Define enum/function in `outcomes.py`; first incomplete check (`not report.complete or any(issue.fatal ...)`), then failed gate; only when `gate_result is None` check `blocking_findings(report)`; finally check runtime observation `status is FindingStatus.FAIL`, else success. Re-export in `application/__init__.py` and `__all__`.
- [ ] **Step 4: Confirm GREEN.** Run focused test above plus `mise exec -- uv run pytest tests/test_gates.py tests/application/test_scan.py -q`.
- [ ] **Step 5: Commit.** `git add src/conformdag/application/outcomes.py src/conformdag/application/__init__.py tests/application/test_outcomes.py && git commit -m "feat: classify canonical scan outcomes"`.

### Task 2: CLI outcome adapter

**Files:** Modify `src/conformdag/cli.py` (scan command imports and exit block near line 682), `tests/test_cli.py` (gate/runtime/incomplete scan cases near lines 759–920).

**Interfaces:** Consumes `application.classify_report(report)` and `ExecutionOutcome`; produces unchanged CLI exit codes 0/1/2/3 and unchanged rendered report.

- [ ] **Step 1: Write failing adapter regressions.** In `tests/test_cli.py`, add focused scan cases for `complete=False` without fatal issue → exit 3, `complete=True` with fatal issue → exit 3 (use existing scan-service monkeypatch pattern), passing gate + blocking finding → exit 0, passing gate + runtime FAIL → exit 1. Retain existing failed-gate, no-gate blocking, runtime, and invalid-input assertions; verify rendered JSON still has no outcome field.
- [ ] **Step 2: Confirm RED.** Run `mise exec -- uv run pytest tests/test_cli.py -k 'outcome or gate or incomplete' -x --tb=short`; at least the inconsistent incomplete regression should fail before changing CLI.
- [ ] **Step 3: Implement mapping.** After rendering, call `classify_report(report)`; raise `typer.Exit(code=3)` for `INCOMPLETE`, `typer.Exit(code=1)` for `POLICY_FAILURE`, fall through for `SUCCESS`. Remove the duplicated fatal/gate/blocking/runtime checks and obsolete imports, but leave invalid-input preflight at 2.
- [ ] **Step 4: Confirm GREEN.** Run `mise exec -- uv run pytest tests/test_cli.py -q`.
- [ ] **Step 5: Commit.** `git add src/conformdag/cli.py tests/test_cli.py && git commit -m "refactor: map CLI exits from scan outcomes"`.

### Task 3: Runner outcome adapter and integration gate

**Files:** Modify `src/conformdag/platform/runner.py` (completion near lines 186–210), `tests/test_platform.py` (runner cases near lines 3146–3300 and 3687–3747), `docs/consolidation/progress.md` (C11 row only).

**Interfaces:** Consumes `application.classify_report(report)` and `ExecutionOutcome`. Produces `ScanStatus.FAILED` with existing `_incomplete_error(report)` only for `INCOMPLETE`; `SUCCEEDED` for both other outcomes, maintaining existing runner return codes and fenced transitions.

- [ ] **Step 1: Write failing runner regressions.** Through existing mocked `execute_application_scan` and platform fixture, assert `complete=True` plus fatal issue persists report and `FAILED`, returning 1; `complete=False` without fatal issue persists report and `FAILED`, returning 1; a failed gate or runtime FAIL persists canonical report with `SUCCEEDED`, returning 0. Reuse existing cancellation and stale-attempt tests; add a cancellation/stale-attempt case for a policy-failure report if current cases do not exercise that branch.
- [ ] **Step 2: Confirm RED.** Run `mise exec -- uv run pytest tests/test_platform.py -k 'runner and (outcome or incomplete or gate)' -x --tb=short`; the fatal + complete regression should fail before runner changes.
- [ ] **Step 3: Implement mapping.** Replace the `if not report.complete` completion branch with `if classify_report(report) is ExecutionOutcome.INCOMPLETE`; retain existing ingestion, `_was_cancelled` checks, `transition_running_scan(... expected_attempt=claim_attempt)`, error string, and return paths unmodified otherwise. Do not mark policy failure as platform failed.
- [ ] **Step 4: Confirm GREEN and full gate.** Run `mise exec -- uv run pytest tests/application/test_outcomes.py tests/test_cli.py tests/test_gates.py tests/application/test_scan.py tests/test_platform.py -q`, `mise run check`, `mise run test:coverage`, `mise run schema --check`, and `git diff --check`. Record actual outputs and environmental limitations; do not claim unavailable gates passed.
- [ ] **Step 5: Update C11 ledger and commit.** Set only C11 row to review with commits, focused/full evidence, intentional inconsistent-report compatibility refinement, schema note, and pending PR review. `git add src/conformdag/platform/runner.py tests/test_platform.py docs/consolidation/progress.md && git commit -m "feat: centralize scan outcomes"`.
- [ ] **Step 6: Push and open/update implementation PR without merging.** Follow project pre-review methodology: push implementation branch, create PR against `main` (not the documentation PR), attach exact-head CI evidence when available; seek review before any merge.
