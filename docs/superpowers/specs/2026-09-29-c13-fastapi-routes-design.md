# C13 FastAPI Route Split Design

**Status:** Design specification  
**Baseline:** `main@6b5122aa5a9d439b503eee37955ebcb3791f62e6`  
**Predecessor:** C12 — Extract Reusable Platform Services  
**Next boundary:** C14 — Complete Platform Contract Typing

## Objective

Split the large `src/conformdag/platform/app.py` FastAPI module into cohesive route modules while preserving the existing `/api/v1` HTTP contract exactly.

After C13:

- route modules own HTTP request/response binding, service invocation, transport error translation, pagination headers, and endpoint-specific rendering;
- `app.py` is the composition root and owns settings, middleware, application state, startup workspace handling, shared authentication wiring, route-family registration order, API fallback registration, and static dashboard mounting;
- C12 platform services remain the owners of repository, scan, baseline, and suppression persistence/business operations;
- pack behavior remains owned by the existing `PackService`;
- no platform DTO or OpenAPI redesign occurs in this slice.

This is an architectural extraction, not a behavior change.

---

## Current state

C12 removed repository, scan, baseline, and suppression persistence logic from FastAPI handlers and placed it behind reusable platform services.

`platform/app.py` still owns:

- platform settings and environment loading;
- request DTO definitions;
- admin authentication;
- middleware and error handling;
- startup workspace loading and pack registration;
- all HTTP handler functions;
- all route registration;
- API fallback behavior;
- dashboard SPA/static behavior.

The remaining problem is structural: route-family HTTP behavior still lives in one large module.

C13 separates those HTTP adapters without changing their public behavior.

---

## Resulting ownership

### `platform/app.py`

`app.py` remains the public platform composition entry point and owns:

- `PlatformSettings`;
- `load_settings()`;
- `create_app()`;
- application-state initialization;
- session-factory installation in `app.state`;
- `PackService` installation in `app.state`;
- CORS configuration;
- request-ID logging middleware;
- unhandled-request error logging;
- `require_admin`;
- startup workspace loading;
- shared workspace-pack registration used by startup and the workspace-load endpoint;
- health binding;
- route-family registration order;
- `/api` fallback registration;
- `/api/{rest:path}` fallback registration;
- `DashboardStaticFiles`;
- SPA/static mounting.

`app.py` must not retain repository, scan, baseline, suppression, overview, trend, policy, or gate endpoint implementations after the split.

The request DTO definitions intentionally remain in `app.py` during C13. C14 owns moving all platform request/response DTOs into `platform/contracts.py`.

### Route modules

Create:

```text
src/conformdag/platform/routes/
├── __init__.py
├── repositories.py
├── scans.py
├── suppressions.py
├── overview.py
└── packs.py
```

Each route module owns only HTTP-adapter concerns for its family.

Route modules may:

- bind FastAPI parameters and request DTOs;
- access dependencies installed in `request.app.state`;
- invoke C12 services or `PackService`;
- commit or roll back caller-owned ordinary service transactions exactly as before;
- translate typed service errors into the existing HTTP statuses/details;
- set HTTP headers;
- render endpoint-specific response formats.

Route modules must not:

- issue SQL queries directly;
- mutate SQLAlchemy rows directly;
- own evaluator or policy-governance rules;
- create a second application workflow;
- alter request or response contracts.

---

## Route-family ownership

| Module | Routes |
| --- | --- |
| `repositories.py` | `POST /api/v1/repos`, `POST /api/v1/workspace/load`, `GET /api/v1/repos` |
| `scans.py` | `POST /api/v1/repos/{repository_id}/scans`, `POST /api/v1/scans/{scan_id}/cancel`, `GET /api/v1/scans/{scan_id}`, `GET /api/v1/repos/{repository_id}/scans`, `PUT /api/v1/repos/{repository_id}/baseline`, `GET /api/v1/scans/{scan_id}/report`, `GET /api/v1/scans/{scan_id}/findings`, `GET /api/v1/scans/{scan_id}/export/{scan_format}` |
| `suppressions.py` | `GET /api/v1/suppressions`, `POST /api/v1/suppressions`, `PATCH /api/v1/suppressions/{suppression_id}` |
| `overview.py` | `GET /api/v1/overview`, `GET /api/v1/repos/{repository_id}/trends` |
| `packs.py` | pack listing, policy CRUD/validation, and quality-gate CRUD |
| `app.py` | `GET /api/v1/health`, API fallbacks, middleware, composition, static mount |

The baseline endpoint belongs to `scans.py` for C13 because it operates on scan lifecycle state and delegates to the existing baseline service. Do not introduce a sixth `baselines.py` route module.

Workspace loading remains in `repositories.py`. Workspace parsing and startup orchestration remain owned by their existing layers; C13 does not redesign workspace architecture.

