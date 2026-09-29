# C13 FastAPI Route Split Implementation Plan

> **Execution contract:** Use `superpowers:executing-plans` in one Native / single-session implementation context. Do not use subagent-driven implementation. Execute tasks sequentially and retain useful task commits. Obtain an independent whole-branch review after implementation.

**Goal:** Split the FastAPI HTTP adapters in `src/conformdag/platform/app.py` into five cohesive route modules while preserving the exact accepted C12 HTTP behavior, route ordering, authentication, error mapping, OpenAPI operation identities, API fallback behavior, and dashboard SPA behavior.

**Approved specification:** `docs/superpowers/specs/2026-09-29-c13-fastapi-routes-design.md` at `12d812d67bc1d587a2b42832276e47c45149e6a6`.

**Architecture:** `app.py` remains the composition root. Route modules own HTTP binding and service invocation. C12 services remain authoritative for repository, scan, baseline, and suppression operations. `PackService` remains authoritative for pack/policy/gate behavior. C14 continues to own DTO/contract centralization.

**Tech stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy-backed C12 services, pytest, React/Vite packaged SPA, mise/uv.

---

## Global constraints

- Create exactly these route-family modules:

```text
src/conformdag/platform/routes/
├── __init__.py
├── repositories.py
├── scans.py
├── suppressions.py
├── overview.py
└── packs.py
```

- Preserve all 25 specific `/api/v1` route registrations.
- Preserve both API fallback registrations.
- Preserve their ordering.
- Preserve the optional dashboard `/` mount after both fallbacks.
- Keep `GET /api/v1/health` in `app.py`.
- Keep `PlatformSettings`, `load_settings()`, `create_app()`, `require_admin`, middleware, startup workspace handling, API fallback logic, and static serving in `app.py`.
- Keep the current request DTO definitions in `app.py` for C13.
- Preserve their current importability from `conformdag.platform.app`.
- Do not move request or response DTOs to `platform/contracts.py`; C14 owns that.
- Do not change path names, HTTP methods, auth requirements, validation, response shapes, error details, media types, pagination headers, or export bytes.
- Do not add SQL queries or ORM mutation logic to route modules.
- Do not modify C12 service ownership.
- Do not change `PackService` semantics.
- Do not change persistence schema or Alembic migrations.
- Do not modify runner/worker orchestration.
- Do not redesign middleware, authentication, workspace architecture, policy models, report models, or frontend contracts.
- Do not introduce a generic route framework or base-route abstraction.

---

## Registration approach

Use explicit route-family registration functions.

Each module exposes:

```python
def register_routes(app: FastAPI) -> None:
    ...
```

`src/conformdag/platform/routes/__init__.py` remains passive. It must not eagerly import every route module.

Because C13 intentionally leaves request DTOs and shared dependencies in `platform.app`, route modules may temporarily import:

```text
API_PREFIX
RepositoryCreate
WorkspaceLoadRequest
PolicyUpsertRequest
SuppressionCreate
SuppressionUpdate
BaselineSetRequest
require_admin
_factory
_register_workspace_packs
```

from `conformdag.platform.app` where required.

To keep that compatibility seam cycle-safe, `app.py` must import the route modules **inside `create_app()` after module initialization**, rather than importing them at the top of `app.py`.

This temporary `routes → app` dependency is explicitly owned by the C13→C14 boundary. Do not solve it by moving DTOs early.

Preserve existing handler function names wherever practical so FastAPI-generated operation IDs remain stable.

---

## Route-family ownership

### `routes/repositories.py`

Own:

```text
POST /api/v1/repos
POST /api/v1/workspace/load
GET  /api/v1/repos
```

Continue delegating repository operations to `platform.services.repositories`.

Workspace loading continues to use `load_workspace()` and shared workspace-pack registration.

### `routes/scans.py`

Own:

