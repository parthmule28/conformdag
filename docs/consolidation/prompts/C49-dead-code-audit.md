# C49 — Audit Dead Code and Redundant Surfaces

## Role and objective

You are the Build agent for C49. Run dead-code, dependency, import, and repository searches after structural movement stabilizes, then remove only proven unused wrappers, aliases, inert fields, and constants.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C33/C37/C47/C48.
- Current compatibility facades, generated types, CLI aliases, model fields, ID helpers, benchmark/demo packages, and all public import tests.

## Current ownership and resulting owner

Structural moves can leave redundant wrappers such as frontend policy aliases, duplicate ID helpers, hidden CLI routes, inert configuration fields, and compatibility exports. After this PR, every retained wrapper has a documented purpose; proven dead code is removed at its actual owner.

## Interfaces

For each candidate record symbol/path, callers, public-contract status, introduction/removal rationale, and decision. Compatibility surfaces stay when C30 says they are supported.

## Expected files

- Modify source/docs/tests only for reviewed findings from Vulture, deptry, Ruff, Pyright, import searches, and generated-file checks.
- Create an audit evidence file under `docs/consolidation/` if the existing ledger cannot hold the findings.
- Do not auto-delete tool findings.

## Test-first sequence

1. Run tools and repository searches; collect candidates without editing.
2. Add regression/import/contract tests for any candidate whose removal could be ambiguous.
3. Remove one proven dead surface at a time and run its focused tests.
4. Run default, coverage, frontend, package, benchmark, and compatibility gates.

## Allowed changes

- Proven dead-code removal, facade cleanup, docs, and regression tests.

## Non-goals and prohibitions

- Do not remove public compatibility paths, generated assets, or “unused” imports that protect optional extras without evidence.
- Do not combine unrelated style cleanup.

## Verification matrix

- Tool findings reviewed manually, focused tests, `mise run check`, coverage, package/frontend/benchmark gates.

## Completion checklist and handoff

- [ ] Every removed symbol has evidence of no supported caller.
- [ ] Retained wrappers have documented ownership.
- [ ] Public/compatibility surfaces remain intact.
- [ ] Commit with `chore: remove proven dead consolidation surfaces`; open the PR without merging.
