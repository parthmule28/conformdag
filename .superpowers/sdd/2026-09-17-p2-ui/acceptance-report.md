# P2 Acceptance Report

Date: 2026-09-18
Branch: `feat/p2-ui-work`
Worktree: `/tmp/opencode/conformdag-p2-ui`
Base: `main` at `09b28cf`

## Scope

P2 delivers the URL-addressable platform dashboard and its supporting API
contracts without changing the single scan pipeline, YAML policy/gate source
of truth, baseline eligibility rules, suppression semantics, or incomplete
report contract.

## Commits

The implementation commits from `09b28cf` through the acceptance fix are:

```text
96409e1 docs: add P2 implementation plan
d0228fc fix: close P2 policy and suppression boundaries
e8e83f7 feat: persist finding end positions
44e7333 feat: add paginated platform finding queries
86945c5 feat: add platform overview and trends
c40f674 feat: manage quality gates through pack validation
775849b feat: add policy domain tags
fae1f7d feat: establish typed platform client
da92676 docs: clarify P2 route bootstrap
bde9741 feat: add routed operations console shell
e9a7012 feat: build overview and repository views
2a47fd2 fix: surface repository trends loading and errors
d935906 feat: add scan and finding investigation views
be7f738 test: cover unsuppressed error finding detail
daa07e3 feat: manage policies gates and suppressions in the UI
79b20e9 fix: read suppression expiry input as UTC
59c100d test: add Playwright platform journeys
4b0e084 test: typecheck the e2e TypeScript gate
f55f2d3 fix: map pack mutation errors precisely
```

The acceptance report and ledger are included in the final documentation
commit following this report.

## Acceptance Commands

All commands were run in `/tmp/opencode/conformdag-p2-ui` unless noted.

| Command | Observed result |
|---|---|
| `mise run check` | Passed: Ruff format/lint, Pyright `0 errors`, policy packs valid, `397 passed`, `13 deselected`. |
| `mise run test:coverage` | Passed: `397 passed`, total coverage `92.24%`, required `90%` reached. |
| `mise run schema --check` | Passed; generated schemas are synchronized. |
| `mise run test:runtime` | Passed: `13 passed`, `397 deselected`. |
| `mise run ui-build` | Passed: TypeScript build and Vite build, `126 modules transformed`. |
| `cd frontend && npm ci && npm run test -- --run && npm run build` | Passed: `107 passed` across `8` Vitest files, strict build, Vite output. `npm ci` reported `0 vulnerabilities`. |
| `cd frontend && npx playwright install chromium && npm run e2e` | Passed: `6 passed` in `26.4s`; Playwright emitted only the known unsupported-OS fallback warning. |
| `mise run benchmark` | Passed: `240/240` cases, `0` failed cases, all six policy quality gates and aggregate gate passed with F1 `1.0`. |
| `mise run build` | Passed: source distribution and wheel built successfully. |

## Browser Coverage

The browser suite uses the real `/api/v1` transport, Alembic migrations, and
the production worker through `scripts/e2e_platform.py`:

- Overview drill-down to repository history, trends, and baseline.
- Mobile navigation and responsive overview table access.
- Gate add/edit, real gate result, and incomplete broken scan state.
- Policy tag editing, pack validation, and persisted values.
- Scan trigger, bounded polling, finding filtering, and finding detail.
- Suppression creation and active-versus-expired waiver behavior.

## Targeted Contract Checks

- Pack deletion validates the complete reconstructed pack, returns `422` for
  validation rejection, preserves bytes, and returns `404` only for missing
  packs or members.
- Unknown API `PUT` paths return JSON `404`; malformed pack listings return
  `422`; unknown pack validation returns `404`.
- Active and expired platform suppressions agree across finding state, report
  completeness, fatal evaluation issues, and gate evaluation.
- Incomplete reports preserve `gate_result: null`, and the UI renders
  `Gates not evaluated` rather than deriving a result.
- Baselines are restricted to same-repository, succeeded, complete scans.
- Aggregates query persisted rows and do not invoke evaluators.
- Migration `0003` adds nullable finding end positions and legacy rows remain
  readable.
- Pagination filters before counting/slicing and exposes `X-Total-Count`.
- No frontend imports Python, SQLAlchemy, or generated server code.
- Specific FastAPI routes precede the API fallback and StaticFiles mount.
- The wheel build succeeds with the ignored dashboard static directory included
  by the existing Hatch artifact rule.

## Review

Each task received an independent review and focused fix/review loop. The final
whole-branch review covered `09b28cf..f55f2d3` plus the acceptance changes and
reported no Critical or Important findings. The final review specifically
verified the `PackNotFoundError` distinction, authenticated 404 tests, and
unknown-pack validation route.

## Known Non-Blocking Residuals

- Some presentation polish remains deferred: gate-delete confirmation,
  URL-addressable selected pack state, per-keystroke text filters, and modal
  background-scroll locking.
- History export links cannot know about retention-pruned artifacts until the
  API exposes artifact availability metadata.
- SQLite development timestamps are naive on round-trip and can display or
  classify differently in non-UTC browser locales.
- Overview/trend suppression counting follows the existing findings semantics;
  the distinction is documented in the SDD ledger rather than duplicated in
  the UI.
- The browser CI job was not executed on GitHub because pushing is outside the
  approved scope. Local Playwright runs can reuse stale servers if a prior run
  was not cleaned up.

## Release Boundary

No push, merge, release tag, publication, or deployment was performed. No
`v*` tag was created.
