# Final P1 Fix Report

## Status

All four blocking final findings are fixed. The implementation, focused regressions,
and this report are intended to be committed together in one conventional commit:
`fix: close final P1 blocking findings`.

No push, merge, PR, release, agent dispatch, or opencode configuration change was
performed. The pre-existing untracked `opencode.json` was left untouched.

## Source Evidence Read

- `docs/superpowers/specs/2026-09-05-p1-foundation-design.md`
- `.superpowers/sdd/2026-09-05-p1-foundation/progress.md` (ledger)
- `.superpowers/sdd/2026-09-05-p1-foundation/task-20-brief.md`
- `.superpowers/sdd/2026-09-05-p1-foundation/task-20-report.md`
- `.superpowers/sdd/2026-09-05-p1-foundation/review-7f7a5d4..69969e6.diff` (all 11,419 lines)
- `.superpowers/sdd/2026-09-05-p1-foundation/global-constraints.md`

## Blocking Findings Fixed

### 1. Org-pack registry mismatch

`policies/pack.yaml` now references the existing registered `sensitive-logging`
check for `AIR-SEM-003`; no evaluator or alias was added.

Real command:

```text
mise exec -- uv run conformdag doctor
```

Result:

```text
PASS config: conformdag.yaml parses
PASS pack: conformdag-default 0.1.0 (14 policies)
PASS registry: every deterministic check is registered
PASS provenance: all policy provenance resolves
PASS gates: quality gates are well-formed
PASS docker: docker binary found
WARN platform-dsn: CONFORMDAG_PLATFORM_DSN is not set; platform reachability not checked
```

Exit status: 0.

The evaluator regression was updated to assert that the now-registered hybrid
deterministic check is evaluated rather than skipped.

### 2. CLI effective pack resolution

`scan.load_pack_for_scan()` is now the shared resolver used by both
`scan_repository()` and the CLI. It applies the same explicit/configured path
rules before gate evaluation, so CLI gates cannot silently fall back to
`policies/*.yaml`.

Regression: `test_scan_uses_configured_pack_for_gate_evaluation` creates a
configured pack and a conflicting implicit pack; the scan passes using the
configured pack's gate and gate ID.

### 3. Retained baseline fingerprints

Gate evaluation accepts retained baseline fingerprints separately from a full
baseline report. The platform runner queries `FindingRow.fingerprint` when
retention has pruned `ScanRow.report_json` and supplies those fingerprints to
`no-new-findings`.

Regression: `test_runner_uses_retained_baseline_findings_after_artifact_pruning`
uses `retention_keep=1`, confirms the baseline report is pruned while its finding
row remains, and confirms an unchanged later scan passes the baseline gate.

### 4. Dashboard policy save payload

The policy save route now validates the request through `PolicyUpsertRequest`.
`PackService.upsert_policy()` preserves existing required policy metadata,
rebuilds `configuration` from the dashboard's `check_kind` and `check_config`,
and validates the complete `Policy` before writing it.

Regression: `test_pack_policy_save_endpoint_persists_dashboard_check_fields`
sends the exact dashboard-shaped payload through the API and reloads the saved
pack to verify the title and `required-owner` configuration.

## TDD Evidence

### Red

Command:

```text
mise exec -- uv run pytest \
  tests/test_cli.py::test_doctor_accepts_the_real_org_pack \
  tests/test_cli.py::test_scan_uses_configured_pack_for_gate_evaluation \
  tests/test_platform.py::test_runner_uses_retained_baseline_findings_after_artifact_pruning \
  tests/test_platform.py::test_pack_policy_save_endpoint_persists_dashboard_check_fields \
  --tb=short
```

Observed result: 4 failures.

- Real doctor returned exit code 1 because `logging-calls` was unregistered.
- Configured-pack scan returned exit code 1 instead of the configured gate pass.
- Pruned-baseline scan reported one new finding instead of passing.
- Dashboard payload raised a Pydantic validation error for missing `ownership`,
  `enforcement`, and `configuration`.

### Green

The same four focused regressions passed after the production changes:

```text
4 passed, 1 warning in 3.38s
```

The affected CLI, platform, and gate suites then passed:

```text
115 passed, 1 warning in 12.11s
```

The warning is the existing Starlette/httpx `TestClient` deprecation warning.

## Required Gates

### `mise run check`

Exit status: 0.

```text
format-check: 118 files already formatted
lint: All checks passed!
typecheck: 0 errors, 0 warnings, 0 informations
test: 271 passed, 13 deselected, 1 warning
validate:packs: conformdag-default 0.1.0 (14 policies) valid
validate:packs: conformdag-community 0.1.0 (3 policies) valid
```

### `mise run test:coverage`

Exit status: 0.

```text
271 passed, 13 deselected
Required test coverage of 90% reached. Total coverage: 90.98%
```

## Changed Files

- `policies/pack.yaml`
- `src/conformdag/scan.py`
- `src/conformdag/cli.py`
- `src/conformdag/gates.py`
- `src/conformdag/platform/runner.py`
- `src/conformdag/platform/packs.py`
- `src/conformdag/platform/app.py`
- `tests/test_cli.py`
- `tests/test_evaluator.py`
- `tests/test_platform.py`
- `.superpowers/sdd/2026-09-05-p1-foundation/final-fix-report.md`

## Concerns and Scope Boundaries

- The existing Starlette/httpx deprecation warning remains.
- `doctor` reports the expected platform DSN warning because
  `CONFORMDAG_PLATFORM_DSN` was unset during verification.
- Runtime-marked Docker tests were not run by the required default gates.
- The final review's deferred Minor baseline status validation was not expanded.
