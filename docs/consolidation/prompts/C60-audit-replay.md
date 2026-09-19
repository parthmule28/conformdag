# C60 — Replay the Historical Audit

## Role and objective

You are the Build agent for C60. Replay every recorded remediation finding from the repository's prior plans and audit evidence against the consolidated tree, and produce evidence that structural work did not reintroduce closed defects.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C58/C59.
- Original audit/remediation plan and evidence, current security/architecture docs, adversarial suite, package/runtime/browser/Postgres checks, and source owners.

## Current ownership and resulting owner

Historical findings are recorded across prior plans and tests. After this PR, one replay checklist maps every original ID to current implementation, regression test, verification command, and status.

## Interfaces

For each recorded finding ID record: original invariant, current owner/path, current regression test, latest evidence, and remaining risk. A closed finding must have implementation and test evidence; intentional changes require a compatibility/security note.

## Expected files

- Create/modify: `docs/consolidation/historical-audit-replay.md`, `progress.md`, and targeted regressions/fixes only for reintroduced defects.
- Do not rewrite historical evidence to match the new architecture.

## Test-first sequence

1. Build the replay matrix for every recorded remediation finding before changing code.
2. Run each focused suite/group and mark discrepancies.
3. Add failing regressions for reintroduced defects, fix owners, and rerun.
4. Run default, coverage, security, privacy, Postgres, runtime, package, browser, benchmark, and architecture gates.

## Allowed changes

- Replay accounting, targeted regressions/fixes, and evidence documentation.

## Non-goals and prohibitions

- Do not mark a finding closed from a code search alone.
- Do not drop an old invariant because the module moved.
- Do not conceal failures with broad skips.

## Verification matrix

- Every recorded historical ID, current regression tests, full relevant verification matrix, and independent review of accounting.

## Completion checklist and handoff

- [ ] Every recorded historical finding ID has current evidence and status, and the replay reports the actual count rather than assuming a fixed total.
- [ ] Reintroduced defects are fixed and retested.
- [ ] Remaining intentional risks are named.
- [ ] Commit with `docs: replay historical audit evidence`; open the PR without merging.
