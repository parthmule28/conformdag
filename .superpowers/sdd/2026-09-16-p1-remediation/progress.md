# SDD ledger — plan: docs/superpowers/plans/2026-09-16-p1-remediation.md

## Identity

- Spec: docs/superpowers/specs/2026-09-16-p1-remediation-design.md
- Plan commit: 849c840
- Branch: feat/policy-management
- Remediation base: 849c840
- No push, merge, publication, P2 work, or workspace deletion is authorized.

## Preflight Interface Scan

| Tasks | Producer / consumer | Finding |
|---|---|---|
| 1 → 2 | Authoritative pack validation precedes runner gate/baseline work | Clean; Task 2 assumes malformed packs cannot enter evaluation. |
| 1 → 5 | PackService mutations consume authoritative validation | Clean; Task 5 validates reconstructed packs before atomic write. |
| 2 → 3 | Durable terminal scan semantics precede worker transitions | Clean; Task 3 must preserve cancelled/failed decisions made by runner. |
| 2 ↔ 4 | Runner changes share platform startup/factory code | Ordered; Task 4 changes factory ownership only after Task 2 stabilizes runner semantics. |
| 3 → 4 | Worker state machine precedes deployment startup changes | Clean; Task 4 may alter factory creation but not Task 3 transitions. |
| 4 → 5 | App startup precedes policy persistence | Clean; Task 5 retains route ordering and startup pack registration. |
| 6 → 7 | Generic edit safety precedes TaskFlow codemod expansion | Clean; Task 7's new spans inherit Task 6 conflict and verification guarantees. |
| 1-7 → 8 | Acceptance consumes all task evidence | Clean; Task 8 changes no product behavior except one consolidated review fix if required. |
| 1 | Tests require loader rejection; implementation centralizes loader validation | Internally consistent. |
| 2 | Tests require failed incomplete scans, eligible baselines, applied suppressions | Internally consistent; API/CLI/runner share one eligibility helper. |
| 3 | Tests require durable retries/cancellation and bounded retention | Internally consistent; timeout remains a hard upper bound. |
| 4 | Tests require startup-only migrations and shared Compose workspace | Internally consistent; fresh test databases must call initializer explicitly. |
| 5 | Tests require lossless metadata and concurrent writes | Internally consistent; lock covers the whole read-modify-write transaction. |
| 6 | Tests require residuals rather than unsafe writes | Internally consistent; identical spans may deduplicate, distinct same-coordinate spans conflict. |
| 7 | Tests require concrete DAG identity and TaskFlow retry autofix | Internally consistent after plan self-review selected decorator codemod support. |
| 8 | Verification and review only | Internally consistent; no push or P2 start. |

## Rulings

- Ruling: implement TaskFlow retry decorator codemods rather than downgrading the
  entire `retry-bounds` kind to manual, because operator retry fixes are already
  safely shipped and the finding payload promises mechanical replacement — cost
  if wrong: additional AST span logic and regression surface in Task 7.

