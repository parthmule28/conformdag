# Final Consolidated Fix Wave — Whole-Branch Review Findings

- Date: 2026-09-17
- Branch: `feat/policy-management`
- Base: HEAD `46c6824` (reviewed tree, clean except the pre-existing untracked `.serena/` and the ledger update recording the final review)
- Findings fixed: final-review.md Important I-1 and Same-Wave Minor M-1. No Critical findings existed.
- Method: TDD — focused failing regressions written and observed red at `46c6824`, then minimal implementation, then green; no subagents, no amend/push/merge/publish.
- Scope discipline: no schema changes, no OpenCode configuration changes, no unrelated refactoring.

## Finding 1 (Important I-1) — Pack mutations validate only the single policy

**Defect.** `PackService.upsert_policy` validated the reconstructed `Policy`
with `Policy.model_validate` but never re-validated the reconstructed
`PolicyPack`. A dashboard mutation could persist, e.g., an
`enforcement.deterministic_checks` entry that is not in `CHECK_EVALUATORS`
(the registry `_evaluator_for_policy` resolves evaluators from that field).
The pack on disk then became unrunnable: subsequent scans fail closed, reads
surface errors, and recovery mutations were blocked because `upsert_policy`
itself starts with `load_policy_pack()`, which now rejects the persisted pack.

**Fix.** `src/conformdag/platform/packs.py` (`upsert_policy`): after splicing
the validated policy into the pack and before `_write_pack()`, run the
authoritative `validate_policy_pack(pack)` (imported from
`conformdag.policy` — the same function `load_policy_pack()` uses) and raise
`PackError("; ".join(issues))` when it reports anything. This validates the
complete reconstructed pack — evaluator references and quality-gate data —
inside the existing lock and before any byte is written.

**Error path.** `PackError` is a `ValueError`; the existing
`_pack_upsert_policy` handler maps it to HTTP 422 (same path as the Task 1
fix-round malformed-pack mapping). No route or handler changes were needed.

## Finding 2 (Minor M-1) — Incomplete CLI reports embedded a passing gate

**Defect.** The CLI `scan` command evaluated `evaluate_pack_gates(...)` and
embedded the result unconditionally. An incomplete report (e.g., one fatal
parse issue, zero blocking findings) could therefore carry
`gate_result.passed == true` alongside `complete: false`.

**Fix.** `src/conformdag/cli.py` (`scan`): evaluate gates only when
`report.complete`; otherwise leave `gate_result` as `None` so the emitted
artifact cannot claim a passing gate. Exit behavior is unchanged: fatal
issues raise exit 3 before the gate/legacy exit-1 branch is reached, so the
documented exit-3 behavior is preserved (proven by the regression).

**Not touched on purpose.** The platform runner already returns before gate
evaluation for incomplete reports (`runner.py` marks them failed first), so
the CLI was the only affected consumer.

## Changed files

| File | Change |
|---|---|
| `src/conformdag/platform/packs.py` | `upsert_policy` runs `validate_policy_pack(pack)` after splice, before `_write_pack`; raises `PackError` on issues (+1 import) |
| `src/conformdag/cli.py` | `scan` evaluates gates only `if report.complete` (1 line) |
| `tests/test_platform.py` | `test_upsert_policy_rejects_unknown_evaluator_and_keeps_pack_usable` (service-level mutation regression: rejection, unchanged bytes, pack still loadable, recovery mutation succeeds); `test_policy_upsert_endpoint_rejects_unknown_evaluator_with_422` (API 422 + unchanged bytes + pack still loadable) |
| `tests/test_cli.py` | `test_scan_incomplete_report_does_not_embed_gate_result` (incomplete report + passing-would-be gate: exit 3, `complete is False`, `gate_result is None`) |
| `.superpowers/sdd/2026-09-16-p1-remediation/final-fix-report.md` | This report |
| `.superpowers/sdd/2026-09-16-p1-remediation/acceptance-report.md` | Step 3 review outcome + fix-wave record; final verdict remains pending scoped re-review |
| `.superpowers/sdd/2026-09-16-p1-remediation/progress.md` | Ledger entries for the fix wave (includes the pre-existing uncommitted final-review ruling lines) |

## TDD evidence

### RED (at `46c6824`, before implementation)

Command:

```
mise exec -- uv run pytest \
  tests/test_platform.py::test_upsert_policy_rejects_unknown_evaluator_and_keeps_pack_usable \
  tests/test_platform.py::test_policy_upsert_endpoint_rejects_unknown_evaluator_with_422 \
  tests/test_cli.py::test_scan_incomplete_report_does_not_embed_gate_result \
  --tb=short -q
```

Observed (all three failed for the expected reason — defect present, not a
test error):

