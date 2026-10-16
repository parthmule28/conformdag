# C20 — Baseline and Suppression Semantics Implementation Plan

> **For future agentic workers:** Use `superpowers:executing-plans` and work sequentially, one task at a time. Do not delegate to subagents. This plan is Stage B material only; implementation must wait until the Stage A documentation PR is merged and the user explicitly authorizes Stage B.

**Goal:** Introduce one immutable, layer-neutral Baseline while preserving current gate, suppression, CLI, platform, fingerprint, and compatibility behavior.

**Architecture:** `src/conformdag/baselines.py` owns the immutable domain value and constructors so core gates and application code can depend inward without a core-to-application import. Application and platform boundaries resolve eligibility and translate the legacy `BaselineInput` adapter; one final suppressed report continues to feed normalization and gate evaluation.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest, mise-managed Ruff and Pyright.

**Spec:** [C20 design](../specs/2026-10-17-c20-baseline-suppression-design.md)

## Global Constraints

- Do not begin Stage B before Stage A merges and the user explicitly authorizes implementation.
- Own `Baseline` in `src/conformdag/baselines.py`; do not import application code from core.
- Preserve `BaselineInput` at both `conformdag.application` and `conformdag.application.scan` import paths, with `report` and `fingerprints` fields through C30.
- Preserve legacy gate positional/keyword forms through C30; if both legacy report and fingerprint sources are given, the report wins.
- Preserve `None` (no baseline) versus an eligible empty `Baseline(frozenset())`, including when an eligible report artifact is pruned and no finding rows remain.
- Preserve current same-repository/succeeded/complete eligibility and application rejection of incomplete or dual-form `BaselineInput`.
- Apply operational suppressions after core/local suppression and before normalization, gates, and outcome classification.
- Do not change C19 fingerprint algorithms/values, the frozen C18 digest, report/schema JSON, database schema, retention, migrations, frontend logic, or the progress ledger.
- Use mise tasks and focused tests; no parallel implementation tasks or subagents.

## Review Focus

1. Both `BaselineInput` paths resolve to a type with the exact ordered fields/defaults; test package and defining-module imports.
2. A legacy report and fingerprint set supplied together to a gate select the report, while `execute_scan` continues rejecting a dual-form `BaselineInput`; test each boundary separately.
3. Missing/ineligible baselines remain `None`; an eligible empty baseline remains a Baseline after report pruning with zero `FindingRow` rows; test resolution as well as gate result.
4. Report-backed baselines include suppressed historical findings, while current suppressed findings remain outside blocking gate inputs; test both sides.
5. Expired/unmatched operational suppressions remain inapplicable and local provenance wins when both suppression layers match; test exact expiry and provenance.

---

## Task 1: Characterize current compatibility and gate semantics

**Files:**

- Modify: `tests/test_gates.py`
- Modify: `tests/application/test_scan.py`
- Keep unchanged: production source

**Interfaces:**

- Consumes: current `BaselineInput`, `evaluate_gate`, `evaluate_pack_gates`, and `execute_scan` APIs.
- Produces: regression tests that pin the legacy contracts before introducing the new value.

- [ ] **Step 1: Add the gate report-wins characterization test.** In `tests/test_gates.py`, pass a report containing fingerprint `known` together with a legacy fingerprint set containing only `other`; assert the report controls `no-new-findings`. Cover both the positional report plus `baseline_fingerprints=` form and the `baseline_report=` keyword form.

- [ ] **Step 2: Add the BaselineInput import/field characterization test.** Assert `conformdag.application.BaselineInput is conformdag.application.scan.BaselineInput`; assert dataclass field names and order are exactly `["report", "fingerprints"]`, both defaults are `None`, and the zero-argument form remains valid.

- [ ] **Step 3: Run the characterization tests.**

Run: `mise exec -- uv run pytest tests/test_gates.py tests/application/test_scan.py -k 'report_wins or baseline_input_defaults or two_baseline_forms' -x --tb=short`
Expected: PASS against the current implementation; the tests describe behavior that later tasks must retain.

- [ ] **Step 4: Commit the characterization tests.** Use commit message `test: characterize C20 baseline compatibility`.

## Task 2: Add the immutable root-level Baseline

**Files:**

- Create: `src/conformdag/baselines.py`
- Create: `tests/test_baselines.py`
- Modify: no application or gate modules in this task

**Interfaces:**

- Consumes: `ScanReport` and `Iterable[str]` from existing core types/standard library.
- Produces:
  - `Baseline(fingerprints: frozenset[str])`
  - `baseline_from_report(report: ScanReport) -> Baseline`
  - `baseline_from_fingerprints(fingerprints: Iterable[str]) -> Baseline`

