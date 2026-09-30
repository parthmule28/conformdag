# C14 Platform Contract Typing Implementation Plan

> **Execution contract:** Use `superpowers:executing-plans` in one Native /
> single-session implementation context. Do not use subagent-driven
> implementation. Execute tasks sequentially and retain useful task commits.
> Obtain an independent whole-branch review after implementation.

**Goal:** Centralize the stable platform HTTP request/response DTOs in
`platform/contracts.py`, remove transport-model ownership from services and
persistence helpers, and make the generated `/api/v1` OpenAPI response contract
explicit without changing valid wire JSON.

**Approved specification:** `docs/superpowers/specs/2026-09-30-c14-platform-contracts-design.md`
at `93d46e488a152868c178cd5247c14d5ec0072059`.

**Baseline for planning:** `main@f47354da12bec225d9b2ccd532d62bf1bc3a908e`.

---

## Global constraints

- Preserve all C13 routes and exact ordering.
- Preserve all C13 operation IDs.
- Preserve auth requirements.
- Preserve JSON field names and array/envelope shapes.
- Preserve `X-Total-Count`.
- Preserve policy canonical and legacy vocabulary.
- Preserve policy mutation semantics.
- Preserve C12 persistence/lifecycle behavior.
- No migration/schema change.
- No C15 security-redaction work.
- No C21 model-package decomposition.
- No C30 compatibility removal.
- No C31 generated TypeScript.
- Do not expose ORM rows.
- Do not create an OpenAPI-generation subsystem.
- Do not move transport conversion into services.

---

# Pre-implementation isolation

Only execute this section after both the spec and this plan are approved.

- [ ] Record approved C14 spec SHA.
- [ ] Record approved C14 plan SHA.
- [ ] Fetch latest `origin/main`.
- [ ] Create `feat/c14-platform-contracts` worktree from exact latest
      `origin/main`.
- [ ] Carry only the approved C14 spec and plan.
- [ ] Compare each carried document byte-for-byte with its approved Git blob.
- [ ] Confirm `.serena/` remains untouched/untracked where present.
- [ ] Confirm clean worktree except intended carried-doc commit.
- [ ] Record implementation base SHA.
- [ ] Run `mise run setup`.

---

# Task 1 — Characterize current HTTP and OpenAPI contract

**Files**

```text
tests/test_platform.py
```

## Step 1 — Preserve C13 operation-ID test

Do not replace or weaken:

```text
test_operation_id_manifest_matches_existing_api
```

The existing C13 operation-ID manifest remains a C14 compatibility gate.

## Step 2 — Add representative current JSON-shape tests

Before changing DTOs, characterize response keys and representative values for:

```text
health
repository registration/list
workspace load
scan queue/cancel/status/history
baseline
finding
suppression
overview/trends
pack summary
policy
pack validation
gate
policy mutation
gate mutation
scan report
```

Use existing fixtures/helpers rather than creating a second platform harness.

These tests should describe the current wire JSON, not implementation classes.

## Step 3 — Add RED contract-model tests

Add tests importing the intended C14 response classes from
`platform.contracts`.

Cover:

```text
HealthResponse
RepositoryRegistrationResponse
WorkspaceLoadResponse
RepositoryResponse
ScanTransitionResponse
ScanStatusResponse
ScanSummaryResponse
BaselineResponse
FindingResponse
SuppressionResponse
PackSummaryResponse
PackValidationResponse
PolicyResponse
GateResponse
PolicyMutationResponse
GateMutationResponse
OverviewResponse
RepositoryTrendsResponse
```

Assert unknown response fields are rejected.

These tests should initially fail for missing/new models or insufficiently typed
models.

## Step 4 — Add RED OpenAPI contract inspection

Add a focused test that checks intended successful response schemas and request
schemas.

Initially it should demonstrate that current route responses are not fully
described.

Also assert no ORM component names are present.

## Step 5 — Run RED evidence

Run focused tests and record the expected failures.

Commit:

```bash
git add tests/test_platform.py
git commit -m "test: characterize platform API contracts"
```

---

# Task 2 — Centralize request and response DTOs

**Files**

```text
src/conformdag/platform/contracts.py
src/conformdag/platform/app.py
tests/test_platform.py
```

## Step 1 — Add response base

Add response-only strict model:

