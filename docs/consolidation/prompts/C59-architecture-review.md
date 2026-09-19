# C59 — Fresh Independent Architecture and Smell Review

## Role and objective

You are the independent architecture reviewer for C59. Find duplicate sources of truth, adapter business-logic leakage, speculative abstractions, low cohesion, ambiguous concepts, and extension points that would make dbt/MCP require modification rather than extension.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C41/C52/C57.
- Current architecture docs, dependency validator, package tree, application/services/check catalogue, platform routes, CLI, tests, and performance evidence.

## Current ownership and resulting owner

This review tests whether the intended architecture exists in code rather than accepting folder names. Every finding must identify the current and proposed owner, dependency violation, contract effect, and smallest correction.

## Interfaces

Review questions: where are duplicate registries/config precedence/fingerprints/redaction/outcome rules; where do adapters evaluate policy; which facades are necessary; which abstractions are speculative; can a second analysis family and MCP call existing services?

## Expected files

- Create/modify: `docs/consolidation/architecture-review.md`, architecture validator rules, targeted source/tests/docs for substantiated findings.
- Do not perform broad cleanup based only on aesthetic preference.

## Test-first sequence

1. Run architecture validator, import graph/complexity measurements, and independent review.
2. Add a failing architecture/test contract for each confirmed violation.
3. Correct one owner/dependency at a time and run affected tests.
4. Rerun full architecture/default/coverage/performance gates and record intentional limitations.

## Allowed changes

- Architecture fixes, validator rules, focused regressions, and review evidence.

## Non-goals and prohibitions

- Do not create dozens of trivial helpers or generic family abstractions before a second family exists.
- Do not break compatibility to make imports look cleaner.
- Do not claim readiness from directory layout alone.

## Verification matrix

- Architecture validator, import/type/default/coverage gates, performance evidence, and independent sign-off.

## Completion checklist and handoff

- [ ] Duplicate sources of truth have one owner or documented compatibility derivation.
- [ ] Adapter leakage is tested and corrected.
- [ ] dbt/MCP extension path is described concretely.
- [ ] Commit with `refactor: resolve architecture review findings`; open the PR without merging.