---

## Registration strategy

Each route-family module exposes an explicit registration function rather than relying on one aggregated router whose inclusion could obscure route ordering.

Conceptually:

```python
def register_routes(app: FastAPI, ...) -> None:
    ...
```

`create_app()` explicitly calls the family registration functions in the required order.

This is preferred over a generic route framework because:

- route ordering is a product compatibility requirement;
- the current endpoint families are small and explicit;
- the split should remain mechanically reviewable;
- C13 must not introduce abstraction unrelated to route ownership.

`routes/__init__.py` must not eagerly import every route module if doing so creates an initialization cycle with the request DTOs still owned by `app.py`.

Route modules may temporarily import the existing request DTO definitions from `platform.app`. This is an explicit C13→C14 compatibility seam. `app.py` must import/register route modules only after its request DTOs and shared dependencies are initialized so no import-time cycle is introduced.

C14 removes this transitional DTO dependency by moving wire models into `platform/contracts.py`.

---

## Exact route-order contract

Route registration order is behaviorally significant because the generic API fallback and static root mount can intercept later routes.

C13 must preserve this sequence:

```text
1.  GET    /api/v1/health

2.  POST   /api/v1/repos
3.  POST   /api/v1/workspace/load
4.  GET    /api/v1/repos

5.  POST   /api/v1/repos/{repository_id}/scans
6.  POST   /api/v1/scans/{scan_id}/cancel
7.  GET    /api/v1/scans/{scan_id}
8.  GET    /api/v1/repos/{repository_id}/scans
9.  PUT    /api/v1/repos/{repository_id}/baseline
10. GET    /api/v1/scans/{scan_id}/report
11. GET    /api/v1/scans/{scan_id}/findings
12. GET    /api/v1/scans/{scan_id}/export/{scan_format}

13. GET    /api/v1/suppressions
14. POST   /api/v1/suppressions
15. PATCH  /api/v1/suppressions/{suppression_id}

16. GET    /api/v1/overview
17. GET    /api/v1/repos/{repository_id}/trends

18. GET    /api/v1/packs
19. GET    /api/v1/packs/{pack_name}/policies
20. PUT    /api/v1/packs/{pack_name}/policies/{policy_id}
21. DELETE /api/v1/packs/{pack_name}/policies/{policy_id}
22. POST   /api/v1/packs/{pack_name}/validate
23. GET    /api/v1/packs/{pack_name}/gates
24. PUT    /api/v1/packs/{pack_name}/gates/{gate_id}
25. DELETE /api/v1/packs/{pack_name}/gates/{gate_id}

26. /api fallback
27. /api/{rest:path} fallback

28. optional dashboard "/" static mount, when built assets exist
```

The two fallback routes support the existing method set:

```text
GET
HEAD
POST
PATCH
PUT
DELETE
```

No specific API route may be registered after either fallback.

The static dashboard mount must remain after both fallbacks.

---

## C13 prompt route-count correction

The original C13 prompt references a “26-route baseline.”

That count is stale relative to the accepted C12 `main` baseline.

Current `main@6b5122a` registers:

- 25 specific `/api/v1` routes;
- 2 explicit API fallback routes.

Therefore the current custom `/api*` manifest contains **27 registrations**.

FastAPI also installs framework documentation/OpenAPI routes, and the dashboard mount is conditional on built static assets. Raw `len(app.routes)` is therefore not an appropriate compatibility assertion.

C13 must characterize and preserve the exact ordered custom `/api*` route manifest from current `main`; it must not remove, merge, rename, or otherwise alter a route merely to satisfy the stale count in the prompt.

---

## HTTP compatibility contract

C13 must preserve all existing externally visible behavior.

This includes:

### Paths and methods

No path or method changes.

### Authentication

The same mutation routes remain protected by the existing `require_admin` dependency.

The same read routes remain unauthenticated.

Existing behavior remains:

- missing configured admin token → `503`;
- missing/incorrect bearer token → `401`;
- successful authorized mutation behavior unchanged.

Do not introduce router-wide authentication that accidentally protects read routes.

### Validation

Existing Pydantic/FastAPI validation remains unchanged, including:

- repository name validation;
- Airflow profile validation;
- pagination limits;
- baseline-status query pattern;
- suppression payload validation;
- policy/gate payload validation.

C14 owns DTO consolidation and stronger contract typing.

### Error mapping

Preserve exact existing HTTP status/detail behavior, including C12 service-error translation.

Examples include:

```text
repository not registered
repository name already registered
scan not found
scan already {status}
scan report not available
scan not found for this repository
scan is not eligible as a baseline: it must be a succeeded, complete scan
suppression already exists for this policy finding
suppression not found
export format must be json, sarif, or html
```

Pack error and policy-validation mappings remain unchanged.

### Pagination