```python
class PlatformResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Do not change request extra-field behavior globally.

## Step 2 — Move request DTO definitions

Move from `app.py` to `contracts.py`:

```text
RepositoryCreate
WorkspaceLoadRequest
PolicyUpsertRequest
SuppressionCreate
SuppressionUpdate
BaselineSetRequest
```

Preserve current class names and field behavior.

Keep `GateUpsertRequest` in `contracts.py`.

## Step 3 — Type gate rules

Change:

```python
GateUpsertRequest.rules
GateResponse.rules
```

to:

```python
list[GateRule]
```

## Step 4 — Add the complete response DTO set

Implement the response models named by the approved specification.

Refine:

```text
FindingResponse.fix → RemediationPayload | None
FindingResponse.status → FindingStatus
FindingResponse.severity → Severity
FindingResponse.baseline_status → Literal["existing", "new"] | None
PolicyVocabularyResponse.configuration → PolicyConfiguration
PolicyVocabularyResponse.check_config → PolicyConfiguration
```

Add `PolicyResponse` using stable domain submodels.

## Step 5 — App compatibility re-export

`app.py` must no longer define the moved request classes.

If preserving the historical import path, re-export them only by importing from
`platform.contracts`.

Add an explicit comment:

```text
C14 compatibility re-export.
Canonical owner: platform.contracts.
Removal/deprecation decision: C30.
```

New route code must not use these aliases.

## Step 6 — Run contract-model tests

Expected: new model tests GREEN.

Run existing policy vocabulary tests as well.

Commit:

```bash
git add \
  src/conformdag/platform/contracts.py \
  src/conformdag/platform/app.py \
  tests/test_platform.py

git commit -m "refactor: centralize platform wire contracts"
```

---

# Task 3 — Remove transport ownership from repository/scan/baseline/suppression services

**Files**

```text
src/conformdag/platform/services/repositories.py
src/conformdag/platform/services/scans.py
src/conformdag/platform/services/baselines.py
src/conformdag/platform/services/suppressions.py
tests/test_platform.py
```

## Step 1 — Repository service records

Replace response dictionaries/wire models with frozen internal records:

```text
RepositoryRegistration
RepositoryRecord
```

No `platform.contracts` import.

## Step 2 — Scan service records

Replace transport responses with typed records:

```text
ScanTransition
ScanStatusRecord
ScanSummaryRecord
FindingRecord
```

Keep `Page[T]`.

Use existing domain enums where appropriate.

Validate persisted finding fixes as `RemediationPayload` when present.

No transport contract import.

## Step 3 — Baseline record

Return a typed `BaselineAssignment`.

## Step 4 — Suppression record

Return a typed `SuppressionRecord`.

Preserve flush/conflict/transaction semantics exactly.

## Step 5 — Direct service tests

Update direct service tests to assert internal typed values rather than wire
Pydantic models/dictionaries.

HTTP JSON tests must remain unchanged.

## Step 6 — Run focused tests

Run repository/scan/baseline/suppression service and HTTP tests.

Commit:

```bash
git add \
  src/conformdag/platform/services/repositories.py \
  src/conformdag/platform/services/scans.py \
  src/conformdag/platform/services/baselines.py \
  src/conformdag/platform/services/suppressions.py \
  tests/test_platform.py