- [ ] **Step 1: Write the value tests first.** Add:
  - `test_baseline_is_frozen_and_uses_frozenset`: mutation of the value raises `FrozenInstanceError`.
  - `test_baseline_from_report_includes_all_findings_including_suppressed`: output equals every report finding fingerprint, including a suppressed finding.
  - `test_baseline_from_fingerprints_snapshots_iterable`: consume a generator and prove later source mutation cannot affect the result.
  - `test_empty_baseline_is_a_value_distinct_from_none`: factory returns a Baseline containing `frozenset()`, not `None`.

- [ ] **Step 2: Run the new tests to verify the intended red.**

Run: `mise exec -- uv run pytest tests/test_baselines.py -x --tb=short`
Expected: FAIL because `conformdag.baselines` and its public names do not yet exist.

- [ ] **Step 3: Implement only the value and constructors in `src/conformdag/baselines.py`.** Import the core `ScanReport` model; snapshot fingerprints into a frozenset. Do not import from `conformdag.application`, add format validation, or redefine incomplete-report/eligibility checks.

- [ ] **Step 4: Rerun the focused tests.**

Run: `mise exec -- uv run pytest tests/test_baselines.py -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit.** Use `feat: add canonical baseline value`.

## Task 3: Add the canonical gate argument and legacy adapter

**Files:**

- Modify: `src/conformdag/gates.py`
- Modify: `tests/test_gates.py`

**Interfaces:**

- Consumes: `Baseline` and constructors from `conformdag.baselines`.
- Produces: `evaluate_gate` and `evaluate_pack_gates` accepting a canonical Baseline while preserving legacy positional `ScanReport`, `baseline_report=`, and `baseline_fingerprints=` calls.

- [ ] **Step 1: Add failing tests for canonical gate inputs.** Verify canonical report-equivalent and fingerprint-equivalent Baselines produce identical results; verify `None` and an empty Baseline each use an empty comparison set.

- [ ] **Step 2: Add legacy compatibility cases.** Verify the third positional `ScanReport`, `baseline_report=`, and `baseline_fingerprints=` continue to work; when both legacy sources are supplied, the report wins even if the fingerprint set would produce the opposite result. Verify the rule for both gate helpers. Verify a canonical Baseline mixed with legacy sources raises `ValueError`.

- [ ] **Step 3: Run the gate tests to verify red for the new canonical API.**

Run: `mise exec -- uv run pytest tests/test_gates.py -x --tb=short`
Expected: new canonical-call tests fail before the adapter is implemented; pre-existing gate behavior remains otherwise unchanged.

- [ ] **Step 4: Implement one baseline resolver in `gates.py`.** Import the Baseline from the root-level module. Route both helpers through the resolver. Keep the report-wins rule limited to the legacy report/fingerprint pair and preserve the old names and positional form through C30.

- [ ] **Step 5: Run gate and Baseline tests.**

Run: `mise exec -- uv run pytest tests/test_baselines.py tests/test_gates.py -x --tb=short`
Expected: PASS.

- [ ] **Step 6: Commit.** Use `refactor: adapt gates to canonical baseline`.

## Task 4: Migrate application and CLI while retaining BaselineInput

**Files:**

- Modify: `src/conformdag/application/scan.py`
- Modify: `src/conformdag/application/__init__.py` only if needed to preserve the facade
- Modify: `src/conformdag/cli.py`
- Modify: `tests/application/test_scan.py`
- Modify: `tests/test_cli.py`

**Interfaces:**

- Consumes: root-level Baseline constructors and gate canonical API.
- Produces: application internals use Baseline; the legacy `BaselineInput` type and both import paths/fields remain supported through C30.

- [ ] **Step 1: Add failing application migration tests.** Cover conversion of either legacy `BaselineInput` form to the equivalent Baseline before gate evaluation; keep `BaselineInput()` as absence; preserve rejection of incomplete reports and both input fields set before the core scan call.

- [ ] **Step 2: Add import and constructor regression tests.** Exercise imports from `conformdag.application` and `conformdag.application.scan`, constructor keywords/defaults, field order, and equality. Assert both imports identify the same compatibility type.

- [ ] **Step 3: Add/retain CLI tests.** The complete JSON report loaded by `--baseline` becomes a report-derived Baseline; incomplete JSON retains the existing user-facing error mapping. The CLI must still call the single application scan path.

- [ ] **Step 4: Run focused tests to verify red for the canonical application path.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py tests/test_cli.py -k 'baseline or delegates_to_application' -x --tb=short`
Expected: the new canonical-path assertions fail before migration; the legacy compatibility tests remain valid.

- [ ] **Step 5: Migrate the application boundary and CLI.** Convert legacy inputs in application code, retain `BaselineInput` with its exact fields and facade exports, and pass one canonical Baseline (or `None`) to gates. Keep suppression/normalization ordering and the one `scan_repository` invocation unchanged.