```text
POST /api/v1/repos/{repository_id}/scans
POST /api/v1/scans/{scan_id}/cancel
GET  /api/v1/scans/{scan_id}
GET  /api/v1/repos/{repository_id}/scans
PUT  /api/v1/repos/{repository_id}/baseline
GET  /api/v1/scans/{scan_id}/report
GET  /api/v1/scans/{scan_id}/findings
GET  /api/v1/scans/{scan_id}/export/{scan_format}
```

Continue delegating to:

```text
platform.services.scans
platform.services.baselines
```

Keep JSON/SARIF/HTML HTTP rendering here.

### `routes/suppressions.py`

Own:

```text
GET   /api/v1/suppressions
POST  /api/v1/suppressions
PATCH /api/v1/suppressions/{suppression_id}
```

Continue delegating to `platform.services.suppressions`.

### `routes/overview.py`

Own:

```text
GET /api/v1/overview
GET /api/v1/repos/{repository_id}/trends
```

Continue delegating to repository-service aggregate wrappers.

### `routes/packs.py`

Own:

```text
GET    /api/v1/packs
GET    /api/v1/packs/{pack_name}/policies
PUT    /api/v1/packs/{pack_name}/policies/{policy_id}
DELETE /api/v1/packs/{pack_name}/policies/{policy_id}
POST   /api/v1/packs/{pack_name}/validate
GET    /api/v1/packs/{pack_name}/gates
PUT    /api/v1/packs/{pack_name}/gates/{gate_id}
DELETE /api/v1/packs/{pack_name}/gates/{gate_id}
```

Continue using `PackService` directly as the existing HTTP adapter does.

---

## Review focus

Pay particular attention to these risks during implementation:

```text
1. Route registration order changes while moving to separate modules.
2. `/api` or `/api/{rest:path}` is registered too early.
3. Static "/" mount begins masking API routes.
4. Mutation auth is accidentally applied router-wide to read routes.
5. Handler renaming changes OpenAPI operation IDs.
6. Moving DTOs into contracts.py accidentally pulls C14 forward.
7. Top-level app ↔ routes imports create a circular import.
8. Workspace loading duplicates or changes _register_workspace_packs behavior.
9. Scan export media types or bytes change during movement.
10. Transaction commit/rollback behavior differs from C12.
11. SQL/ORM business logic leaks back into routes.
12. Pack exception translation changes during movement.
```

---

# Pre-implementation isolation

Complete this only after the C13 implementation plan itself has been reviewed and explicitly approved.

- [ ] Wait for the plan PR's exact-head CI to pass.
- [ ] Record the approved written-spec SHA:
  `12d812d67bc1d587a2b42832276e47c45149e6a6`.
- [ ] Record the approved implementation-plan SHA.
- [ ] Fetch the latest `origin/main`.
- [ ] Create a separate `feat/c13-fastapi-routes` worktree from that exact `origin/main` tip.
- [ ] Do not move, merge, or delete the docs-only specification or plan branches.
- [ ] Carry only the approved C13 specification and implementation-plan documents into the feature branch.
- [ ] Verify each carried document byte-for-byte against its approved Git blob using `git show <approved-sha>:<path>` plus `cmp`.
- [ ] Confirm no other docs changes were carried.
- [ ] Confirm the implementation worktree is clean except for the intended carried docs commit.
- [ ] Confirm `.serena/` remains untracked and untouched wherever it exists.
- [ ] Record the exact implementation base SHA.
- [ ] Run `mise run setup`.
- [ ] Begin Task 1.

---

# Task 1 — Characterize the accepted route contract before movement

**Files:**

```text
tests/test_platform.py
```

Do not create route modules yet.

## Step 1 — Add ordered custom API manifest characterization

Add a test that constructs the existing application and inspects `app.routes`.

Filter only custom routes whose path is `/api` or starts with `/api/`.

Record, in order:

```text
path
HTTP method set
route name / endpoint name where useful
```

The expected manifest must describe:

```text
25 specific /api/v1 registrations
then /api
then /api/{rest:path}
```

Do **not** assert:

```python
len(app.routes) == 26
```

