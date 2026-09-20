# C14 — Complete Platform Contract Typing

## Role and objective

You are the Build agent for C14. Centralize all platform request and response DTOs and make the stable `/api/v1` OpenAPI contract explicit without leaking ORM rows or dynamic dictionaries where a typed shape is possible.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C02/C13.
- `src/conformdag/platform/app.py` request models and route return shapes.
- `src/conformdag/platform/contracts.py`, `platform/routes/`, `platform/services/`, and `src/conformdag/models.py`.
- `frontend/src/api.ts`, current generated schemas, and platform contract tests.

## Current ownership and resulting owner

Some request models live in `app.py`, while response models are split between `contracts.py` and raw dictionaries. After this PR, `platform/contracts.py` owns request/response wire models; routes bind them and services return domain values that routes convert explicitly.

## Interfaces

Add or centralize typed models for repository, scan transition/status, baseline, suppression, policy, gate, finding, and mutation responses. Use `list[GateRule]` rather than raw gate dictionaries. Keep genuinely dynamic remediation payloads typed as their domain model or an explicitly bounded mapping.

## Expected files

- Modify: `src/conformdag/platform/contracts.py`, `platform/routes/*.py`, and `platform/services/*.py`.
- Remove request-model definitions from `platform/app.py` after imports are updated.
- Modify: `frontend/src/api.ts`, frontend types, `tests/test_platform.py`, and schema/OpenAPI checks.
- Do not generate TypeScript types yet; C31 consumes the stable OpenAPI output.

## Test-first sequence

1. Add response-model tests for repository, scan, baseline, suppression, mutation, finding, and gate shapes; assert unknown fields are rejected where intended.
2. Add an OpenAPI snapshot/inspection test for required paths, auth, response models, and no accidental ORM schemas.
3. Move request models and annotate route responses without changing JSON fields or array envelopes.
4. Update frontend client types only enough to match the stable contract; C31 replaces manual duplication later.
5. Run platform, schema, frontend build, `mise run check`, and coverage.

## Allowed changes

- Contract models, route annotations, explicit domain-to-wire conversion, and contract tests.
- Additive response fields only when documented and backward compatible.

## Non-goals and prohibitions

- Do not expose SQLAlchemy rows, internal `Policy` objects, or arbitrary `dict[str, Any]` as the default response model.
- Do not change endpoint paths, auth, pagination, fallback ordering, or policy mutation semantics.
- Do not make the frontend authoritative for server decisions.

## Verification matrix

- HTTP contract and OpenAPI tests.
- Existing platform/pack/schema tests and frontend build.
- `mise run check`, coverage, and schema synchronization.
- Review generated OpenAPI for `additionalProperties` leaks.

## Completion checklist and handoff

- [ ] All platform request/response DTOs have one owner.
- [ ] OpenAPI describes stable response shapes.
- [ ] Existing clients remain compatible.
- [ ] Commit with `refactor: type platform contracts`; open the PR without merging.
