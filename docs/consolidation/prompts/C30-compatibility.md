# C30 — Make Compatibility and Deprecation Explicit

## Role and objective

You are the Build agent for C30. Create an explicit compatibility layer for legacy policy IDs, imports, hidden CLI aliases, report/policy contracts, and deprecation timing after the structural moves stabilize.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C02/C28/C29.
- All package facades and registry compatibility views, CLI command history/tests, `frontend/src/api.ts`, schemas, and current docs.

## Current ownership and resulting owner

Legacy mappings and aliases are scattered across evaluator, CLI, and tests. After this PR, `src/conformdag/compat/` owns historical routing and documentation records; modern domain/catalogue modules remain authoritative.

## Interfaces

Define explicit modules such as `compat/checks.py` and `compat/cli.py`. Every compatibility entry records reason, introduced version, and removal condition. Legacy IDs resolve to modern check kinds before normal catalogue lookup.

## Expected files

- Create: `src/conformdag/compat/__init__.py`, `checks.py`, `cli.py`, and `docs/compatibility.md`.
- Modify: registry, CLI facade, package `__init__` facades, schemas/docs, and compatibility tests.
- Do not remove old fields/aliases in this PR unless the documented beta policy explicitly permits it and all consumers are migrated.

## Test-first sequence

1. Add tests for legacy ID routing, old imports, hidden `explain`, old report/policy fields, and installed entry points.
2. Run the compatibility tests before extraction.
3. Move historical logic into explicit compat modules and make modern modules consume generated mappings.
4. Run full Python/frontend/package tests and schema checks.
5. Run `mise run check`, coverage, and wheel smoke.

## Allowed changes

- Compatibility modules, deprecation docs, generated mappings, and regression tests.

## Non-goals and prohibitions

- Do not make compatibility modules a second modern implementation.
- Do not delete a public path without migration evidence and removal condition.
- Do not add speculative versioning for features that do not exist.

## Verification matrix

- Compatibility/import/CLI/report/schema tests.
- Frontend build, default gate, coverage, and installed-wheel smoke.
- Independent review of every deprecated surface.

## Completion checklist and handoff

- [ ] Legacy routing is explicit and generated from modern metadata where possible.
- [ ] Compatibility docs name reason/version/removal condition.
- [ ] Modern code does not depend on adapter aliases.
- [ ] Commit with `docs: define compatibility policy`; open the PR without merging.