because FastAPI framework routes and the conditional dashboard mount make raw route count unsuitable.

Explicitly prove that every specific `/api/v1` route precedes both fallback routes.

When the dashboard `Mount("/")` exists, prove it occurs after both API fallback registrations.

## Step 2 — Characterize operation IDs

Read the current OpenAPI document before any handler movement.

Add a focused compatibility assertion for the existing operation IDs of the 25 specific routes.

Prefer an expected mapping keyed by:

```text
(method, path) -> operationId
```

The purpose is to prevent a pure module move from silently changing client-visible OpenAPI operation identities.

Do not redesign or normalize operation IDs in this slice.

## Step 3 — Retain fallback compatibility tests

Ensure the existing tests continue to cover:

```text
GET unknown API path → JSON 404
PUT unknown API path → JSON 404
HEAD /api → 404
HEAD unknown /api/v1 path → 404
dashboard deep-link fallback
missing asset → 404
unknown API never receives SPA HTML
```

Add only missing coverage required to make ordering explicit.

## Step 4 — Run the characterization tests against the unsplit app

Run:

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'route_manifest or operation_id or unknown_api or dashboard' \
  -x --tb=short
```

The new characterization tests must pass **before** route extraction starts.

If the observed current route manifest differs from the approved C13 specification, stop and report the discrepancy instead of rewriting expected values to fit the implementation.

## Step 5 — Commit

```bash
git add tests/test_platform.py
git commit -m "test: characterize platform route contract"
```

---

# Task 2 — Create route package and extract repository routes

**Files:**

```text
Create:
src/conformdag/platform/routes/__init__.py
src/conformdag/platform/routes/repositories.py

Modify:
src/conformdag/platform/app.py
tests/test_platform.py
```

## Step 1 — Create passive route package

`routes/__init__.py` should contain only package documentation or similarly passive declarations.

It must not eagerly import the route-family modules.

## Step 2 — Move repository handlers without behavior changes

Move the existing implementations for:

```text
register_repository
load_workspace_file
list_repositories
```

into `routes/repositories.py`.

Preserve the existing function names.

The module may import the current request DTOs and shared app dependencies from `platform.app` under the approved C13 compatibility seam.

`register_routes(app)` must register the three routes in this exact relative order:

```text
POST /api/v1/repos
POST /api/v1/workspace/load
GET  /api/v1/repos
```

Preserve mutation auth at the endpoint level.

## Step 3 — Preserve C12 repository behavior

Do not alter:

```text
direct repository path validation
policy-pack file validation
repository-name validation
Airflow-profile validation
duplicate-name translation
caller commit/rollback
workspace existence-only path-kind compatibility
workspace skip-existing semantics
workspace pack registration
response bodies
status/detail mappings
```

`load_workspace_file()` must continue using the single shared `_register_workspace_packs()` owner rather than duplicating pack-registration code.

## Step 4 — Wire the module from `create_app()`

Inside `create_app()`, import the repository route module only after `platform.app` has initialized its DTOs and dependencies.

Call its registration function at the same position previously occupied by these three explicit registrations.

Do not register other route families yet.

## Step 5 — Run focused tests

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'repository or workspace or auth or route_manifest or operation_id or unknown_api' \
  -x --tb=short
```

Expected: PASS.

The route manifest and OpenAPI operation-ID characterization must remain unchanged.

## Step 6 — Commit

```bash
git add \
  src/conformdag/platform/routes/__init__.py \
  src/conformdag/platform/routes/repositories.py \
  src/conformdag/platform/app.py \
  tests/test_platform.py

git commit -m "refactor: split repository routes"
```

---

# Task 3 — Extract scan and baseline routes

**Files:**

```text
Create:
src/conformdag/platform/routes/scans.py

Modify:
src/conformdag/platform/app.py
tests/test_platform.py
```

## Step 1 — Move the existing scan-family handlers

Move, without semantic edits:

