# C03 — Authoritative Check Catalogue

## Role and objective

You are the Build agent for C03. Replace the manually maintained evaluator, configuration, legacy-alias, scaffold, and fixability tables with one authoritative check catalogue while keeping compatibility names derived from it. This is a high-risk registry change: preserve behavior and prove that adding one `CheckSpec` is enough to expose every required view.

## Required reads

- `AGENTS.md`, `docs/consolidation/architecture-rules.md`, `docs/consolidation/progress.md`, and C01–C02 prompts.
- `src/conformdag/evaluator.py` (`CHECK_EVALUATORS`, legacy lookup, evaluator protocol).
- `src/conformdag/fixing/codemods.py` (`AUTOFIX_KINDS`, `PROPOSED_ONLY_KINDS`, `MANUAL_KINDS`, `FIXERS`).
- `src/conformdag/cli.py` policy scaffolding around `policy_new`.
- `src/conformdag/policy.py:validate_policy_pack`.
- `tests/test_evaluator.py`, `tests/test_fixing.py`, `tests/test_cli.py`, and `tests/test_policy.py`.

## Current ownership and resulting owner

`evaluator.py`, `fixing/codemods.py`, and `cli.py` each know part of the check catalogue. After this PR, `src/conformdag/checks/registry.py` owns `Fixability`, `CheckSpec`, `CHECK_SPECS`, `check_spec()`, and generated compatibility views. Evaluator implementations remain in `evaluator.py` until C05; codemod functions remain in `fixing/codemods.py` until they can query the catalogue.

## Interfaces

- Consumes: existing evaluator instances keyed by check kind and codemod/fixability sets.
- Produces: `CheckSpec`, `Fixability`, `CHECK_SPECS`, `LEGACY_POLICY_CHECKS`, `CHECK_EVALUATORS`, and derived fixability views. `CheckSpec` includes `kind`, `configuration_kind`, `evaluator`, `fixability`, `fix_kind`, `scaffold_factory`, and `legacy_policy_ids`.

## Expected files

- Create: `src/conformdag/checks/__init__.py`, `src/conformdag/checks/registry.py`, and `tests/checks/test_registry.py`.
- Modify: `src/conformdag/evaluator.py`, `src/conformdag/fixing/codemods.py`, `src/conformdag/cli.py`, `src/conformdag/policy.py`, and focused existing tests.
- Do not move evaluator classes or codemod bodies; C05 owns that movement.

## Test-first sequence

1. Add registry tests for unique kinds, valid configuration kinds, unique legacy IDs, scaffold validation, fixability/codemod consistency, and generated legacy lookup.
2. Run `mise exec -- uv run pytest tests/checks/test_registry.py -x --tb=short`; confirm the registry symbols do not exist yet.
3. Implement the catalogue with explicit `CheckSpec` entries for the current 12 check kinds and generated compatibility dictionaries.
4. Replace manual lookups in CLI, policy validation, and codemod classification with registry queries while preserving old imports.
5. Run `tests/checks/test_registry.py`, evaluator/fixing/CLI/policy tests, the 80-case round-trip test, `mise run check`, and `mise run test:coverage`.

## Allowed changes

- Add registry metadata and derived views.
- Add scaffold factories that return schema-valid configuration payloads.
- Preserve `CHECK_EVALUATORS`, `AUTOFIX_KINDS`, `PROPOSED_ONLY_KINDS`, and `MANUAL_KINDS` as derived compatibility names.

## Non-goals and prohibitions

- Do not change evaluator logic, finding semantics, fix application, or policy IDs.
- Do not register by policy ID as the primary key.
- Do not add a second hidden registry in CLI, codemods, or policy validation.
- Do not use a broad `dict[str, Any]` metadata escape hatch in place of `CheckSpec` fields.

## Verification matrix

- Registry unit tests and schema-valid scaffolding tests.
- Existing evaluator, policy, CLI, fixing, and round-trip suites.
- `mise run check`, `mise run test:coverage`, and pack validation.
- Independent review must attempt to add a check by editing only the catalogue and verify no duplicate table is required.

## Completion checklist and handoff

- [ ] One source of truth derives all compatibility views.
- [ ] Every current check has a `CheckSpec` and every autofix has a codemod.
- [ ] Legacy IDs map to check kinds, not directly to evaluator instances.
- [ ] No evaluator implementation moved prematurely.
- [ ] Commit with `refactor: centralize check catalogue`; open the PR without merging and attach registry/round-trip evidence.
