# C16 — Decompose the Policy Package

## Role and objective

You are the Build agent for C16. Convert `src/conformdag/policy.py` into a cohesive package for loading, provenance, validation, and hashing while preserving all public imports and exact policy behavior.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C01.
- Full `src/conformdag/policy.py`, its importers, and policy-related tests.
- `src/conformdag/models.py`, `src/conformdag/evaluator.py`, `src/conformdag/gates.py`, `src/conformdag/platform/packs.py`, and `src/conformdag/packpull.py`.
- `tests/test_policy.py`, `tests/test_platform.py`, `tests/test_cli.py`, and bundled pack files.

## Current ownership and resulting owner

One module owns YAML loading, path resolution, pack selection, provenance validation, pack validation, policy hashes, and suppressions. After this PR, `policy/loading.py`, `provenance.py`, `validation.py`, and `hashes.py` own those concerns; `policy/__init__.py` re-exports old names. Suppression movement waits for C18/C20 if it improves ownership.

## Interfaces

Preserve `PolicyValidationError`, `resolve_policy_pack_path()`, `resolve_configured_policy_pack()`, `resolve_source_document()`, `load_policy_pack()`, `select_policy_pack()`, `validate_policy_provenance()`, `validate_policy_pack()`, `policy_contract_hash()`, and `policy_enforcement_hash()` signatures unless a compatibility wrapper is added.

## Expected files

- Create: `src/conformdag/policy/__init__.py`, `loading.py`, `provenance.py`, `validation.py`, and `hashes.py`.
- Remove: `src/conformdag/policy.py` only after import parity is proven.
- Modify: importers and split/add `tests/policy/` modules without losing current coverage.
- Do not implement canonical editing; C17 owns mutation semantics.

## Test-first sequence

1. Add import-parity tests and keep current policy characterization tests green.
2. Run policy, pack, CLI, platform, and distribution tests before moving code.
3. Move functions by responsibility, preserve targeted ruamel YAML pyright comments, and add facade exports.
4. Run provenance, alias, duplicate, suppression, hash, and invalid-pack regressions.
5. Run `mise run check`, coverage, pack validation, and schema checks if model imports move.

## Allowed changes

- Package movement, facade exports, test split, and narrowly required typing/import corrections.

## Non-goals and prohibitions

- Do not change provenance resolution, hash inputs, alias behavior, YAML format, or policy schema.
- Do not add route or database dependencies to policy.
- Do not create a second pack loader in platform services.

## Verification matrix

- Full policy/pack/CLI/platform/distribution tests.
- `mise run validate:packs`, `mise run check`, and coverage.
- Import and hash parity review.

## Completion checklist and handoff

- [ ] Every previous public policy symbol is re-exported.
- [ ] Loading, provenance, validation, and hashing have distinct owners.
- [ ] No behavior or schema changed.
- [ ] Commit with `refactor: split policy package`; open the PR without merging.
