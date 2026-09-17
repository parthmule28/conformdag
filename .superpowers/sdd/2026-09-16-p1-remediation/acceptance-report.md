# P1 Remediation Acceptance Report

- Date: 2026-09-17
- Branch: `feat/policy-management`
- Remediation merge base: `849c840` (plan commit)
- HEAD at acceptance: `abbed9c` (`fix: make unresolved evaluations fail closed across consumers`)
- Working tree: clean except the pre-existing untracked `.serena/`
- Requirements consumed: `.superpowers/sdd/2026-09-05-p1-foundation/p1-readiness-audit.md`,
  `docs/superpowers/specs/2026-09-16-p1-remediation-design.md`,
  `docs/superpowers/plans/2026-09-16-p1-remediation.md`,
  task briefs/reports/reviews for Tasks 1-7, `.superpowers/sdd/2026-09-16-p1-remediation/progress.md`.

## Step 1 — Requirement-to-Evidence Matrix

Every Critical and Important blocker from the readiness audit maps to passing,
re-run focused regression nodes. **No blocker was ruled out of scope**; the
audit's P2-scope list (Journey D UI, OpenAPI polish, semantic/BYOK config,
pagination/CORS/logging/Unicode deferrals) remains out of scope by the
remediation spec's explicit "Out Of Scope" section and was never an acceptance
requirement.

### Critical blockers

| # | Audit blocker | Remediation | Re-run evidence (all PASS) |
|---|---|---|---|
| C1 | Worker retry exhaustion rolled back; scans permanently running | Task 3 | `test_exhausted_abandoned_scan_is_committed_failed`, `test_worker_requeues_scan_when_runner_cannot_launch`, `test_timeout_at_attempt_budget_commits_failed`; every terminal write is a conditional `WHERE status='running'` UPDATE (`transition_running_scan`) |
| C2 | Compose workspace worker-only; startup silently ignores bad workspace | Task 4 | `test_compose_workspace_mounted_for_api_and_worker`, `test_invalid_configured_workspace_fails_app_startup`, `test_configured_workspace_env_var_fails_app_startup`, `test_configured_workspace_registers_packs_at_startup` |
| C3 | Unknown deterministic evaluator kinds skipped, not rejected | Task 1 | `test_load_policy_pack_rejects_unknown_deterministic_check`; entry-point set: CLI scan/validate-policies, `PackService.validate_rejects_unknown_check`, `test_workspace_registration_surfaces_unknown_check`, `test_validate_policy_pack_reports_unknown_check_and_unknown_gate` |
| C4 | Invalid gate references scan and pass | Task 1 | `test_load_policy_pack_rejects_unknown_gate_policy` + the same authoritative-boundary entry-point set (gate validation folded into `validate_policy_pack` inside `load_policy_pack()`) |
| C5 | Incomplete scans recorded as succeeded and usable as baselines | Task 2 | `test_runner_marks_incomplete_report_failed`, `test_baseline_eligibility_rejects_ineligible_scans[*]` (queued/running/failed/cancelled/incomplete), `test_runner_baseline_eligibility_requires_succeeded_and_complete`, CLI `test_baseline_eligibility_rejects_ineligible_scan`, `test_scan_rejects_incomplete_report_as_baseline` |
| C6 | Dashboard policy edits corrupt invariant/source metadata | Task 5 | `test_dashboard_policy_update_preserves_contract_metadata` (lossless merge from `existing.model_dump(mode="json")`; `invariant` never derived from `check_config`) |
| C7 | Auto-apply writes invalid Python; rescan completeness ignored; conflicting zero-width spans accepted | Task 6 | `test_apply_spans_rejects_distinct_zero_width_insertions_at_same_offset`, `test_incomplete_verification_never_applies`, `test_apply_verified_refuses_unparsable_content`, `test_owner_codemod_uses_repr_for_generated_literals`, `test_apply_quotes_generated_owner_literals_safely`, `test_patch_candidates_converts_distinct_insertions_at_same_offset_into_residuals` |

### Important blockers

