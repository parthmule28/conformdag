# C10 Platform Runner Delegation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace duplicate platform scan orchestration with the canonical application workflow while preserving platform persistence and lifecycle fencing.

**Architecture:** `platform.runner` adapts persisted configuration, eligible baseline data, and live operational suppressions into application-owned values and calls `application.execute_scan()`. It then ingests the returned canonical report and uses the existing attempt-fenced transitions. Worker process lifecycle remains unchanged.

**Tech Stack:** Python 3.12, Pydantic models, SQLAlchemy platform adapter, pytest, Ruff, Pyright, `mise`.

**Spec:** `docs/superpowers/specs/2026-09-28-c10-platform-runner-design.md` (grounded in `docs/consolidation/prompts/C10-platform-runner.md` and the C06 application scan contract).

## Global Constraints

- `src/conformdag/scan.py:scan_repository()` remains the single canonical core evaluation primitive.
- `application` must not import SQLAlchemy, FastAPI, Typer, or platform adapters.
- The platform runner owns claimed-scan loading, baseline/suppression adapters, canonical ingestion, cancellation checks, and attempt-fenced completion; it must not own scan orchestration, gate calculation, suppression application, or final normalization.
- Worker remains owner of claim, subprocess lifecycle, heartbeat, timeout, cancellation process control, retry, and retention trigger.
- Persisted scan status/trigger values and report JSON remain compatible; no migration, ORM enum, schema, or API change is in scope.
- Platform scans do not gain implicit semantic-provider or runtime execution wiring.
- Existing cancellation and exact-attempt fencing must continue to prevent late completion writes.

## Review Focus

- Runner application configuration versus platform/project policy-pack and Airflow-profile precedence — test configured project pack, platform pack override, platform profile override, and omitted platform profile.
- Baseline report pruned but finding rows retained — test a no-new-findings gate using fingerprint-only `BaselineInput`.
- Mixed suppression provenance and expiry boundaries — test repository-local suppression preservation, matching active operational suppression, and expired operational suppression.
- Incomplete results where operational suppression resolves evaluation errors versus unrelated fatal issues — test both completeness outcomes and ensure incomplete scans cannot succeed.
- Cancellation or attempt reclamation while application execution is in flight — retain cancellation and stale-attempt regression checks around report ingestion and completion.

---

### Task 1: Characterize canonical runner report behavior

**Files:**
- Modify: `tests/test_platform.py` (runner integration and report assertions around the runner cases)
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: current `platform.runner.execute_scan`, application `execute_scan`, `ScanOptions`, `BaselineInput`, `Suppression`, existing fixture helpers.
- Produces: passing characterization tests proving canonical application/runner report parity and pinning current runner persistence/outcome behavior before orchestration changes.

- [ ] **Step 1: Add a deterministic golden parity test**

Run the platform runner against a deterministic fixture with a configured pack. Independently execute the application workflow for the same repository/configuration. Compare canonical report fields after removing only run timestamps/IDs and platform-only metadata; assert finding identities, completeness, gate result, and result fingerprint are equal.

- [ ] **Step 2: Run the parity test against the existing runner**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'runner_application_report_parity' -x --tb=short`
Expected: PASS before runner orchestration changes. If current results differ, document the specific field and resolve whether it is intended platform metadata or an existing parity defect before proceeding.

- [ ] **Step 3: Pin the retained baseline and suppression inputs**

Extend/add test cases proving that the comparison fixture exercises a complete report baseline, the fingerprint-only path used after retention pruning, an active suppression, an expired suppression, and a repository-local suppression with provenance. Reuse existing lifecycle tests where they already assert the behavior; do not duplicate equivalent tests without adding the app/runner boundary assertion.

- [ ] **Step 4: Run the focused characterization set**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'runner or suppression or baseline' -x --tb=short`
Expected: PASS with old runner implementation; output records pre-refactor behavior for the tests in scope.

---

### Task 2: Adapt platform rows and delegate execution

**Files:**
- Modify: `src/conformdag/platform/runner.py`
- Modify only if a missing transport-neutral input is identified: `src/conformdag/application/scan.py` and `src/conformdag/application/__init__.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: `execute_scan(options, configuration, *, baseline, operational_suppressions, parse_cache) -> ScanExecutionResult`; `eligible_baseline`; `SuppressionRow`; typed scan state.
- Produces: a runner that constructs canonical application inputs, invokes the application workflow once, persists `ScanExecutionResult.report`, and retains existing transition/exit behavior.

- [ ] **Step 1: Test conversion of platform suppressions and baselines at the workflow seam**

Use a spy around the real application `execute_scan` call to assert that only unexpired suppression rows become canonical `Suppression` values with reason, owner, and timestamps intact; an eligible retained report becomes `BaselineInput(report=...)`; and an eligible artifact-pruned baseline becomes `BaselineInput(fingerprints=...)`. Assert ineligible/missing baselines become `None`.

- [ ] **Step 2: Run the seam tests and confirm they fail for the missing delegation path**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'runner_passes_application_inputs' -x --tb=short`
Expected: FAIL because the current runner does not call the application workflow with canonical baseline/suppression inputs.

- [ ] **Step 3: Replace duplicated orchestration with the application call**

