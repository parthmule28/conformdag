# C13 — Split FastAPI Routes and Leave a Composition Root

## Role and objective

You are the Build agent for C13. Split the large FastAPI module into route modules while preserving exact route ordering, auth, API fallback, static SPA behavior, and service delegation. `app.py` should become composition and middleware wiring, not database business logic.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C12.
- `src/conformdag/platform/app.py:create_app` and all current route functions.
- `src/conformdag/platform/services/`, `platform/contracts.py`, `platform/packs.py`, and `platform/workspace.py`.
- `tests/test_platform.py` route ordering, API 404, auth, SPA, pagination, pack, and mutation cases.

## Current ownership and resulting owner

All route registration and handlers live in `platform/app.py`. After this PR, `platform/routes/repositories.py`, `scans.py`, `suppressions.py`, `packs.py`, and `overview.py` own HTTP binding and service invocation; `app.py` owns settings, middleware, dependency wiring, router registration, startup workspace loading, API fallback, and static mounting.

## Interfaces

- Route modules expose `APIRouter` instances or explicit registration functions accepting the existing settings/session/service dependencies.
- `create_app()` remains the public composition entry point.
- All current `/api/v1` paths, methods, response bodies, status codes, auth requirements, and fallback ordering remain stable.

## Expected files

- Create: `src/conformdag/platform/routes/__init__.py`, `repositories.py`, `scans.py`, `suppressions.py`, `packs.py`, `overview.py`.
- Modify: `src/conformdag/platform/app.py`, service imports, and platform tests.
- Do not change route contracts; C14 owns contract extraction.

## Test-first sequence

1. Add/retain route-ordering tests for specific routes before `/api/{rest:path}` and static mount, including unknown `PUT` API paths.
2. Run focused HTTP tests against the current app.
3. Move one route family at a time, registering it in the same order and translating service errors identically.
4. Inspect `app.routes` to verify the 26-route baseline and route methods after the split.
5. Run full platform tests, frontend build, packaged SPA/API smoke where available, `mise run check`, and coverage.

## Allowed changes

- Router modules, composition registration, imports, and route-focused tests.
- Small dependency factories required to make routers testable.

## Non-goals and prohibitions

- Do not put SQL queries or evaluator logic in route modules.
- Do not register fallback/static mounts before specific routes.
- Do not change auth or wire shapes under cover of a module move.

## Verification matrix

- Full platform HTTP suite and route introspection.
- Frontend build and packaged-server API/SPA checks.
- `mise run check`, coverage, and independent route-order review.

## Completion checklist and handoff

- [ ] `app.py` is a composition root with middleware/startup/mount responsibilities.
- [ ] Route families are cohesive and service-backed.
- [ ] API fallback and static mount remain last.
- [ ] Commit with `refactor: split platform routes`; open the PR without merging.