| # | Audit blocker | Remediation | Re-run evidence (all PASS) |
|---|---|---|---|
| I1 | `always-block` ignores nonblocking semantic failures | Task 2 | `test_always_block_includes_nonblocking_semantic_failures`; fix-round regression `test_always_block_honors_suppressions` (suppressed listed findings never block) |
| I2 | Platform suppressions stored but never applied to worker scans | Task 2 | `test_runner_applies_platform_suppression_before_gate_evaluation` |
| I3 | Timeout/cancellation do not safely stop/retry; completion overwrites cancellation | Task 3 | `test_timeout_requeues_scan_with_attempts_left`, `test_cancellation_terminates_child_during_execution`, `test_execute_claimed_scan_kills_child_that_ignores_termination`, `test_runner_persistent_failure_after_cancel_keeps_cancelled_status`, `test_runner_completion_after_cancel_keeps_cancelled_status` |
| I4 | API/CLI baseline selection not same-repo/successful/complete | Task 2 | API `test_baseline_eligibility_rejects_ineligible_scans[*]`, runner eligibility, CLI eligibility, CLI incomplete-report rejection (all via shared `eligible_baseline()`) |
| I5 | Retention permits `keep=0`, pruning newest artifact | Task 3 | `test_retention_zero_is_rejected` (pydantic + worker env), `test_retention_target_scan_ids_protect_newest_with_zero_keep` (`max(keep, 1)` defense) |
| I6 | TaskFlow DAG identity alias-only; alias reuse crosses defaults | Task 7 (+ fix round) | `test_reused_dag_alias_uses_nearest_concrete_dag_defaults`, `test_operator_tasks_resolve_defaults_by_enclosing_context_line`, `test_explicit_operator_dag_binding_wins_over_enclosing_context` |
| I7 | Advertised mechanical fixes unsafe (TaskFlow retry, start dates, dynamic `datetime()`) | Task 7 (+ Task 6 repr) | `test_taskflow_retry_autofix_round_trip` (AUTOFIX classification + span + verify-by-rescan), `test_unresolved_taskflow_retries_do_not_mask_dag_defaults`, `test_missing_start_date_fails_the_dag`, `test_dynamic_datetime_start_date_does_not_crash`, `test_owner_codemod_uses_repr_for_generated_literals` |
| I8 | Startup migration execution races API/worker/runner | Task 4 | `test_runner_does_not_run_migrations` (runner subprocess provably migration-free; `initialize_session_factory` owns migrations at serve/worker/`baseline set` startup) |
| I9 | Pack edits share a temp filename and unlocked read-modify-write | Task 5 (+ fix round) | `test_concurrent_policy_updates_do_not_lose_changes` (per-instance `RLock` across load-modify-validate-write), `test_write_pack_uses_unique_same_directory_temp_files`, `test_write_pack_cleans_temp_when_temp_write_fails` |

### Task 7 fix-round hardening (ERROR fail-closed across consumers)

Unsuppressed `FindingStatus.ERROR` findings now make reports incomplete
(`EVALUATION_ERROR` fatal issue), exit CLI 3, mark platform scans `failed`,
become baseline-ineligible, count as blocking in gates, and surface in agent
triage as manual. Operator unresolved retry values no longer coerce to zero.
Re-run evidence (9 nodes, PASS):

```
tests/test_scan.py::test_scan_marks_unresolved_static_evaluation_incomplete
tests/test_cli.py::test_scan_exits_three_when_static_evaluation_is_unresolved
tests/test_agent.py::test_triage_surfaces_unresolved_evaluation_as_manual
tests/test_platform.py::test_runner_marks_unresolved_evaluation_failed
tests/test_gates.py::test_error_findings_block_like_failures
tests/test_check_pack.py::test_unresolved_operator_retries_do_not_silently_pass
tests/test_check_pack.py::test_explicit_operator_dag_binding_wins_over_enclosing_context
tests/test_check_pack.py::test_operator_tasks_resolve_defaults_by_enclosing_context_line
tests/test_analysis.py::test_operator_unresolved_kwargs_are_tracked_and_bindings_resolved
→ 9 passed
```

## Step 1 — Exact commands and observed outputs

