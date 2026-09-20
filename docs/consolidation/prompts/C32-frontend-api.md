# C32 — Clean the Frontend API Surface

## Role and objective

You are the Build agent for C32. Remove redundant frontend wrappers and backend-domain duplication while preserving server-authoritative semantics and the generated API type boundary from C31.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C31.
- `frontend/src/api.ts`, generated API types, query hooks/components, `frontend/src/pages/`, policy/gate/suppression UI, and frontend tests.
- Backend contracts and platform tests for routes used by the client.

## Current ownership and resulting owner

`updatePolicy()` wraps `upsertPolicy()` without an independent contract, and UI helpers may duplicate server eligibility/gate/suppression decisions. After this PR, endpoint functions are one-to-one with server operations; UI-only convenience predicates are clearly presentation helpers and never replace server validation.

## Interfaces

Preserve `request()`, `requestPage()`, `ApiError`, auth/token behavior, query-string encoding, and endpoint return types. Remove `updatePolicy()` only after all callers use `upsertPolicy()` and tests prove no public client import requires the alias, or retain it as an explicit deprecated wrapper documented in C30.

## Expected files

- Modify: `frontend/src/api.ts`, query hooks/callers, policy/gate/suppression pages/components, generated type imports, and frontend tests.
- Modify: backend only if a contract mismatch is proven; do not add frontend-driven domain logic.

## Test-first sequence

1. Add client tests for endpoint request methods, payloads, error mapping, pagination, and policy update behavior.
2. Search all callers of redundant wrappers and server-duplicating predicates.
3. Migrate callers, remove or deprecate wrappers, and annotate UX-only predicates as non-authoritative.
4. Run frontend Vitest/typecheck/build and backend contract tests.
5. Run packaged-server Playwright journeys and `mise run check` where frontend gates are included.

## Allowed changes

- Client API cleanup, generated type adoption, caller migration, tests, and comments documenting server authority.

## Non-goals and prohibitions

- Do not reimplement gate, suppression, baseline, policy compatibility, or authorization semantics in React.
- Do not change backend endpoint shapes without a separate contract decision.
- Do not remove a public wrapper without compatibility evidence.

## Verification matrix

- Frontend Vitest/typecheck/build.
- Backend OpenAPI/platform tests and packaged Playwright journeys.
- Search-based review for duplicated server decisions.

## Completion checklist and handoff

- [ ] One client function represents each backend operation.
- [ ] Generated types are used for wire shapes.
- [ ] Server remains authoritative for governance decisions.
- [ ] Commit with `refactor: simplify frontend API client`; open the PR without merging.
