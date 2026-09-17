# SDD ledger — plan: docs/superpowers/plans/2026-09-17-p2-ui.md

## Preflight

The approved specification is `docs/superpowers/specs/2026-09-17-p2-ui-design.md`. The implementation plan was read in full. The worktree is `/tmp/opencode/conformdag-p2-ui` on `feat/p2-ui-work`, based on `96409e1`.

Skill preflight found generic process skills (`brainstorming`, `executing-plans`, `subagent-driven-development`, `test-driven-development`, `verification-before-completion`, and related review skills) but no dedicated frontend-design, API-development/contract-first, Playwright, or accessibility skill in the configured catalog or repository-local directories. The approved spec is the fallback contract for those areas.

Baseline verification: `mise run check` passed with 342 selected tests and 0 failures; `frontend/npm run build` passed with TypeScript strict compilation and Vite output. No implementation task has started.

## Plan Conflict Scan

The table records every task's internal consistency and every task pair that shares a file or interface. Findings are ruled against the approved spec before dispatch.

### Task Self-Consistency

| Task | Files and outputs checked | Tests against implementation | Finding | Ruling |
|---|---|---|---|---|
| 1 | `packs.py`, `app.py`, `runner.py`, `test_platform.py`, SDD ledger | Delete validation, malformed-list 422, PUT fallback, active/expired suppression tests cover each requested behavior | Consistent | Proceed |
| 2 | migration, `db.py`, `runner.py`, `app.py`, `contracts.py` | Migration, ingest, legacy row, and payload tests cover each new field | Consistent | Proceed |
| 3 | `app.py`, `contracts.py`, optional `db.py` | Header, tie ordering, filters, baseline filtering, and CORS tests cover the list contract | Consistent | Proceed |
| 4 | `aggregates.py`, `contracts.py`, `app.py` | Seeded status/baseline/suppression/date tests cover current and trend aggregates | Consistent | Proceed |
| 5 | `packs.py`, `app.py`, `contracts.py` | Service and HTTP tests cover all five rule types, validation, order, auth, and bytes | Consistent | Proceed |
| 6 | `models.py`, `packs.py`, `app.py`, schema | Model and round-trip tests cover defaults, slug validation, omitted/empty updates, and schema | Consistent | Proceed |
| 7 | `api.ts`, package files, Vitest setup | Fixture tests cover transport headers, errors, serialization, and all client helpers | Consistent | Proceed |
| 8 | shell, router, tokens, primitives | Theme/router tests plus build cover named shell outputs; browser accessibility is deferred to Task 12 | Consistent | Proceed |
| 9 | overview/repository pages and query hooks | Page tests cover loading, empty, error, populated, lifecycle, and baseline states | Consistent | Proceed |
| 10 | scan/finding pages and query hooks | Page fixtures cover complete, incomplete, pruned, suppressed, baseline, filters, and exports | Consistent | Proceed |
| 11 | policy/gate/suppression pages and query hooks | Page tests cover tag filters, draft failures, rule forms, expiry, and mutation errors | Consistent | Proceed |
| 12 | Playwright, seed process, CI | Real browser journeys consume the finished API and seeded healthy/broken repositories | Consistent | Proceed |
| 13 | ledger, acceptance report, whole branch | Full gates and invariant checks cover all prior outputs | Consistent | Proceed |

### Shared File And Interface Pairs

