# C21 — Split the Domain Models Package

## Role and objective

You are the Build agent for C21. Split `src/conformdag/models.py` into cohesive model modules while preserving every old import and proving checked-in JSON schemas remain structurally unchanged.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C02/C18–C20.
- Full `src/conformdag/models.py`, `scripts/export_schemas.py`, `schemas/`, and all model importers.
- `tests/test_models.py`, `tests/test_policy.py`, `tests/test_gates.py`, `tests/test_scan.py`, `tests/test_fixing.py`, and platform contract tests.

## Current ownership and resulting owner

One file owns common model settings, policy/configuration, gates, findings, reports, runtime, semantic, and project configuration. After this PR, `models/common.py`, `policy.py`, `gates.py`, `findings.py`, `report.py`, `runtime.py`, `semantic.py`, and `config.py` own those groups; `models/__init__.py` re-exports the complete old public surface.

## Interfaces

Preserve `ConformModel`, all Pydantic model names, validators, discriminated-union tags, JSON serialization, and import paths. No consumer should need to know which new file owns a type.

## Expected files

- Create: `src/conformdag/models/` modules and `tests/models/` only if splitting tests improves ownership.
- Remove: `src/conformdag/models.py` after import/schema parity.
- Modify: importers, `scripts/export_schemas.py` only for module discovery, `schemas/*.json` only after `mise run schema:update`.

## Test-first sequence

1. Add import-parity and schema snapshot tests; run the full model/policy/gate/report/fixing/platform tests before moving code.
2. Move common/policy/gate/finding/report/runtime/semantic/config models one group at a time.
3. Re-export from `models/__init__.py` and regenerate schemas.
4. Inspect every schema diff; reject unrelated shape changes.
5. Run `mise run schema`, `mise run check`, coverage, and package import smoke.

## Allowed changes

- File movement, facade exports, import cleanup, and schema-generator path adjustments.

## Non-goals and prohibitions

- Do not redesign domain models, rename fields, or add speculative dbt family fields.
- Do not hide schema changes by weakening validation or deleting schema files.
- Do not add adapter dependencies to models.

## Verification matrix

- Model import, validation, serialization, and schema tests.
- Full default suite, coverage, and `mise run schema`.
- Installed-wheel import smoke.

## Completion checklist and handoff

- [ ] Old imports and schemas remain compatible.
- [ ] Each model group has one cohesive owner.
- [ ] Any schema diff is intentional and documented.
- [ ] Commit with `refactor: split domain models`; open the PR without merging.