`X-Total-Count` remains set by the route layer for:

- repository scan history;
- scan findings.

Service-level filtered totals remain authoritative.

### Export behavior

`scans.py` owns the HTTP projection of the canonical report for export.

Preserve byte/media behavior for:

- JSON;
- SARIF;
- HTML.

`ScanReport` retrieval remains delegated to the C12 scan service.

### Middleware and CORS

C13 must not change:

- request-ID generation or echo;
- request logging;
- unexpected-error handling;
- configured CORS origins;
- exposed `X-Total-Count`;
- middleware registration.

These remain in `app.py`.

### SPA and fallback behavior

Preserve:

- dashboard index at `/`;
- SPA deep-link fallback;
- missing static assets returning 404;
- unknown API paths returning JSON 404 rather than SPA HTML;
- unknown `PUT` API paths returning the API fallback 404;
- unknown `HEAD` `/api*` requests not falling into the dashboard.

---

## Request DTO boundary

These request DTOs remain defined and importable from `platform.app` throughout C13:

```text
RepositoryCreate
WorkspaceLoadRequest
PolicyUpsertRequest
SuppressionCreate
SuppressionUpdate
BaselineSetRequest
```

Also preserve existing public imports for:

```text
PlatformSettings
load_settings
create_app
```

Do not move these models into `platform/contracts.py` during C13.

Do not redesign response models or raw dictionary responses during C13.

C14 owns:

- centralized platform request DTOs;
- centralized response DTOs;
- OpenAPI response-model typing;
- explicit domain-to-wire conversion;
- frontend contract alignment.

---

## Workspace behavior

The HTTP workspace-load route moves to `routes/repositories.py`, but workspace semantics do not move.

Preserve the C12 compatibility distinction:

- direct repository registration retains strict repository-directory and policy-pack-file checks;
- workspace-loaded repositories retain the existing workspace existence-only path-kind behavior.

The route continues to:

1. call `load_workspace()`;
2. register workspace policy packs using the existing shared pack-registration behavior;
3. delegate repository persistence to `repository_service.register_workspace_repositories()`;
4. commit through the caller-owned session;
5. return the existing repository count shape.

Startup workspace loading remains entirely in `create_app()`.

Do not duplicate the shared workspace-pack registration logic between startup and the workspace-load endpoint.

---

## Service and transaction boundaries

C13 must preserve C12 ownership.

### Repository routes

Delegate persistence/query behavior to `platform.services.repositories`.

### Scan routes

Delegate scan lifecycle and reads to `platform.services.scans`.

Cancellation must continue using the C12 service, which invokes the existing atomic transition primitive.

### Baseline route

Delegate to `platform.services.baselines`.

### Suppression routes

Delegate to `platform.services.suppressions`.

Ordinary caller-owned commit/rollback behavior remains unchanged.

### Overview routes

Delegate to repository-service aggregate wrappers.

Aggregation implementation remains in `platform.aggregates`.

### Pack routes

Continue using the existing `PackService`.

Do not create a duplicate platform pack service or move policy-editing semantics into route modules.

---

## Test-first requirements

Before moving route handlers, add a characterization test against the current application.

The route-manifest characterization must assert, in order:

- each custom `/api*` path;
- its HTTP method set;
- the two API fallback registrations after all 25 specific routes;
- the static mount, when present, after the API fallbacks.

Do not assert a raw total `len(app.routes) == 26`.

Also characterize existing OpenAPI operation IDs for the moved routes or preserve the current handler names so the module move does not silently rename generated operation IDs.

Retain or strengthen tests for:

- unknown GET API path → JSON 404;
- unknown PUT API path → JSON 404;
- unknown HEAD API/root path behavior;
- dashboard index;
- dashboard deep links;
- missing static assets;
- read-route authentication;
- mutation-route authentication;
- repository registration/workspace behavior;
- scan lifecycle;
- scan history ordering and total header;
- finding filtering/pagination and total header;
- baseline behavior;
- report/export behavior;
- suppressions;
- overview/trends;
- pack policy CRUD;
- pack gate CRUD;
- policy/gate validation error mapping;
- startup workspace registration;
- CORS;
- request logging/error middleware.

Existing platform HTTP tests remain the behavioral compatibility source of truth.

---

## Extraction sequence

Move route families incrementally in this order:

```text
1. Characterize current ordered route manifest.
2. Create routes package and shared registration structure.
3. Move repository/workspace routes.
4. Move scan/baseline/report/finding/export routes.
5. Move suppression routes.
6. Move overview/trend routes.
7. Move pack/policy/gate routes.
8. Remove moved handlers and now-unused service/rendering imports from app.py.
9. Verify exact route manifest and fallback/static ordering.
10. Run the complete verification gate.
```

At every intermediate step the application must remain runnable and route behavior must remain compatible.