git commit -m "refactor: detach platform services from wire models"
```

---

# Task 4 — Decouple aggregates and PackService from contracts

**Files**

```text
src/conformdag/platform/aggregates.py
src/conformdag/platform/packs.py
tests/test_platform.py
```

## Step 1 — Aggregate records

Replace `TrendPoint`, `OverviewScan`, `OverviewResponse`, and
`RepositoryTrendsResponse` construction with internal aggregate records.

Suggested internal types:

```text
TrendPointData
OverviewScanData
OverviewData
RepositoryTrendsData
```

`platform.aggregates` must no longer import `platform.contracts`.

## Step 2 — Repository service aggregate return types

Update repository-service wrapper annotations to return aggregate data records,
not wire models.

## Step 3 — Pack summaries and validation

Add internal values:

```text
PackSummaryData
PackValidationResult
```

## Step 4 — Domain policy/gate reads

Change:

```text
PackService.list_policies() → list[Policy]
PackService.list_gates() → list[QualityGate]
```

Remove `PolicyVocabularyResponse` from `PackService`.

Do not change pack mutation semantics.

## Step 5 — Update direct PackService/aggregate tests

Tests of `PackService` should consume domain/internal values.

HTTP response compatibility remains separately covered at the route layer.

## Step 6 — Import audit

Verify:

```text
platform/aggregates.py → no platform.contracts
platform/packs.py      → no platform.contracts
platform/services/*    → no platform.contracts
```

Commit:

```bash
git add \
  src/conformdag/platform/aggregates.py \
  src/conformdag/platform/packs.py \
  src/conformdag/platform/services/repositories.py \
  tests/test_platform.py

git commit -m "refactor: detach platform data services from HTTP contracts"
```

---

# Task 5 — Convert route families to explicit wire models

**Files**

```text
src/conformdag/platform/routes/repositories.py
src/conformdag/platform/routes/scans.py
src/conformdag/platform/routes/suppressions.py
src/conformdag/platform/routes/overview.py
src/conformdag/platform/routes/packs.py
src/conformdag/platform/app.py
tests/test_platform.py
```

## Step 1 — Import DTOs directly from contracts

Routes must no longer import request DTOs from `platform.app`.

Keep only non-contract app dependencies required by the C13 composition seam.

## Step 2 — Repository conversion

Convert service records to:

```text
RepositoryRegistrationResponse
WorkspaceLoadResponse
RepositoryResponse
```

## Step 3 — Scan conversion

Convert service records to:

```text
ScanTransitionResponse
ScanStatusResponse
ScanSummaryResponse
BaselineResponse
FindingResponse
```

Keep:

```text
ScanReport
raw export Response
X-Total-Count
```

exactly as before.

## Step 4 — Suppression conversion

Return `SuppressionResponse`.

## Step 5 — Aggregate conversion

Map internal aggregate records to:

```text
TrendPoint
OverviewScan
OverviewResponse
RepositoryTrendsResponse
```

## Step 6 — Pack conversion

Map:

```text
PackSummaryData → PackSummaryResponse
Policy → PolicyResponse
QualityGate → GateResponse
PackValidationResult → PackValidationResponse
```

Mutation routes return the entity-specific mutation DTOs.

Canonical and legacy policy vocabulary must both derive from the same
`Policy.configuration` and `Policy.enforcement`.

## Step 7 — Health typing

Return `HealthResponse` without changing JSON.

## Step 8 — FastAPI response contract

Use explicit return annotations and/or `response_model=` so generated OpenAPI
shows the approved C14 models.

Do not change handler function names.

## Step 9 — Run HTTP parity

Run all representative HTTP characterization tests.

Every valid JSON body must match the pre-C14 characterization.

Commit:

```bash
git add \
  src/conformdag/platform/app.py \
  src/conformdag/platform/routes \
  tests/test_platform.py

git commit -m "refactor: type platform route responses"
```

---

# Task 6 — Lock the OpenAPI contract

**Files**

```text
tests/test_platform.py
```

## Step 1 — Verify request component ownership

Check the OpenAPI component references for:

```text
RepositoryCreate
WorkspaceLoadRequest
PolicyUpsertRequest
SuppressionCreate
SuppressionUpdate
BaselineSetRequest
GateUpsertRequest
```

## Step 2 — Verify success response components

Assert that all 25 specific `/api/v1` path/method operations remain present
across the existing 20 unique specific API paths.

Assert each C14 endpoint-to-contract mapping from the specification.

For arrays, assert typed array items rather than a free-form array.

## Step 3 — ORM leakage check

Assert no component is named for:

```text
RepositoryRow
ScanRow
FindingRow
SuppressionRow
ScanRow
```

and no response directly describes ORM fields outside the approved contract.

## Step 4 — `additionalProperties` inspection

Inspect the platform response DTO components.

Fail on accidental bare/free-form platform response objects.

Allow explicitly documented dynamic structures belonging to canonical
`ScanReport`/core domain models.

Do not write a blanket assertion that forbids every
`additionalProperties` occurrence in the entire OpenAPI document.

## Step 5 — Auth and pagination

Assert:

- existing mutation operations still contain the current authorization
  dependency;
- read operations did not accidentally gain mutation auth;
- history/findings remain array responses;
- `X-Total-Count` behavior remains covered by HTTP tests.

## Step 6 — Re-run C13 operation-ID manifest

Must remain byte-for-byte/logically unchanged.

Commit:

```bash
git add tests/test_platform.py
git commit -m "test: lock typed platform OpenAPI contract"
```

---

# Task 7 — Align the hand-written frontend types

**Files**

```text
frontend/src/api.ts
frontend tests only if required
```

Do not change endpoint URLs or request runtime behavior.

## Step 1 — Add stable value unions where appropriate

Introduce manual TypeScript unions for:

```text
ScanLifecycleStatus
FindingStatus
Severity
```

Use them in existing interfaces.

## Step 2 — Type remediation

Add a `RemediationPayload` interface matching the backend domain wire shape.

Use it for:

```text
Finding.fix
ReportFinding.fix
```

instead of `Record<string, unknown>`.

## Step 3 — Split mutation responses

Replace the broad optional-ID `MutationResponse` usage with:

```text
PolicyMutationResponse
GateMutationResponse
```

Update function return types only.

## Step 4 — Align request optionality

Make TypeScript request optionality match the stable backend request where the
frontend currently overstates required fields.

Do not weaken server validation or reimplement policy rules.

## Step 5 — Preserve GateRule

Keep the current discriminated `GateRule` union aligned with backend
`GateRule`.

## Step 6 — Frontend verification

Run:

```bash
cd frontend
npm test
npm run build
npm run typecheck:e2e
cd ..
```

No TypeScript generation in C14.

Commit:

```bash
git add frontend/src/api.ts frontend
git commit -m "refactor: align frontend platform contract types"
```

Only include additional frontend files if they actually required type-only
adjustments.

---

# Task 8 — Full C14 verification and architecture audit

Run:

```bash
mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'contract or openapi or repository or workspace or scan or baseline or finding or suppression or overview or trend or pack or policy or gate' \
  -x --tb=short

mise exec -- uv run pytest tests/test_platform.py -x --tb=short

cd frontend && npm test && npm run build && npm run typecheck:e2e && cd ..

mise run check
mise run test:coverage
mise run schema --check
mise run build
git diff --check
```

Record exact:

```text
focused test count
platform test count
full check count
skipped count
deselected count
coverage
frontend test count
schema result
build result
whitespace result
```

## Architecture audit

Verify:

```text
services do not import platform.contracts
aggregates does not import platform.contracts
PackService does not import platform.contracts
route DTO imports come from platform.contracts
no ORM row appears in route annotations
no request DTO definition remains in app.py
app.py compatibility aliases, if retained, point to contracts.py
C13 route order unchanged
C13 operation IDs unchanged
no migration
no core schema diff
no generated TypeScript
```

## Final integration commit

If needed:

```bash
git add \
  src/conformdag/platform \
  frontend/src/api.ts \
  tests/test_platform.py

git commit -m "refactor: type platform contracts"
```

Retain useful task commits.

---

# Task 9 — Implementation PR and independent review

Before publication verify:

```text
correct implementation base
approved spec carried exactly
approved plan carried exactly
C14 scope only
no migration
no C15/C21/C30/C31 work
.serena untouched
clean worktree
```

Push `feat/c14-platform-contracts`.

Open an implementation PR against `main`.

Record in PR body:

```text
implementation base SHA
approved spec SHA
approved plan SHA
contracts.py ownership
service/aggregate/PackService decoupling
request compatibility re-export policy
OpenAPI contract coverage
JSON parity
frontend type alignment
local verification counts
coverage
schema/build results
known limitations
```

Do not merge.

Wait for exact implementation-head CI.

Obtain an independent whole-branch review focused on the approved spec.

All Critical and Important findings must be fixed.

After fixes:

```text
focused tests
full gates
push
new exact-head CI
independent re-review when required
```

---

# Task 10 — Review ledger

Only after:

```text
product implementation complete
implementation-head CI green
independent review complete
all Critical/Important findings resolved
```

change only the C14 ledger row:

```text
planned → review
```

Record:

```text
PR
base
implementation head
fix head if any
approved spec/plan
JSON/OpenAPI evidence
frontend evidence
full local gates
coverage
exact-head CI
independent-review result
scope rulings/limitations
```

Commit separately:

```bash
git add docs/consolidation/progress.md
git commit -m "docs: record C14 implementation review evidence"
```

Push and wait for final PR-head CI.

Verify the delta from reviewed product head to final head is ledger-only.

Stop with the PR open and unmerged.

---

# Post-merge acceptance

After explicit merge authorization:

1. verify product merge commit;
2. verify post-merge `main` CI;
3. create docs-only C14 acceptance branch;
4. change C14 from `review` to `accepted`;
5. record product final head, merge commit, final-head CI, post-merge CI,
   review resolution, and limitations;
6. open acceptance PR;
7. stop unmerged unless separately authorized.

---

# Completion definition

C14 is complete when:

```text
contracts.py owns all platform DTO definitions
request definitions are gone from app.py
ordinary JSON responses are explicitly typed
ScanReport remains canonical
GateRule is used for gate transport
RemediationPayload is used for finding fix transport
services do not depend on wire contracts
aggregates do not depend on wire contracts
PackService does not depend on wire contracts
routes perform explicit domain/service → wire conversion
OpenAPI contains no ORM schemas
OpenAPI contains no accidental free-form platform response models
C13 operation IDs/order/auth remain unchanged
valid JSON is compatible
frontend manual types match
C31 generation remains deferred
local gates pass
exact-head CI passes
independent review is clean of unresolved Critical/Important findings
ledger status is review
implementation PR remains open and unmerged
```