All re-run at HEAD `abbed9c`, clean tree, mise-managed environment
(`uv`-synced with `--all-extras`). Format: command → tail of output → exit code.

| Task | Command | Result |
|---|---|---|
| 1 | `mise exec -- uv run pytest tests/test_policy.py -k "unknown_deterministic_check or unknown_gate_policy" --tb=short -q` | `2 passed, 12 deselected in 0.15s` — exit 0 |
| 1 | `mise exec -- uv run pytest tests/test_policy.py tests/test_cli.py tests/test_platform.py tests/test_gates.py -k "unknown_check or unknown_gate" --tb=short -q` | `7 passed, 166 deselected` — exit 0 |
| 1 (fix) | `mise exec -- uv run pytest tests/test_platform.py -k "malformed_pack" --tb=short -q` | `2 passed, 103 deselected` — exit 0 (mutation endpoints 422 on malformed packs) |
| 2 | `mise exec -- uv run pytest tests/test_gates.py tests/test_platform.py tests/test_cli.py -k "always_block or incomplete_report or baseline_eligibility or applies_platform_suppression" --tb=short -q` | `15 passed, 144 deselected` — exit 0 |
| 2 (fix) | `mise exec -- uv run pytest tests/test_gates.py::test_always_block_honors_suppressions --tb=short -q` | `1 passed` — exit 0 |
| 3 | `mise exec -- uv run pytest tests/test_platform.py -k "exhausted_abandoned or timeout_requeues or cancellation_terminates or retention_zero" --tb=short -q` | `4 passed, 101 deselected` — exit 0 |
| 4 | `mise exec -- uv run pytest tests/test_platform.py tests/test_runtime.py -k "runner_does_not_run_migrations or configured_workspace or compose_workspace" --tb=short -q` | `5 passed, 113 deselected` — exit 0 |
| 5 | `mise exec -- uv run pytest tests/test_platform.py -k "preserves_contract_metadata or concurrent_policy_updates or invalid_source_section" --tb=short -q` | `3 passed, 102 deselected` — exit 0 |
| 5 (fix) | `mise exec -- uv run pytest tests/test_platform.py -k "cleans_temp_when_temp_write_fails or unique_same_directory_temp or replace_failure or leaves_no_tmp or validation_failure" --tb=short -q` | `5 passed, 100 deselected` — exit 0 |
| 6 | `mise exec -- uv run pytest tests/test_fixing.py -k "zero_width or incomplete_verification or sharing_a_range or deduplicates_identical or uses_repr or quotes_generated or refuses_unparsable" --tb=short -q` | `8 passed, 38 deselected` — exit 0 |
| 6 (fix) | `mise exec -- uv run pytest tests/test_fixing.py -k "distinct_insertions_at_same_offset or sequentially_with_distinct_anchors or codemod_parse_failures" --tb=short -q` | `3 passed, 43 deselected` — exit 0 |
| 7 | `mise exec -- uv run pytest tests/test_analysis.py tests/test_check_pack.py tests/test_fixing.py -k "reused_dag_alias or unresolved_taskflow or missing_start_date or dynamic_datetime or taskflow_retry" --tb=short -q` | `6 passed, 65 deselected` — exit 0 |
| 7 (fix) | 9-node explicit selection (listed above) | `9 passed` — exit 0 |

## Step 2 — Complete verification

| Gate | Command | Result |
|---|---|---|
| Full local gate | `mise run check` | **exit 0** — format-check OK; lint OK; pyright strict `0 errors, 0 warnings, 0 informations`; `339 passed, 13 deselected, 1 warning in 31.15s`; `validate:packs` OK |
| Coverage | `mise run test:coverage` | **exit 0** — `TOTAL 3465 198 984 160 92%`; `Required test coverage of 90% reached. Total coverage: 91.55%`; `339 passed, 13 deselected` (baseline at audit time: 271 passed / 90.98%) |
| Schemas | `mise run schema --check` | **exit 0** — no diffs (no public Pydantic model changes in remediation) |
| Runtime | `mise run test:runtime` | **exit 0** — `13 passed, 339 deselected, 1 warning in 0.70s` |
| Frontend | `npm run build` (in `frontend/`) | **exit 0** — `tsc -b && vite build`: 75 modules transformed, built in 935ms, outputs emitted to `src/conformdag/platform/static/` |