---

## `app.py` completion shape

After C13, `app.py` should contain composition concerns such as:

```text
settings
environment loading
request DTOs temporarily retained for C14
admin auth dependency
session/app-state wiring
DashboardStaticFiles
workspace startup
shared workspace-pack registration
health
exception handling
request logging middleware
route-family registration
API fallback
static mount
create_app()
```

It should no longer contain the implementation bodies for:

```text
repository endpoints
workspace HTTP endpoint
scan endpoints
baseline endpoint
report/findings/export endpoints
suppression endpoints
overview/trends endpoints
pack/policy/gate endpoints
```

The presence of request DTOs in `app.py` is intentional and is not a C13 defect.

---

## Architecture constraints

Route modules must not import or use:

```text
RepositoryRow
ScanRow
FindingRow
SuppressionRow
SQLAlchemy select/update/delete query construction
core evaluators
scan_repository()
runner/worker orchestration
```

The route layer may depend on:

```text
FastAPI transport types
platform request/response contracts
C12 platform services
PackService
report projection functions for export
workspace loader at the HTTP adapter boundary
```

No new generic route framework, repository abstraction, service facade, or transport base class is introduced.

---

## Allowed changes

C13 may change:

- `src/conformdag/platform/app.py`;
- `src/conformdag/platform/routes/__init__.py`;
- `src/conformdag/platform/routes/repositories.py`;
- `src/conformdag/platform/routes/scans.py`;
- `src/conformdag/platform/routes/suppressions.py`;
- `src/conformdag/platform/routes/overview.py`;
- `src/conformdag/platform/routes/packs.py`;
- route-focused tests in `tests/test_platform.py`.

A very small route dependency/helper abstraction is allowed only when it removes genuine repeated transport wiring and does not introduce domain behavior.

---

## Explicit non-goals

C13 does not include:

- contract/DTO centralization;
- new response models;
- OpenAPI redesign;
- generated TypeScript;
- frontend API redesign;
- SQL/service redesign;
- pack-editing redesign;
- policy-model changes;
- workspace architecture changes;
- middleware redesign;
- authentication redesign;
- schema changes;
- Alembic migrations;
- runner or worker changes;
- scan workflow changes;
- report model changes;
- C14 work.

If implementation reveals one of those changes is required for correctness, stop and amend/review the C13 specification rather than silently expanding scope.

---

## Verification

Run at minimum:

```bash
mise run setup

mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'route or api or dashboard or workspace or repository or scan or baseline or finding or export or suppression or overview or trend or pack or gate or auth or cors or request' \
  -x --tb=short

mise run ui-build
mise run check
mise run test:coverage
mise run schema --check
git diff --check
```

Also run the existing packaged server/API/SPA smoke path if one is already available in the repository or CI. Do not create a new infrastructure subsystem solely for C13.

Perform an architecture audit that confirms:

```text
platform/routes/*.py contains no SQL business queries;
app.py contains no moved route-family handlers;
all specific /api/v1 routes precede API fallback;
both API fallback routes precede static mounting;
C12 services remain the owners of persistence/business behavior;
no C14 contract work entered the branch.
```

Obtain an independent whole-branch review focused on:

- route registration ordering;
- auth parity;
- HTTP status/detail parity;
- OpenAPI/operation-ID accidental changes;
- fallback behavior;
- SPA/static behavior;
- absence of SQL/business logic in route modules;
- C12 service delegation;
- C14 scope containment.

Fix all Critical and Important findings before final review evidence is recorded.

---

## Delivery workflow

Use the established docs/implementation approval process.

For the written-spec phase:

```text
1. Materialize this specification exactly.
2. Create a docs-only C13 spec branch from current origin/main.
3. Commit only the C13 specification.
4. Push the branch.
5. Open a docs-only PR.
6. Verify the remote head and exact-head CI.
7. Stop.
```

Do not write the C13 implementation plan yet unless the written specification has been approved.

Do not begin product implementation from the specification PR.

After written-spec approval, a separate implementation plan will define the task-level execution sequence and implementation worktree contract.

---

## Completion criteria

C13 is complete only when:

- the five route-family modules own their intended HTTP adapters;
- `app.py` is reduced to composition/middleware/startup/fallback/static responsibilities plus request DTOs intentionally deferred to C14;
- all 25 specific `/api/v1` routes remain present;
- both API fallback registrations remain present after all specific routes;
- the static mount remains last when present;
- paths, methods, auth, statuses, details, headers, response bodies, exports, and SPA behavior remain compatible;
- route modules contain no SQL business logic;
- C12 services remain authoritative;
- C14 contract work remains untouched;
- all required local gates pass;
- exact-head CI passes;
- independent whole-branch review has no unresolved Critical or Important findings;
- the implementation PR remains unmerged pending explicit authorization.