- [ ] **Step 6: Rerun focused application and CLI tests.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py tests/test_cli.py -x --tb=short`
Expected: PASS.

- [ ] **Step 7: Commit.** Use `refactor: migrate application baseline inputs`.

## Task 5: Migrate platform resolution and prove pruning/eligibility parity

**Files:**

- Modify: `src/conformdag/platform/runner.py`
- Modify: `tests/test_platform.py`
- No database model, migration, or schema changes

**Interfaces:**

- Consumes: application Baseline resolution and existing `eligible_baseline`.
- Produces: eligible report-backed and retained-fingerprint baselines resolve to the same Baseline value; missing/ineligible baselines resolve to `None`.

- [ ] **Step 1: Add a failing empty-pruned-baseline test.** Create an eligible succeeded/complete scan with `report_json is None` and zero `FindingRow` values. Assert the runner supplies an empty Baseline, not `None`, and the resulting gate behavior matches an eligible report-backed empty baseline.

- [ ] **Step 2: Add/retain eligibility and non-empty parity tests.** Cover same-repository ownership, succeeded and complete status; reject missing, cross-repository, queued, running, failed, cancelled, or incomplete baselines. Compare report-backed and artifact-pruned non-empty gate results.

- [ ] **Step 3: Add/retain suppression integration assertions.** Confirm active exact-match operational suppressions are applied before gates, existing repository suppression provenance is preserved, expired/unmatched suppressions do not affect the result, and the final report remains application/platform parity.

- [ ] **Step 4: Run focused platform tests to verify red for any missing canonical resolution.**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'baseline or suppression_before_gate or report_parity' -x --tb=short`
Expected: the new empty-pruned canonical-value assertion fails before runner migration; existing eligibility and suppression contracts remain characterized.

- [ ] **Step 5: Migrate the runner.** Keep `eligible_baseline` authoritative. Convert a persisted report via `baseline_from_report`; after pruning, convert retained row fingerprints via `baseline_from_fingerprints`, including the zero-row case. Preserve `None` for absent/ineligible baselines. Do not change retention persistence or aggregate/API semantics.

- [ ] **Step 6: Rerun platform and suppression tests.**

Run: `mise exec -- uv run pytest tests/test_platform.py tests/reporting/test_suppressions_contract.py -m 'not runtime' -x --tb=short`
Expected: PASS, including report/pruned parity and suppression timing.

- [ ] **Step 7: Commit.** Use `refactor: unify platform baseline resolution`.

## Task 6: Full verification and implementation handoff

**Files:**

- Inspect all C20 implementation changes.
- Do not change the progress ledger to accepted.
- Open an unmerged implementation PR only after explicit authorization for Stage B.

**Interfaces:**

- Consumes: completed tasks 1–5.
- Produces: verified implementation evidence and an unmerged PR ready for independent review.

- [ ] **Step 1: Run the focused compatibility and round-trip set.**

Run: `mise exec -- uv run pytest tests/test_baselines.py tests/test_gates.py tests/application/test_scan.py tests/test_cli.py tests/test_platform.py tests/reporting/test_suppressions_contract.py tests/test_roundtrip.py -m 'not runtime' -x --tb=short`
Expected: PASS.

- [ ] **Step 2: Run the repository verification tasks.**

Run: `mise run check`
Expected: format check, Ruff, Pyright with 0 errors, fast suite, pack validation, and dependency inventory all pass.

Run: `mise run test:coverage`
Expected: pass the repository's configured 90% minimum.

Run: `mise run schema`
Expected: checked-in schemas are unchanged and valid.

- [ ] **Step 3: Inspect compatibility and scope.** Confirm both legacy BaselineInput import paths and fields remain; report-wins is tested; no-baseline and empty-eligible-baseline remain distinct after pruning; the C18 digest is unchanged; no fingerprint, report/schema, migration, retention, or frontend change occurred.

- [ ] **Step 4: Inspect Git diff and commit scope.** Run `git diff --check`, `git status --short`, and inspect all source/test diffs. Keep the progress ledger out of the acceptance state until post-merge CI and a separate acceptance step.

- [ ] **Step 5: Report exact verification evidence and known limitations.** Include test totals, coverage, Pyright, schema, round-trip, final head, and required GitHub CI. Leave the implementation PR open for independent review; do not merge.

## Stage A and Stage B handoff

Stage A consists only of the C20 design and this sequential plan as Markdown
under `docs/superpowers/`. Stage A does not implement or test production
changes and does not modify `docs/consolidation/progress.md`.

This plan describes future Stage B only. The executor must wait for the Stage A
documentation PR to merge and for explicit user authorization. Then execute
the tasks above in order, with a test-first red/green cycle and a reviewable
commit at each task boundary. Do not merge the implementation PR.