```text
trigger_scan
cancel_scan
scan_status
scan_history
set_baseline
scan_report
scan_findings
export_scan
```

Preserve handler names.

`register_routes(app)` must register them in this exact order:

```text
POST /api/v1/repos/{repository_id}/scans
POST /api/v1/scans/{scan_id}/cancel
GET  /api/v1/scans/{scan_id}
GET  /api/v1/repos/{repository_id}/scans
PUT  /api/v1/repos/{repository_id}/baseline
GET  /api/v1/scans/{scan_id}/report
GET  /api/v1/scans/{scan_id}/findings
GET  /api/v1/scans/{scan_id}/export/{scan_format}
```

## Step 2 — Preserve C12 service ownership

Continue using:

```text
scan_service.queue_scan
scan_service.cancel_scan
scan_service.scan_status
scan_service.scan_history
baseline_service.set_baseline
scan_service.load_report
scan_service.scan_findings
```

No ORM rows or SQL queries may be introduced into `routes/scans.py`.

Cancellation must continue through the existing atomic C12 service/transition path.

## Step 3 — Preserve pagination and query validation

Keep exactly:

```text
scan history limit: 1..500
scan history offset >= 0
findings limit: 1..500
findings offset >= 0
baseline_status pattern: ^(existing|new)$
```

Continue setting `X-Total-Count` in the HTTP layer using the service-returned total.

## Step 4 — Preserve report/export projection

Keep the current behavior exactly:

```text
report endpoint → canonical ScanReport JSON
JSON export → same bytes + newline
SARIF export → same sorted/indented bytes + newline
HTML export → same rendering
same media types
same unknown-format 404
same unavailable-report 404
```

Do not move rendering into the C12 service.

## Step 5 — Run focused tests

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'scan or baseline or finding or export or pagination or auth or route_manifest or operation_id or unknown_api' \
  -x --tb=short
```

Expected: PASS.

## Step 6 — Commit

```bash
git add \
  src/conformdag/platform/routes/scans.py \
  src/conformdag/platform/app.py \
  tests/test_platform.py

git commit -m "refactor: split scan routes"
```

---

# Task 4 — Extract suppression and overview routes

**Files:**

```text
Create:
src/conformdag/platform/routes/suppressions.py
src/conformdag/platform/routes/overview.py

Modify:
src/conformdag/platform/app.py
tests/test_platform.py
```

## Step 1 — Extract suppression handlers

Move:

```text
list_suppressions
create_suppression
update_suppression
```

Preserve names and exact route order:

```text
GET   /api/v1/suppressions
POST  /api/v1/suppressions
PATCH /api/v1/suppressions/{suppression_id}
```

Continue delegating to `suppression_service`.

Preserve:

```text
source/audit fields
uniqueness conflict → 409
missing suppression → 404
partial-update semantics
route-owned commit/rollback
auth requirements
```

## Step 2 — Extract overview handlers

Move:

```text
overview
repository_trends
```

into `routes/overview.py`.

Preserve route order:

```text
GET /api/v1/overview
GET /api/v1/repos/{repository_id}/trends
```

Continue using repository-service aggregate wrappers.

Do not move aggregation implementation out of `platform.aggregates`.

## Step 3 — Run focused tests

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'suppression or overview or trend or auth or route_manifest or operation_id or unknown_api' \
  -x --tb=short
```

Expected: PASS.

## Step 4 — Commit

```bash
git add \
  src/conformdag/platform/routes/suppressions.py \
  src/conformdag/platform/routes/overview.py \
  src/conformdag/platform/app.py \
  tests/test_platform.py

git commit -m "refactor: split suppression and overview routes"
```

---

# Task 5 — Extract pack, policy, and gate routes

**Files:**

```text
Create:
src/conformdag/platform/routes/packs.py

Modify:
src/conformdag/platform/app.py
tests/test_platform.py
```

## Step 1 — Move existing pack handlers

Move the current implementations corresponding to:

