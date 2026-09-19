# C31 — Generate TypeScript API Types from OpenAPI

## Role and objective

You are the Build agent for C31. Remove manual backend/frontend wire-type duplication by generating TypeScript types from the stable FastAPI OpenAPI document while keeping the handwritten client transport helpers.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C13/C14/C30.
- `src/conformdag/platform/app.py`/routes, `platform/contracts.py`, `frontend/src/api.ts`, `frontend/package.json`, `mise.toml`, and frontend tests.
- Existing build/package/CI workflows and generated-schema conventions.

## Current ownership and resulting owner

The backend Pydantic contracts and `frontend/src/api.ts` manually duplicate many response interfaces. After this PR, generated `frontend/src/generated/api-schema.ts` owns backend-derived TypeScript types; `api.ts` continues to own base URL, auth headers, request helpers, pagination, `ApiError`, and endpoint convenience functions.

## Interfaces

Add a reproducible `mise run api-types` generation command and a check mode that fails when generated output differs. The generation input is the FastAPI OpenAPI JSON; UI-specific view models remain handwritten.

## Expected files

- Create: `frontend/src/generated/api-schema.ts` and the chosen dev-only generator configuration/script.
- Modify: `frontend/src/api.ts`, `frontend/package.json`, `mise.toml`, CI workflow, frontend tests, and docs for regeneration.
- Do not add a production runtime dependency for generation.

## Test-first sequence

1. Add a generation/check script test or CI command that detects stale generated output.
2. Run it before adding generated types and confirm the check fails or the file is absent.
3. Generate types from the current OpenAPI and migrate endpoint interfaces without changing runtime requests.
4. Run frontend typecheck/build/Vitest and backend OpenAPI/platform tests.
5. Run `mise run api-types --check` (or the exact project task), `mise run check`, and packaged SPA smoke.

## Allowed changes

- Dev-only type generator, generated file, client type imports, CI/task wiring, and tests.

## Non-goals and prohibitions

- Do not generate a full client that replaces handwritten transport/error/auth logic.
- Do not make generated UI types authoritative for domain behavior.
- Do not change endpoint payload semantics under cover of type generation.

## Verification matrix

- OpenAPI generation drift check.
- Frontend build/typecheck/Vitest, backend contract tests, and Playwright where relevant.
- Package build includes no generator-only runtime dependency.

## Completion checklist and handoff

- [ ] Generated types match the checked-in OpenAPI contract.
- [ ] `api.ts` retains transport/auth/error ownership.
- [ ] CI detects stale generated output.
- [ ] Commit with `build: generate frontend API types`; open the PR without merging.