BASE for Task 1: 849c840
Task 1 review 1: Important — malformed registered-pack mutations return HTTP
500 because app routes do not map `PolicyValidationError` to HTTP 422.
Task 1: minor (deferred): doctor no longer aggregates provenance/gate rows after
an initial pack-load failure; fail-closed behavior is intact.
Task 1: minor (deferred): PackService validates errors via `str(exc).split("; ")`
rather than the typed `exc.issues` list.
Task 1: fix round 1/5 (1 addressed, 0 open — typed malformed-pack mutation
errors now map to HTTP 422; commits 2aea0d9..ce87f94)
Task 1: minor (deferred): read-only malformed-pack policy listing still maps
`PolicyValidationError` through the generic HTTP 500 handler; it remains
fail-closed and was outside the reviewed mutation contract.
Task 1: complete (commits 849c840..ce87f94, task review and scoped fix review clean)
BASE for Task 2: ce87f94
Task 2 review 1: Important — add an explicit always-block suppression
regression; implementation already excludes suppressed findings.
Task 2: minor (deferred): persistent runner failure path skips cancellation
re-check; carry to Task 3.
Task 2: minor (deferred): cancellation can race between check and final commit;
carry to Task 3.
Task 2: minor (deferred): `_was_cancelled()` expires the whole identity map;
consider a targeted refresh in Task 3.
Task 2: fix round 1/5 (1 addressed, 0 open — explicit always-block suppression
regression; commits c7bda4c..1a2a9d8)
Task 2: complete (commits ce87f94..1a2a9d8, task review and scoped fix review clean)
BASE for Task 3: 1a2a9d8
Task 3: minor (deferred): timeout cleanup grace can exceed the nominal deadline;
carry as an operational bound note.
Task 3: minor (deferred): zero/negative timeout has a pipe-drain edge case.
Task 3: minor (deferred): cancel endpoint's reverse TOCTOU can overwrite a
runner success; carry as platform state follow-up.
Task 3: minor (deferred): status-only claim transition lacks a claim-generation
guard under stale-worker misconfiguration.
Task 3: minor (deferred): cancellation/rowcount behavior needs real Postgres
runtime evidence; SQLite and focused tests pass.
Task 3: complete (commits 1a2a9d8..f51a4c5, review clean; 5 deferred minors)
BASE for Task 4: f51a4c5
Task 4: minor (deferred): deployment docs overstate startup repository seeding;
workspace startup currently registers packs, not RepositoryRows.
Task 4: minor (deferred): AGENTS.md still documents the old migration-owning
`create_session_factory` contract and should be refreshed.
Task 4: minor (deferred): concurrent API/worker Alembic startup can race on a
fresh Postgres deployment.
Task 4: minor (deferred): Compose hard-codes the workspace filename.
Task 4: minor (deferred): Compose test uses a CWD-relative path.
Task 4: complete (commits f51a4c5..18ce2e8, review clean; 5 deferred minors)
BASE for Task 5: 18ce2e8
Task 5 review 1: Important — temp path is assigned after `handle.write()`, so
partial write failures leak unique temporary files; restore write-failure
cleanup regression and assign the path before writing.
Task 5: minor (deferred): safe_path/source_version cannot be explicitly cleared
because null means preserve.
Task 5: minor (deferred): raw thread exceptions are observed indirectly in the
concurrency test.
Task 5: minor (deferred): unreachable `configuration` merge branch remains.
Task 5: fix round 1/5 (1 addressed, 0 open — assign temp path before write and
restore partial-write cleanup regression; commits a94e056..5f0afdf)
Task 5: complete (commits 18ce2e8..5f0afdf, task review and scoped fix review clean; 3 deferred minors)
BASE for Task 6: 5f0afdf
Task 6 ruling: uphold the authoritative Safe Fix Contract over preserving the
current shared-anchor implementation; make `_merge_spans` dedup-only and move
owner/tags legitimate insertions to distinct anchors, with roundtrip coverage —
cost if wrong: codemod anchor changes may require additional regression work,
but retaining the merge would ship an explicit safety-contract violation.
Task 6 review 1: Important — engine merges distinct same-coordinate zero-width
insertions instead of converting them to residuals; fix under the ruling above.
Task 6: minor (deferred): proposed-only span conflicts can still propagate from
`_record_proposed_moves`; carry to final fix-safety review.
Task 6: minor (deferred): incomplete-verification residual dedup can retain an
empty reason over the fatal scan reason.
Task 6: fix round 1/5 (1 addressed, 0 open — shared-offset insertion merge;
commit 80110f4..bc57827)
Task 6: minor (deferred): sequential re-anchoring can apply redundant identical
cross-finding payloads twice when duplicate policies target one call.
Task 6: complete (commits 5f0afdf..bc57827, review clean; 3 deferred Minors)
Task 7 review 1: Important findings — ERROR outcomes are not operationally
fail-closed across gates/CLI/agent/platform; unresolved operator retry names
still coerce to zero; explicit `dag=` can be shadowed by with-context defaults.
Task 7 ruling: preserve the brief's ERROR finding status while making ERROR an
incomplete/non-successful evaluation across every consumer; apply the same
fail-closed treatment to unresolved operator retry values; explicit resolved
`dag=` bindings take precedence over enclosing context, while line linkage
remains the fallback for implicit context. Cost if wrong: exit/report and
default-resolution behavior changes are broader than the original file list,
but leaving these paths open violates the unconditional dynamic-value and
TaskFlow-context guarantees.
Task 7: fix round 1/5 (3 addressed, 0 open — ERROR consumer handling, operator
uncertainty, explicit dag binding; commit 8b62798..abbed9c)
Task 7: minor (deferred): dynamic operator execution_timeout now loses SET
fixability when unresolved values are omitted.
Task 7: minor (deferred): platform suppressions run after the fatal ERROR issue
is minted, so they cannot waive that issue.
Task 7: minor (deferred): TaskFlow decorator assignment constants are not
resolved like operator values.
Task 7: minor (deferred): reused aliases for explicit dag bindings remain
statically ambiguous.
Task 7: complete (commits bc57827..abbed9c, review clean; 9 deferred Minors)
Task 8 final review: Important I-1 — PackService mutation validates only the
individual policy and can persist an unrunnable reconstructed pack; this violates
the authoritative mutation boundary. Minor M-1 — incomplete CLI reports can
carry a passing gate_result. No Critical findings.
Final review ruling: fix I-1 and include M-1 in the same consolidated wave
because both are small authoritative-boundary/report-integrity defects and the
acceptance verdict cannot be Ready while I-1 remains. Cost if wrong: one extra
fix/review cycle and broader final-gate reruns; leaving I-1 would require
filesystem recovery for a normal dashboard mutation.
BASE for Task 8: abbed9c
Task 8: acceptance Step 1 executed — every audit Critical (7) and Important (9)
blocker re-verified green at abbed9c via the Tasks 1-7 focused regression
nodes plus fix-round nodes (13 focused runs, all exit 0); no out-of-scope
ruling was needed. Evidence: acceptance-report.md requirement-to-evidence
matrix and command log.
Task 8: acceptance Step 2 executed — `mise run check` (339 passed, pyright
strict 0 errors, exit 0), `mise run test:coverage` (91.55% >= 90%, exit 0),
`mise run schema --check` (exit 0), `mise run test:runtime` (13 passed, Docker
daemon available, exit 0), `npm run build` in frontend/ (tsc + vite, exit 0);
no root `.coverage.cachyos*` artifacts remain after all test processes.
Task 8: Step 3 whole-branch review (849c840..abbed9c) is PENDING and owned by
the controller; verdict is provisional until it returns clean or any
Critical/Important finding is fixed in one consolidated wave plus one scoped
re-review.
Task 8: provisional decision — P1 Ready (provisional), recorded in
acceptance-report.md; no push, merge, publication, P2 start, or
recovery-evidence deletion performed.
Task 8: final fix wave executed at base 46c6824 (TDD red→green) — I-1 fixed by
authoritative `validate_policy_pack()` before `_write_pack()` in
`PackService.upsert_policy` (PackError → existing 422 path, pack bytes
unchanged, recovery proven); M-1 fixed by skipping gate evaluation for
incomplete CLI reports (exit-3 behavior preserved). Regressions:
test_upsert_policy_rejects_unknown_evaluator_and_keeps_pack_usable,
test_policy_upsert_endpoint_rejects_unknown_evaluator_with_422,
test_scan_incomplete_report_does_not_embed_gate_result. Full gates re-run
green: `mise run check` (342 passed, pyright 0 errors), `mise run
test:coverage` (91.56%), `mise run schema --check`, `mise run test:runtime`
(13 passed), `mise run ui-build` — all exit 0. Evidence:
final-fix-report.md. Scoped re-review of the fix wave PENDING; verdict stays
provisional until it returns.
Task 8: scoped re-review of final fix wave complete — I-1 and M-1 addressed,
no new Critical/Important/Minor findings. Evidence: final-re-review.md.
Task 8: minor (deferred): `delete_policy()` can persist a gate-invalid pack
after removing a referenced policy; pre-existing and outside the final scoped
findings, with fail-visible recovery impact.
Task 8: complete (commits 849c840..dff158f, review clean; P1 Ready; deferred
residuals recorded; no push, merge, publication, P2 start, or evidence deletion)