| Tasks | Producer -> consumer | Finding | Ruling |
|---|---|---|---|
| 1 -> 2 | `app.py` hygiene and `runner.py` suppression state -> finding DTO/migration work | Task 2 must retain Task 1's final report semantics while adding only persisted end positions | No conflict; Task 2 consumes the corrected behavior | Proceed |
| 1 -> 3 | `app.py` fallback/CORS route surface -> paginated list routes | Specific routes remain before fallback; Task 3 only adds headers/query parameters | No conflict | Proceed |
| 1 -> 5 | `packs.py` complete validation -> gate CRUD | Gate writes use the same validation/atomic writer boundary strengthened for deletes | No conflict; Task 5 reuses the Task 1 boundary | Proceed |
| 1 -> 6 | `app.py`/`packs.py` policy mutation errors -> tag field threading | Tags must preserve Task 1's validation/error mapping | No conflict | Proceed |
| 1 -> 12 | runner suppression semantics -> broken/healthy browser seed journeys | Seeded scans must expose active and expired semantics through the final UI | No conflict | Proceed |
| 2 -> 3 | `FindingResponse`, `ScanSummaryResponse`, `end_line` -> filters/pagination | Task 3 consumes DTO names and adds no incompatible body wrapper | No conflict | Proceed |
| 2 -> 4 | `contracts.py` scan/finding shapes -> aggregate DTOs | Aggregate DTOs extend the same explicit wire-contract module | No conflict; shared module edits remain additive | Proceed |
| 2 -> 5 | `contracts.py` response models -> gate DTOs | Gate DTOs append to the module without ORM serialization | No conflict | Proceed |
| 2 -> 6 | `app.py` request/response model location -> tags request field | Task 6 extends existing request models additively | No conflict | Proceed |
| 2 -> 7 | backend finding/scan DTOs -> TypeScript DTOs | Client mirrors stable JSON and maps array headers to `Page<T>` | No conflict; HTTP body remains an array | Proceed |
| 2 -> 10 | `end_line`, `fix`, `baseline_status` -> finding detail UI | Task 10 renders persisted fields and retained report evidence separately | No conflict | Proceed |
| 3 -> 4 | baseline filter/order/count semantics -> trend count semantics | Both use `eligible_baseline()` and persisted rows; aggregates do not call routes | No conflict; share a helper only when it is genuinely reusable | Proceed |
| 3 -> 7 | array response plus `X-Total-Count` -> `requestPage()` | Task 7 must parse headers without changing backend array responses | No conflict | Proceed |
| 3 -> 9 | history pagination/header -> repository history table | Task 9 uses `Page<ScanSummary>` and server total, not item length | No conflict | Proceed |
| 3 -> 10 | findings query filters/pagination -> findings toolbar/table | Task 10 sends exact server filters and resets page on changes | No conflict | Proceed |
| 4 -> 7 | overview/trend DTOs -> typed client | Client types mirror date/count/recent-scan fields | No conflict | Proceed |
| 4 -> 9 | overview/trends routes -> overview/repository views | Pages consume aggregate data and do not fabricate missing dates | No conflict | Proceed |
| 5 -> 6 | `contracts.py` gate models -> policy tags in same module | Additive DTO changes do not alter gate wire shape | No conflict | Proceed |
| 5 -> 7 | gate API routes -> gate client functions | Client uses exact PUT/DELETE paths and typed rules | No conflict | Proceed |
| 5 -> 11 | gate CRUD contract -> gate editor | UI delegates validation and result evaluation to backend | No conflict | Proceed |
| 6 -> 7 | `Policy.tags` API -> TypeScript policy DTO | Client adds tags without dropping existing metadata | No conflict | Proceed |
| 6 -> 11 | tag validation/round-trip -> policy editor/filter | UI sends ordered slugs and represents server validation failures | No conflict | Proceed |
| 7 -> 8 | typed client/error model -> shell/query hooks | Shell owns transport-independent layout; pages use client only through hooks | No conflict | Proceed |
| 7 -> 9 | client functions -> overview/repository query hooks | Hook keys/invalidation can consume all client outputs | No conflict | Proceed |
| 7 -> 10 | client functions -> scan/finding query hooks | Report 404 and ApiError status are preserved for UI state | No conflict | Proceed |
| 7 -> 11 | client functions -> mutation forms | Pages map `ApiError` statuses and keep drafts on rejection | No conflict | Proceed |
| 8 -> 9 | router/shell/primitives -> overview/repository pages | Pages render inside AppShell and use only shared tokens/primitives | No conflict | Proceed |
| 8 -> 10 | router/shell/primitives -> scan page | Scan route and detail primitives are available before page work | No conflict | Proceed |
| 8 -> 11 | router/shell/primitives -> policy/suppression pages | Existing route names remain stable while App.tsx is split | No conflict | Proceed |
| 9 -> 10 | query hook naming/invalidation -> scan-specific hooks | Task 10 extends the hook layer without changing Task 9 page contracts | No conflict | Proceed |
| 9 -> 12 | page selectors/navigation -> Playwright journeys | Task 12 adds selectors required by completed pages and tests real URLs | No conflict | Proceed |
| 10 -> 12 | scan/finding states -> browser scan journey | Seed and browser assertions cover complete/incomplete/artifact-pruned branches | No conflict | Proceed |
| 11 -> 12 | policy/gate/suppression selectors -> browser mutation journeys | Browser tests use the same typed client and real mutation routes | No conflict | Proceed |
| 12 -> 13 | CI/browser artifacts -> final acceptance | Task 13 reruns local/CI-equivalent browser commands and records evidence | No conflict | Proceed |

The scan found no contradiction with the approved specification, no task that requires a second evaluation pipeline, and no task that writes schema outside Alembic. The plan is approved for execution without additional rulings.