```
FAILED tests/test_platform.py::test_upsert_policy_rejects_unknown_evaluator_and_keeps_pack_usable \
  — Failed: DID NOT RAISE PackError          (invalid evaluator was persisted)
FAILED tests/test_platform.py::test_policy_upsert_endpoint_rejects_unknown_evaluator_with_422 \
  — assert 200 == 422                        (endpoint saved the broken policy)
FAILED tests/test_cli.py::test_scan_incomplete_report_does_not_embed_gate_result \
  — assert {'gate_id': 'default', 'passed': True, ...} is None
3 failed
```

### GREEN (after the minimal implementation)

Same command, observed:

```
3 passed, 1 warning in 0.94s
```

### Focused regression surfaces (post-fix)

| Command | Result |
|---|---|
| `mise exec -- uv run pytest tests/test_cli.py -k "gate or incomplete or baseline or scan" --tb=short -q` | `21 passed, 21 deselected` — exit 0 |
| `mise exec -- uv run pytest tests/test_platform.py -k "upsert or pack or policy or malformed or concurrent or temp or validation" --tb=short -q` | `30 passed, 77 deselected` — exit 0 |
| `mise exec -- uv run pytest tests/test_gates.py tests/test_scan.py tests/test_policy.py --tb=short -q` | `39 passed` — exit 0 |

## Full verification surfaces (all at the fix commit, mise-managed env)

| Gate | Command | Result |
|---|---|---|
| Full local gate | `mise run check` | **exit 0** — format-check OK; lint OK; pyright strict `0 errors, 0 warnings, 0 informations`; `342 passed, 13 deselected, 1 warning in 31.14s` (339 prior + 3 new); `validate:packs` OK |
| Coverage | `mise run test:coverage` | **exit 0** — `TOTAL 3468 198 986 160 92%`; `Required test coverage of 90% reached. Total coverage: 91.56%`; `342 passed, 13 deselected` |
| Schemas | `mise run schema --check` | **exit 0** — no diffs (no model changes) |
| Runtime suite | `mise run test:runtime` | **exit 0** — `13 passed, 342 deselected, 1 warning in 0.70s` (Docker-runner contract tests, per the standing honesty note; no live Airflow containers) |
| Frontend build | `mise run ui-build` | **exit 0** — `tsc -b && vite build`, 74.60 kB gzip bundle emitted to `src/conformdag/platform/static/` |

Coverage-artifact check after all test processes: `find . -maxdepth 1 -name ".coverage*"`
→ `.coverage` only (gitignored); no `.coverage.cachyos*` artifacts. Post-run
`git status --porcelain`: only this wave's intended files plus untracked `.serena/`.

## Self-review

1. **Authoritative boundary restored.** The mutation path now runs the exact
   validation `load_policy_pack()` runs on every read (`validate_policy_pack`
   covers both unknown deterministic checks and quality-gate authoring
   errors). There is still only one validation authority; no second pipeline
   was created.
2. **No write on rejection.** The pack-level validation happens strictly
   before `_write_pack()` and inside the per-instance lock, so a rejected
   mutation cannot touch disk (proven byte-for-byte by both new platform
   tests) and cannot wedge the lock or the pack (proven by the recovery
   mutation in the service test).
3. **Fail-closed and exit semantics preserved.** CLI: fatal issues still exit
   3 before any gate-based exit-1 branch; incomplete reports now carry
   `gate_result: null`; complete reports are bit-for-bit unchanged in
   behavior. The runner's earlier early-return for incomplete reports was
   already correct and was not modified.
4. **Atomicity/locking untouched.** `_write_pack`, unique temp files, and the
   read-modify-write lock are unchanged; the 30-node platform focused run
   (concurrency, temp-file, malformed-pack nodes) stays green.
5. **Test quality.** Each regression fails at HEAD for the exact defect
   (observed), asserts real behavior (HTTP status, file bytes, report JSON),
   and the service test additionally proves recovery is possible — the
   operational harm the review called out.

## Concerns

- `delete_policy` still does not re-validate the pack after removal; deleting
  a policy referenced by an `always-block` gate can produce a pack that
  `load_policy_pack()` rejects. This was outside the review's scoped findings
  (I-1 names `upsert_policy` only) and was deliberately not changed in this
  wave to avoid scope creep; it deserves its own small fix wave.
- The CLI now skips gate evaluation for incomplete reports, so downstream
  consumers that previously read an embedded (misleadingly passing) gate from
  incomplete artifacts will see `null` — the intended fail-closed contract.
- Runtime suite remains the Docker-runner contract tests (no live Airflow
  containers), unchanged from the acceptance evidence; real-Postgres runtime
  verification is still a deferred item from Task 3.
- Scoped re-review of this wave is still pending; the acceptance verdict must
  not be finalized before it returns.
