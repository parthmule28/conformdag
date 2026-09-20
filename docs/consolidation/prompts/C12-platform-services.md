# C12 — Extract Reusable Platform Services

## Role and objective

You are the Build agent for C12. Move platform business behavior out of FastAPI route functions into reusable services for repositories, scans, baselines, and suppressions. Services must be callable by future MCP or CLI adapters without importing FastAPI.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C10–C11.
- `src/conformdag/platform/app.py` all repository/scan/baseline/suppression functions and exception mappings.
- `src/conformdag/platform/db.py`, `platform/contracts.py`, `platform/packs.py`, `platform/workspace.py`, and `tests/test_platform.py`.
- `src/conformdag/application/outcomes.py` and `application/scan.py`.

## Current ownership and resulting owner

`platform/app.py` currently owns HTTP binding, SQL query construction, mutation semantics, and status translation in the same functions. After this PR, `platform/services/repositories.py`, `scans.py`, `baselines.py`, and `suppressions.py` own domain/application operations; routes remain in `app.py` until C13 but become thin callers.

## Interfaces

Create small typed service errors:

```python
class ServiceError(Exception): ...


class NotFoundError(ServiceError): ...


class ConflictError(ServiceError): ...


class InvalidOperationError(ServiceError): ...
```

Service functions receive a SQLAlchemy `Session` or explicit session factory according to the existing transaction rule and return domain/contract-ready values, never `HTTPException`.

## Expected files

- Create: `src/conformdag/platform/services/__init__.py`, `repositories.py`, `scans.py`, `baselines.py`, `suppressions.py`, and focused service tests.
- Modify: `src/conformdag/platform/app.py` to translate service errors and call services; modify `platform/db.py` only for shared query primitives.
- Do not split route modules yet; C13 owns route files.

## Test-first sequence

1. Add service tests using real SQLite sessions for duplicate repository, missing repository/scan, queue/cancel, baseline eligibility, suppression uniqueness/expiry, and transaction failures.
2. Run the focused service tests against the current route behavior and record expected responses.
3. Extract service operations without changing HTTP status codes or response shapes.
4. Replace route SQL/business bodies with service calls and explicit exception translation.
5. Run service/platform tests, `mise run check`, coverage, and migration tests.

## Allowed changes

- Service modules, service errors, route delegation, and focused real-session tests.
- Shared persistence query helpers when at least two services need them.

## Non-goals and prohibitions

- Do not import FastAPI, Request, HTTPException, or Typer in services.
- Do not change API paths, auth policy, persistence schema, or runner orchestration.
- Do not create a generic service base class with no concrete behavior.

## Verification matrix

- Service tests without TestClient.
- HTTP tests proving status/error translation remains stable.
- Default gate, coverage, and architecture import review.
- Independent review must confirm a future MCP adapter can call services without FastAPI.

## Completion checklist and handoff

- [ ] Repository, scan, baseline, and suppression operations have one reusable owner each.
- [ ] Routes translate service errors rather than implementing SQL semantics.
- [ ] Existing HTTP behavior is preserved.
- [ ] Commit with `refactor: extract platform services`; open the PR without merging.