Task 1: minor (deferred): the expired-suppression regression was already green before the fix because expiry filtering was pre-existing; it remains a useful boundary lock.
Task 1: minor (deferred): the unknown-API PUT regression does not cover HEAD/OPTIONS, which is outside the task brief.
Task 1: minor (deferred): `_seed_error_scan` duplicates an existing fixture shape; extract only if another copy is needed.
Task 1: complete (commits 96409e1..d0228fc, review clean)
Task 2: minor (deferred): the history DTO test is not selected by the brief's focused `-k` filter, but it is covered by the full suite.
Task 2: minor (deferred): history and status duplicate gate-result extraction; a shared helper can be considered if future drift appears.
Task 2: minor (deferred): migration downgrade is not automated, matching the pre-existing migration test convention.
Task 2: complete (commits d0228fc..e8e83f7, review clean)
Task 3: minor (deferred): NULL `file_path`/`start_line` ordering is implemented with `nullslast()` but lacks a dedicated seeded regression.
Task 3: minor (deferred): uppercase severity normalization is implemented but not separately exercised.
Task 3: minor (deferred): pre-existing invalid-pagination bounds tests were green before the change; new pagination tests provide the red evidence.
Task 3: complete (commits e8e83f7..44e7333, review clean)
Task 4: minor (deferred): `recent_scans` includes failed/cancelled rows as recent dashboard context; the binding contract permits active/completed summaries and the behavior is pinned.
Task 4: minor (deferred): trend FAIL/ERROR buckets exclude suppressed rows and track suppression separately; this matches current findings semantics but could be stated more explicitly in the spec.
Task 4: minor (deferred): the direct aggregate helper returns empty points for an unknown repository while the HTTP route maps it to 404.
Task 4: minor (deferred): latest eligible scan selection materializes all succeeded/complete rows; a window-function query can be considered at larger scale.
Task 4: complete (commits 44e7333..86945c5, review clean)
Task 5: minor (deferred): invalid gate ID shape is enforced by `QualityGate` but not covered by a dedicated route test.
Task 5: minor (deferred): `GateUpsertRequest` omits a conflicting payload `id`, so the path ID remains authoritative at HTTP level; direct service mismatch coverage remains.
Task 5: minor (deferred): the delete-gate post-validation failure branch is unreachable with current validation rules but is retained for future rules.
Task 5: minor (deferred): pre-existing policy-upsert unknown-pack mapping differs from the new gate PUT mapping; Task 5 preserves the specified gate behavior.
Task 5: complete (commits 86945c5..c40f674, review clean)
Task 6: Ruling: use a 1-32 character lowercase slug regex with an alphanumeric final character, rather than the literal pattern that permits trailing hyphens — the explicit behavioral requirement rejects trailing hyphens; cost if wrong: tags ending in hyphens would be rejected even if a future contract intentionally permits them.
Task 6: minor (deferred): global model whitespace stripping means surrounding tag whitespace is normalized before the tag validator runs.
Task 6: minor (deferred): creating a new policy with tags lacks a dedicated platform test, though model/default and update cases cover the required behavior.
Task 6: minor (deferred): successful writes serialize `tags: []` for previously tag-less policies, including unrelated valid writes.
Task 6: minor (deferred): `list_policies()` exposes the live tags list rather than a `model_dump` copy, which is harmless after JSON serialization.
Task 6: minor (deferred): post-construction tag assignment bypasses validation, matching existing model-validator convention.
Task 6: complete (commits c40f674..775849b, review clean)
Task 7: minor (deferred): `requestPage()` uses lenient integer parsing for malformed `X-Total-Count` values.
Task 7: minor (deferred): fail-closed pagination errors report the HTTP status in the message rather than the synthetic 502 status.
Task 7: minor (deferred): the unexported header merge would not copy a future `Headers` instance correctly.
Task 7: minor (deferred): successful non-JSON responses surface `SyntaxError` rather than `ApiError`, though current JSON routes do not hit it.
Task 7: minor (deferred): the `Repository` DTO still needs `baseline_scan_id` for the baseline UI.
Task 7: minor (deferred): the legacy App finding count used page length; the App rewrite must use page total.
Task 7: minor (deferred): CORS does not expose `X-Request-ID` for cross-origin clients.
Task 7: minor (deferred): blank-token tests do not separately cover whitespace-only input.
Task 7: complete (commits 775849b..fae1f7d, review clean)
Task 8: Ruling: create minimal route-target page modules with the shell so `routes.tsx` can compile and map all canonical paths; Tasks 9-11 replace those stubs with feature pages — cost if wrong: the shell commit contains temporary page modules that add no behavior and must be replaced before acceptance.
Task 8: minor (deferred): shell navigation initially omits parameterized repository and scan links; Tasks 9-10 must add contextual links.
Task 8: minor (deferred): explicit-dark users can see one light frame before the theme effect applies.
Task 8: minor (deferred): the unused Tailwind `dark` custom variant remains harmless dead CSS.
Task 8: minor (deferred): fixed tab IDs can collide if multiple instances reuse a tab ID.
Task 8: minor (deferred): table empty-state headings reuse the table caption and are cosmetic.
Task 8: minor (deferred): dark palette declarations are duplicated but currently identical.
Task 8: complete (commits da92676..bde9741, review clean)
Task 9: minor (deferred): successful-cancel invalidation is verified by code inspection but lacks a dedicated test.
Task 9: minor (deferred): mobile history layout relies on the shared table primitive and has no page-level responsive test.
Task 9: minor (deferred): a scan-queued banner can persist across repository navigation until dismissed.
Task 9: minor (deferred): cancelled scans render with the `INCOMPLETE` badge tone.
Task 9: minor (deferred): pure presentation helpers live in the query-hook module.
Task 9: fix round 1/5 (1 addressed, 0 open; commits e9a7012..2a47fd2)
Task 9: minor (deferred): the new pending trends test uses an unscoped status-role lookup.
Task 9: complete (commits bde9741..2a47fd2, review clean)
Task 10: minor (deferred): scan detail exports are shown for any loaded report artifact, including incomplete failed reports, while history export links require complete scans.
Task 10: minor (deferred): `routes.tsx` was listed as modified but needed no change because the scan route already existed.
Task 10: minor (deferred): text filters issue server queries per keystroke.
Task 10: minor (deferred): cancelled scans reuse the `INCOMPLETE` badge tone while retaining a distinct status label.
Task 10: minor (deferred): `EMPTY_FINDINGS_FILTERS` is mutable-shaped but only copied/reset by current code.
Task 10: fix round 1/5 (1 addressed, 0 open; commits d935906..be7f738)
Task 10: complete (commits 2a47fd2..be7f738, review clean)
Task 11: minor (deferred): gate deletion has no confirmation dialog.
Task 11: minor (deferred): selected pack state is component-local rather than URL-addressable.
Task 11: minor (deferred): policy filter options derive from the currently loaded data.
Task 11: minor (deferred): pack policy and gate lists remain unpaginated because the backend contract is unpaginated.
Task 11: minor (deferred): policy save invalidates the pack root, including gates, beyond the minimum required invalidation.
Task 11: minor (deferred): lifecycle status constants are duplicated between policy page/editor modules.
Task 11: minor (deferred): gate rule editor keys are positional and can churn DOM nodes after mid-list removal.
Task 11: fix round 1/5 (2 addressed, 0 open; commits daa07e3..79b20e9)
Task 11: complete (commits be7f738..79b20e9, review clean)
Task 12: minor (deferred): local Playwright `reuseExistingServer` can reuse stale seed state and produce noisy duplicate-row/gate failures.
Task 12: minor (deferred): the new CI browser job has not run on GitHub because pushing is intentionally out of scope.
Task 12: minor (deferred): journey specs depend on Playwright file ordering because one suppression mutates a fingerprint used by later journeys.
Task 12: minor (deferred): the seed worker join has a finite timeout while runner subprocesses can have a longer timeout, creating a theoretical cleanup race.
Task 12: minor (deferred): browser timing headroom is generous and relies on CI retry/trace settings as a flake backstop.
Task 12: fix round 1/5 (1 addressed, 0 open; commits 59c100d..4b0e084)
Task 12: minor (deferred): `@types/node` becomes ambient in the app TypeScript space because the root config has no `types` restriction.
Task 12: minor (deferred): the e2e typecheck script redundantly passes `--noEmit` already present in its config.
Task 12: complete (commits 79b20e9..4b0e084, review clean)
Task 13: final review initially found one Important API classification issue: delete handlers treated missing resources and reconstructed-pack validation failures as the same `PackError`/404 response. Root cause was confirmed in `PackService` and the HTTP handlers. A TDD regression reproduced policy deletion returning 404 for a live validation conflict and a gate-handler validation error returning 404.
Task 13: fix loop added `PackNotFoundError` as a `PackError` subtype, mapped not-found errors to 404 and remaining pack validation errors to 422 across policy/gate mutations, and mapped unknown pack validation requests to 404. Auth-masked unknown-resource tests were replaced with exact authenticated assertions. Focused status tests: 6 passed.
Task 13: final whole-branch review verified the fixes and reported no Critical or Important findings. Remaining notes are Minor and recorded in `acceptance-report.md`.
Task 13: acceptance complete. `mise run check` 397 passed; coverage 92.24%; schema check passed; runtime 13 passed; UI build passed; frontend 107 passed and built; Playwright 6 passed; benchmark 240/240 passed; wheel build passed. No release action taken. Documentation commit follows.