In `platform.runner`, retain claimed scan and repository loading, effective configuration resolution, parse-cache construction, baseline and active suppression SQL reads/conversions, logging, cancellation read, `_ingest`, and fenced transitions. Call application `execute_scan` once with `ScanOptions(repository_root)`, the resolved configuration, the canonical `BaselineInput`, canonical active `Suppression` sequence, and worker parse cache. Remove runner-owned direct `scan_repository`, platform suppression transformation, `normalize_report`, policy-pack reload, and `evaluate_pack_gates` logic/imports.

- [ ] **Step 4: Preserve incomplete and exception outcomes using the application result**

For incomplete `result.report`, keep the existing fresh cancellation check, ingest report, transition to `FAILED` with `_incomplete_error`, and return exit code 1. For complete results, keep the cancellation check, ingest report including the application's gate result, and transition to `SUCCEEDED` with the exact attempt. Preserve the existing failure handling for configuration/application exceptions and do not classify a failed gate as an incomplete scan.

- [ ] **Step 5: Run parity and runner tests**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'runner or suppression or baseline' -x --tb=short`
Expected: PASS; golden parity and database assertions match Task 1's captured behavior.

---

### Task 3: Verify lifecycle and full compatibility gates

**Files:**
- Modify only if tests expose a required adapter correction: `src/conformdag/platform/runner.py`, `src/conformdag/application/scan.py`
- Test: `tests/test_platform.py`, `tests/application/test_scan.py` only for an application boundary regression

**Interfaces:**
- Consumes: delegated runner and the unchanged worker claim/heartbeat/cancel/retry path.
- Produces: regression evidence for one application execution path, report persistence parity, incomplete failure behavior, and cancellation/attempt fencing.

- [ ] **Step 1: Exercise both suppression completeness branches**

Assert that an active operational suppression can recover completeness only when it resolves the relevant evaluation errors, while unrelated fatal parse/provider/runtime issues remain incomplete. Assert that an expired suppression is not passed/applied and the scan remains failed/incomplete when the underlying report is incomplete.

- [ ] **Step 2: Exercise gate and baseline outcomes end-to-end**

Assert a complete report receives the application-produced gate result for no baseline, report baseline, and retained-fingerprint baseline; a failing gate remains a succeeded complete scan with `gate_result.passed == false`; an incomplete report has no successful terminal transition.

- [ ] **Step 3: Exercise cancellation and stale-attempt fencing after delegation**

Use the existing cancellation-during-run and stale-attempt tests plus a runner integration case where cancellation or a changed attempt occurs while application execution is paused. Assert no late result overwrites the cancelled/reclaimed scan and no stale attempt ingests findings or report data.

- [ ] **Step 4: Run focused application, worker, and platform tests**

Run: `mise exec -- uv run pytest tests/application/test_scan.py tests/test_platform.py -k 'scan or runner or worker or suppression or baseline or gate or cancel or attempt' -x --tb=short`
Expected: PASS; also run the unfiltered two files if the selected expression omits any direct runner coverage.

- [ ] **Step 5: Run repository verification gates**

Run: `mise run check`
Expected: all format, lint, type, test, policy-pack, and inventory gates pass.

Run: `mise run test:coverage && mise run schema --check && git diff --check`
Expected: coverage meets the configured 90% threshold; schemas are current; no whitespace errors.

Run configured Postgres concurrency gate if available; otherwise record that the verification was not configured and retain SQLite cancellation/stale-attempt evidence without presenting it as PostgreSQL evidence.

---

### Task 4: Independent review and PR handoff

**Files:**
- Modify: `docs/consolidation/progress.md` only after independent review accepts the verified implementation head
- Test: no new behavior; rerun `git diff --check` after ledger-only evidence update

**Interfaces:**
- Consumes: implementation branch, C10 design, this plan, full local verification, PR CI.
- Produces: independently reviewed C10 implementation PR, with the ledger moved from `planned` to `review` only after the exact reviewed head and its CI are verified.

- [ ] **Step 1: Request a read-only independent review**

Supply the reviewer the base/head SHA, spec, plan, parity evidence, and verification output. Require a trace of every former runner responsibility to one owner; check that runner no longer directly scans, normalizes, applies suppressions, or evaluates gates; check conversion completeness, baseline retention path, incomplete report handling, cancellation, and exact-attempt fencing. Record all behavior deliberately declined to judge.

- [ ] **Step 2: Resolve review findings and re-verify**

Fix verified Critical/Important findings, rerun affected tests and full required local gates, push the corrected head, and obtain a reviewer re-review of that exact head. Leave any accepted Minor observations documented with a technical rationale.

- [ ] **Step 3: Open the implementation PR without merging**

Commit product changes with `refactor: delegate platform scans to application`, push the feature branch, open a PR against `main`, and verify CI against its exact head. Do not merge the PR.

- [ ] **Step 4: Record C10 review evidence**

Only after review acceptance and matching-head CI, update the C10 row in `docs/consolidation/progress.md` to `review` with PR, reviewed head, focused/full test counts, coverage, schema, PostgreSQL evidence or explicit unavailability, and review disposition. Commit and push this documentation-only update, then verify the resulting final PR head and CI; leave it open and unmerged.
