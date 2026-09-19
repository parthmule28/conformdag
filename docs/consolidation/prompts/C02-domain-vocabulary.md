# C02 — Correct Domain Vocabulary and Additive Policy Contract Fields

## Role and objective

You are the Build agent for C02. Remove ambiguity between `policy_id`, `check_kind`, `configuration_kind`, and `fix_kind` before new adapters and check families depend on the vocabulary. Introduce additive wire fields first and keep the current beta fields readable during the migration.

## Required reads

- `AGENTS.md`, `docs/consolidation/architecture-rules.md`, `docs/consolidation/progress.md`, and the C01 prompt.
- `src/conformdag/models.py` (`Policy`, `PolicyConfiguration`, enforcement models).
- `src/conformdag/platform/app.py` (`PolicyUpsertRequest` and pack routes).
- `src/conformdag/platform/packs.py`.
- `src/conformdag/platform/contracts.py`.
- `frontend/src/api.ts` and `frontend/src/components/policies/PolicyEditor.tsx`.
- `tests/test_platform.py`, `tests/test_models.py`, `tests/test_policy.py`, and `scripts/export_schemas.py`.

## Current ownership and resulting owner

The platform mutation request currently exposes `check_kind` and `check_config`, while the core policy model already carries typed enforcement and configuration concepts. After this PR, transport-facing policy data introduces `deterministic_checks` and `configuration`; the old fields remain a documented compatibility view until C14/C30 complete the migration. Core policy validation remains in the domain models, not the frontend.

## Interfaces

- Consumes: current `Policy` and `PolicyPack` Pydantic models and existing `/api/v1/packs/{pack_name}/policies/{policy_id}` behavior.
- Produces: additive typed request/response fields, frontend use of the new fields, and an explicit deprecation note for old names.

## Expected files

- Modify: `src/conformdag/platform/app.py`, `src/conformdag/platform/packs.py`, `src/conformdag/platform/contracts.py`, `frontend/src/api.ts`, `frontend/src/components/policies/PolicyEditor.tsx`, and related policy tests.
- Modify: `schemas/*.json` only if the Pydantic contract changes require it; run `mise run schema:update` and inspect the diff.
- Test: add focused contract cases under `tests/` using the existing platform test helpers; do not split the monolithic platform suite yet.
- Do not move route or model modules; those moves belong to C13/C14/C21.

## Test-first sequence

1. Add a test that a policy response/mutation can represent `deterministic_checks` and `configuration` while old `check_kind`/`check_config` remain readable.
2. Run the focused platform and frontend tests and confirm the new contract is absent or rejected before implementation.
3. Implement additive translation at the platform boundary; keep canonical evaluation on `Policy.enforcement.deterministic_checks` and typed configuration.
4. Update the policy editor/client to read and send the new fields without reimplementing validation.
5. Run focused tests, `mise run schema`, frontend build/tests, and `mise run check`.

## Allowed changes

- Add fields, translation helpers, deprecation documentation, and frontend migration code.
- Preserve old response fields for this release cycle and document their removal condition in `docs/compatibility.md` if that file exists; otherwise record it in the consolidation progress ledger for C30.

## Non-goals and prohibitions

- Do not rename core model fields without a compatibility facade.
- Do not let the frontend infer evaluator or fixability semantics.
- Do not introduce `family`, MCP, dbt, or speculative generic policy machinery.
- Do not alter report JSON or gate behavior.

## Verification matrix

- Focused platform policy CRUD tests and model/schema tests.
- Frontend TypeScript/build and policy editor tests.
- `mise run schema` when schemas changed.
- `mise run check`.
- Review the OpenAPI field names for ambiguity and additive compatibility.

## Completion checklist and handoff

- [ ] New fields have one documented meaning each.
- [ ] Old fields are retained only as an explicit compatibility view.
- [ ] Frontend uses the new fields and delegates validation to the server.
- [ ] Schema changes are checked in and explained.
- [ ] Commit with `feat: clarify policy and check vocabulary`; open the PR without merging.