```text
_pack_list
_pack_policies
_pack_upsert_policy
_pack_delete_policy
_pack_validate
_pack_gates
_pack_upsert_gate
_pack_delete_gate
```

Preserve the existing endpoint function names where required for operation-ID compatibility. If the leading-underscore names are part of the current generated OpenAPI identity, retain them for C13 rather than renaming for aesthetics.

Do not redesign handler naming until a separately reviewed contract change.

## Step 2 — Preserve route order

Register exactly:

```text
GET    /api/v1/packs
GET    /api/v1/packs/{pack_name}/policies
PUT    /api/v1/packs/{pack_name}/policies/{policy_id}
DELETE /api/v1/packs/{pack_name}/policies/{policy_id}
POST   /api/v1/packs/{pack_name}/validate
GET    /api/v1/packs/{pack_name}/gates
PUT    /api/v1/packs/{pack_name}/gates/{gate_id}
DELETE /api/v1/packs/{pack_name}/gates/{gate_id}
```

These registrations must remain after overview routes and before both API fallbacks.

## Step 3 — Preserve PackService mappings exactly

Do not alter the current mappings for:

```text
PackNotFoundError
PackError
PolicyValidationError
```

Preserve the existing 404/422 distinction per operation.

Preserve policy payload `model_dump()` behavior, including existing `exclude_none` behavior where used.

Preserve gate serialization through the current `GateResponse`.

No pack/policy business logic enters `routes/packs.py`; it remains transport translation around `PackService`.

## Step 4 — Run focused tests

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'pack or policy or gate or auth or route_manifest or operation_id or unknown_api' \
  -x --tb=short
```

Expected: PASS.

## Step 5 — Commit

```bash
git add \
  src/conformdag/platform/routes/packs.py \
  src/conformdag/platform/app.py \
  tests/test_platform.py