Runtime-suite honesty note: Docker is available in this environment and
`mise run test:runtime` exits zero, but the 13 runtime-marked tests are the
project's Docker-runner **contract** tests (argument arrays, image manifests,
digest policy, structured failure protocols — `tests/test_runtime.py`); they do
not execute live Airflow containers. This is identical to the runtime evidence
accepted by Task 4. No runtime or frontend failure occurred or was worked
around.

### Coverage-artifact check

- Before: `ls .coverage*` → only the gitignored `.coverage` data file.
- After all test processes: `find . -maxdepth 1 -name ".coverage*"` → `.coverage` only.
- `.coverage.cachyos*` artifacts: **none remain** (none were generated at any point in the acceptance run).
- Post-run `git status --porcelain`: only the pre-existing untracked `.serena/`.

## Task commits (remediation merge base `849c840` → HEAD `abbed9c`)

| Task | Commits (in order) |
|---|---|
| 1 | `2aea0d9` fix: fail closed on invalid policy packs · `ce87f94` fix: return 422 for pack mutations on malformed packs (fix round 1) |
| 2 | `c7bda4c` fix: enforce complete scan and baseline semantics · `1a2a9d8` test: prove always-block honors suppressions (fix round 1) |
| 3 | `f51a4c5` fix: make worker scan transitions durable |
| 4 | `18ce2e8` fix: serialize platform startup and workspace loading |
| 5 | `a94e056` fix: preserve policy contracts on concurrent saves · `5f0afdf` fix: clean pack temp file when the temporary write fails (fix round 1) |
| 6 | `80110f4` fix: prevent unsafe verified patches · `bc57827` fix: make fix-engine spans dedup-only and apply findings sequentially (fix round 1) |
| 7 | `8b62798` fix: resolve TaskFlow context and fixability safely · `abbed9c` fix: make unresolved evaluations fail closed across consumers (fix round 1) |

## Recorded rulings and cost if wrong

1. **TaskFlow retry codemods (pre-Task-1 ruling).** Implement TaskFlow retry
   decorator codemods rather than downgrading the entire `retry-bounds` kind to
   manual, because operator retry fixes are already safely shipped and the
   finding payload promises mechanical replacement. **Cost if wrong:**
   additional AST span logic and regression surface in Task 7 (borne and
   verified by `test_taskflow_retry_autofix_round_trip`).
2. **Task 6 — Safe Fix Contract upheld over the shared-anchor merge.** Make
   `_merge_spans` dedup-only and move owner/tags legitimate insertions to
   distinct anchors (sequential per-finding application), with roundtrip
   coverage. **Cost if wrong:** codemod anchor changes may require additional
   regression work, but retaining the merge would ship an explicit
   safety-contract violation (80-case roundtrip gate and focused regressions
   confirm no regression).
3. **Task 7 — ERROR remains a finding status while consumers fail closed.**
   Preserve the brief's ERROR finding status while making ERROR an
   incomplete/non-successful evaluation across every consumer; same fail-closed
   treatment for unresolved operator retry values; explicit resolved `dag=`
   bindings take precedence over enclosing context; line linkage remains the
   fallback for implicit context. **Cost if wrong:** exit/report and
   default-resolution behavior changes are broader than the original file list
   (accepted: consumers embedding `conformdag scan` see exit 3 on dynamic
   retry values — the ruling's intent), but leaving these paths open violates
   the unconditional dynamic-value and TaskFlow-context guarantees.

## Deferred Minor findings (carried; none block P1 acceptance)

- Task 1 (3): doctor no longer aggregates provenance/gate rows after an
  initial pack-load failure (fail-closed intact); `PackService` reconstructs
  errors via `str(exc).split("; ")` rather than typed `exc.issues`; read-only
  malformed-pack policy listing still maps `PolicyValidationError` through the
  generic HTTP 500 handler (fail-closed).
- Task 2 (3, carried to Task 3 and **resolved there**): persistent-failure
  cancellation re-check, cancellation-vs-final-commit race, `_was_cancelled()`
  identity-map expiry — all three closed by Task 3's conditional transitions
  and fresh scalar SELECT. Review note (informational): CLI does not
  independently enumerate `running` baselines; unit/API coverage covers it.
- Task 3 (5): timeout cleanup grace can exceed the nominal deadline;
  zero/negative timeout pipe-drain edge case; cancel endpoint's reverse TOCTOU
  can overwrite a runner success; status-only claim transition lacks a
  claim-generation guard under stale-worker misconfiguration;
  cancellation/rowcount behavior needs real-Postgres runtime evidence.
- Task 4 (5): deployment docs overstate startup repository seeding; AGENTS.md
  still documents the old migration-owning `create_session_factory` contract;
  concurrent API/worker Alembic startup can race on fresh Postgres; Compose
  hard-codes the workspace filename; Compose test uses a CWD-relative path.
- Task 5 (3): `safe_path`/`source_version` cannot be explicitly cleared (null
  means preserve); raw thread exceptions observed indirectly in the concurrency
  test; unreachable `configuration` merge branch remains.
- Task 6 (3): proposed-only span conflicts can propagate from
  `_record_proposed_moves` (proposed moves are never applied);
  incomplete-verification residual dedup can retain an empty reason over the
  fatal scan reason; sequential re-anchoring can apply redundant identical
  cross-finding payloads twice when duplicate policies target one call.
- Task 7 (9): TaskFlow retry insertion/bare-decorator coverage; literal
  `retries=None` wording; mirrored analysis test helper; `default_args`
  start_date; line-based decorator targeting in pathological layouts; dynamic
  operator `execution_timeout` SET fixability loss (payload flips to ADD);
  platform suppressions cannot waive the fatal ERROR issue minted by scanning;
  TaskFlow decorator assignment constants unresolved; reused aliases for
  explicit `dag=` bindings statically ambiguous.

## Step 3 — Independent whole-branch review

**PENDING** — owned by the controller per the acceptance instruction; no
additional reviewer was dispatched. Review package scope when run:
`849c840..abbed9c` (12 commits) with the remediation spec, plan, both readiness
audits, all task reports/reviews, and the full diff. Any resulting
Critical/Important findings require one consolidated fix wave plus one scoped
re-review before this verdict is finalized.

## Spec acceptance criteria cross-check

1. Invalid evaluator kinds and gate references fail pack validation, cannot
   yield a passing scan — **met** (Task 1 evidence).
2. No incomplete, cancelled, queued, failed, or cross-repository scan acts as a
   successful baseline — **met** (Task 2 evidence).
3. Worker retry, timeout, cancellation, retention, Compose workspace, and
   migration behavior durable — **met** (Tasks 3-4 evidence; runtime suite
   green per the honesty note above).
4. Dashboard policy edits preserve valid policy metadata; concurrent writes do
   not corrupt or lose pack changes — **met** (Task 5 evidence).
5. `--apply` never writes incomplete/unparsable verification or conflicting
   insertion spans — **met** (Task 6 evidence).
6. TaskFlow effective configuration correct for nested DAGs, reused aliases,
   unresolved expressions, and supported autofix forms — **met** (Task 7
   evidence; nested-DAG resolution covered by existing suite plus the
   context-line guard).
7. `mise run check`, coverage ≥ 90%, schema check, Docker runtime tests pass —
   **met** (Step 2: 0/0/0/0/0 exits; 91.55%).

## Provisional decision

**P1 Ready — provisional.** All seven spec acceptance criteria are verified at
HEAD `abbed9c`; every Critical and Important audit blocker maps to re-run
passing evidence with no out-of-scope ruling; full gates, coverage (91.55%),
schemas, runtime, and frontend build are green; no `.coverage.cachyos*`
artifacts remain. This verdict becomes final only after the controller's
Step 3 whole-branch review (`849c840..abbed9c`) returns clean, or after any
Critical/Important finding it raises is fixed in one consolidated wave plus one
scoped re-review. No push, merge, publication, P2 start, or recovery-evidence
deletion was performed.