git commit -m "refactor: split pack routes"
```

---

# Task 6 — Finish `app.py` as the composition root

**Files:**

```text
Modify:
src/conformdag/platform/app.py
src/conformdag/platform/routes/*.py
tests/test_platform.py
```

## Step 1 — Remove all moved handler bodies from `app.py`

After extraction, `app.py` must no longer define the moved family handlers.

It should retain only composition responsibilities, including:

```text
API_PREFIX
STATIC_DIR
DashboardStaticFiles
PlatformSettings
load_settings()
request DTOs intentionally retained until C14
require_admin
_factory
_register_workspace_packs
_health
create_app()
request exception handling
request logging middleware
_api_fallback
```

Remove route-family imports that became unused:

```text
C12 service modules
PackService errors used only by route handlers
report renderers used only by export
route-specific response models used only in moved handlers
```

Retain only imports genuinely needed by the composition root and request DTOs.

## Step 2 — Register route families explicitly

Inside `create_app()` register in exactly this order:

```text
health

repository routes
scan routes
suppression routes
overview routes
pack routes

/api fallback
/api/{rest:path} fallback

optional "/" dashboard static mount
```

Do not use dynamic discovery, alphabetical router iteration, or registry dictionaries whose ordering is less obvious during review.

The composition should be visually auditable.

## Step 3 — Verify no SQL/business behavior leaked into routes

Review all files under:

```text
src/conformdag/platform/routes/
```

Confirm they do not import:

```text
RepositoryRow
ScanRow
FindingRow
SuppressionRow
select
update
delete
scan_repository
worker
runner
```

A SQLAlchemy `Session` type import is unnecessary for route modules and should not be introduced unless a concrete typing need exists. Session acquisition remains through the existing app-state factory.

Do not add a generic architecture-test framework in C13; C41 owns durable architecture enforcement. Perform this as a scoped C13 audit.

## Step 4 — Verify C14 has not entered the branch

Confirm:

```text
platform/contracts.py unchanged
frontend API types unchanged
OpenAPI contract intentionally unchanged
request DTOs still owned/importable from platform.app
service return types unchanged
no new response DTOs
```

## Step 5 — Re-run exact route and OpenAPI compatibility

Run the Task 1 characterization tests again and confirm byte-for-byte/logical identity of the expected manifest.

The final ordered custom API registrations must remain:

```text
25 specific /api/v1 routes
/api fallback
/api/{rest:path} fallback
```

The optional dashboard mount must remain after them.

## Step 6 — Run the full focused C13 HTTP suite

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'route or api or dashboard or workspace or repository or scan or baseline or finding or export or suppression or overview or trend or pack or gate or auth or cors or request' \
  -x --tb=short
```

Record the exact result.

## Step 7 — Run platform tests

```bash
mise exec -- uv run pytest tests/test_platform.py -x --tb=short
```

Record the exact result.

## Step 8 — Build the SPA

```bash
mise run ui-build
```

Then re-run the dashboard/API fallback tests with built static assets present.

At minimum:

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'dashboard or unknown_api or route_manifest' \
  -x --tb=short
```

This verifies that the actual mounted dashboard does not mask the API.

## Step 9 — Run full repository gates

```bash
mise run check
mise run test:coverage
mise run schema --check
mise run build
git diff --check
```

Record:

```text
test count
skipped count
deselected count
coverage
schema result
build result
whitespace result
```

No schema diff is expected.

## Step 10 — Optional local platform-image smoke

The repository already contains the platform-image smoke in `.github/workflows/release.yml`.

If Docker is available locally, run an equivalent scoped validation:

```bash
mise run ui-build
mise run build
docker build -f deploy/Dockerfile -t conformdag-platform-smoke:local .
docker run --rm conformdag-platform-smoke:local version
docker run --rm conformdag-platform-smoke:local serve --help > /dev/null
docker run --rm conformdag-platform-smoke:local worker --help > /dev/null
docker run --rm --entrypoint python conformdag-platform-smoke:local -c \
  "import conformdag.platform.app, conformdag.platform.worker, pathlib, conformdag.platform as p; assert (pathlib.Path(p.__file__).parent / 'static' / 'index.html').is_file(), 'dashboard static assets missing'"
```

If Docker is unavailable, record that limitation. Do not block C13 solely because the existing PR CI does not run the release-only platform-image job.

## Step 11 — Final integration commit

After all local gates pass:

```bash
git add \
  src/conformdag/platform/app.py \
  src/conformdag/platform/routes \
  tests/test_platform.py

git commit -m "refactor: split platform routes"
```

Retain all useful earlier task commits.

Do not squash them merely to produce one commit.

---

# Task 7 — Implementation PR and independent review

## Step 1 — Verify feature branch before publication

Confirm:

```text
correct implementation base
approved spec carried byte-for-byte
approved plan carried byte-for-byte
only C13-scoped product/test files changed
no migration files
no frontend contract changes
no contracts.py changes
no worker/runner changes
no .serena tracking
clean worktree
```

## Step 2 — Push and open implementation PR

Push `feat/c13-fastapi-routes`.

Open a separate implementation PR against `main`.

The PR description must record:

```text
implementation base SHA
approved spec SHA
approved plan SHA
new route-module ownership
route-count correction: 25 specific + 2 fallbacks
HTTP compatibility statement
C14 explicitly deferred
local focused test result
full platform test result
mise run check result
coverage result
schema result
build result
git diff --check result
Docker/platform-image smoke result or limitation
```

Do not merge.

## Step 3 — Wait for exact implementation-head CI

Verify all required PR jobs at the exact implementation head.

Expected jobs include:

```text
Fast checks
macOS host CLI and source analysis
Browser journeys
Airflow runtime profile
Offline benchmark
Release validation
```

Semantic-provider smoke may remain skipped when the opt-in variable is not enabled.

Do not record final review evidence before the exact implementation-head CI is known.

## Step 4 — Independent whole-branch review

Obtain an independent review of the entire feature range from implementation base through the current head.

Review specifically for:

```text
route registration ordering
handler/operation-ID parity
authentication parity
validation parity
status/detail parity
transaction parity
X-Total-Count behavior
export byte/media parity
API fallback ordering
SPA/static ordering
workspace startup/load behavior
PackService exception mapping
absence of SQL/business logic in routes
absence of moved handlers in app.py
cycle-safe route loading
C12 service ownership
C14 scope containment
```

Classify findings as:

```text
Critical
Important
Minor
```

## Step 5 — Resolve review findings

All Critical and Important findings must be fixed before C13 can proceed.

For each correction:

```text
make focused change
run directly affected tests
run required full gates
commit correction
push
wait for new exact-head CI
obtain independent re-review when appropriate
```

Minor issues may be deferred only when explicitly recorded with rationale and future owner/slice.

---

# Task 8 — Record C13 review evidence

Only after:

```text
product implementation complete
exact implementation-head CI passed
independent whole-branch review completed
all Critical/Important findings resolved
re-review completed when required
```

may the progress ledger be updated.

**File:**

```text
docs/consolidation/progress.md
```

Change only the C13 row from:

```text
planned
```

to:

```text
review
```

Record:

```text
implementation PR
implementation base SHA
implementation head SHA
review-fix head SHA if applicable
approved spec SHA
approved plan SHA
focused HTTP/platform results
mise run check result
coverage
schema/build/diff checks
exact implementation-head CI
independent-review findings/resolution
scope notes
known limitations
```

Do not mark C13 `accepted` before merge and post-merge `main` CI.

Commit the ledger separately:

```bash
git add docs/consolidation/progress.md
git commit -m "docs: record C13 implementation review evidence"
```

Push it and wait for **final PR-head CI**.

If the ledger commit is the only change after the reviewed implementation head, no product re-review is required, but verify that the diff from reviewed head to final head is ledger-only.

---

# Final pre-merge state

Before reporting C13 complete for review, verify:

```text
PR remains open
PR remains unmerged
final head known
final-head CI green
spec carried exactly
plan carried exactly
25 specific routes preserved
2 API fallbacks preserved
fallbacks ordered last among /api routes
dashboard mount ordered after fallbacks when present
operation IDs preserved
auth preserved
HTTP status/details preserved
pagination headers preserved
export bytes/media preserved
app.py contains composition concerns only
five route-family modules own HTTP adapters
route modules contain no SQL business logic
C12 services remain authoritative
contracts.py unchanged
frontend contract unchanged
no schema/migration change
independent review has no unresolved Critical/Important findings
C13 ledger status = review
```

Then stop.

Do not merge.

---

# Post-merge acceptance

After explicit merge authorization and merge by the user:

1. verify the implementation merge commit;
2. wait for post-merge `main` CI;
3. verify every required job passes;
4. semantic smoke may remain skipped as configured;
5. create a separate docs-only C13 acceptance update;
6. change C13 from `review` to `accepted`;
7. record:
   - final PR head;
   - product merge commit;
   - final PR-head CI;
   - post-merge `main` CI;
   - independent-review resolution;
   - relevant limitations;
8. push the acceptance branch;
9. open the acceptance PR;
10. stop without merging unless explicitly authorized.

---

# Expected implementation commit sequence

A normal C13 implementation should retain approximately:

```text
test: characterize platform route contract
refactor: split repository routes
refactor: split scan routes
refactor: split suppression and overview routes
refactor: split pack routes
refactor: split platform routes
[optional focused review-fix commits]
docs: record C13 implementation review evidence
```

Do not rewrite useful history without a specific reason.

---

# Completion definition

The product implementation is ready for final review when:

```text
route extraction is complete;
all HTTP behavior is preserved;
route order is characterized and unchanged;
OpenAPI operation IDs are unchanged;
app.py is a composition root;
route modules contain no SQL/domain business logic;
C12 service ownership is intact;
C14 work has not entered the branch;
local verification passes;
exact implementation-head CI passes;
independent review is clean of Critical/Important findings;
final ledger-head CI passes;
the implementation PR remains open and unmerged.
```
