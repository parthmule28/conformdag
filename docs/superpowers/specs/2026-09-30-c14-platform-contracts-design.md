# C14 Platform Contract Typing Design

**Status:** Design specification
**Baseline:** `main@f47354da12bec225d9b2ccd532d62bf1bc3a908e`
**Predecessor:** C13 — Split FastAPI Routes and Leave a Composition Root
**Next boundary:** C15 — Centralize Security Redaction

## Objective

Make `src/conformdag/platform/contracts.py` the single owner of the stable
`/api/v1` request and response wire models.

C14 must make the FastAPI/OpenAPI contract explicit without changing the
existing HTTP product behavior.

After C14:

- all platform request DTO definitions live in `platform/contracts.py`;
- all ordinary JSON response shapes have explicit typed response models;
- FastAPI routes bind wire DTOs and explicitly convert service/domain values
  into response DTOs;
- repository, scan, baseline, suppression, aggregate, and pack services do not
  depend on `platform.contracts`;
- SQLAlchemy rows are never exposed through the HTTP contract;
- `GateRule` is used for quality-gate request and response rules rather than
  free-form gate dictionaries;
- finding remediation/fix payloads use the existing typed
  `RemediationPayload`;
- valid endpoint JSON, paths, methods, authentication, pagination, route
  ordering, operation IDs, policy mutation semantics, and error status mappings
  remain compatible;
- the hand-written frontend client remains aligned with the explicit backend
  contract;
- TypeScript generation remains deferred to C31.

This slice establishes a typed transport boundary. It does not redesign the
underlying product domain.

---

## Current state

C13 established five HTTP route modules:

```text
platform/routes/
├── repositories.py
├── scans.py
├── suppressions.py
├── overview.py
└── packs.py
```

`platform/app.py` is now the composition root.

The remaining contract problems are:

1. request DTOs are still defined in `platform/app.py`;
2. only some response shapes have Pydantic models;
3. many routes return untyped dictionaries;
4. C12 services construct or return wire models in several places;
5. `platform.aggregates` directly constructs transport response models;
6. `PackService` uses a transport response model to create policy dictionaries;
7. gate rules are still represented as `list[dict[str, Any]]` in the backend
   transport contract;
8. finding fixes use an unbounded dictionary despite the existing
   `RemediationPayload` domain model;
9. most FastAPI responses therefore have incomplete OpenAPI schemas.

C14 corrects those ownership violations without changing the wire JSON.

---

## Ownership after C14

### `platform/contracts.py`

Sole owner of platform HTTP DTO definitions:

- request bodies;
- ordinary JSON response bodies;
- transport-only compatibility fields;
- wire-level response validation.

It may depend on stable core/domain types such as:

```text
LifecycleStatus
Severity
FindingStatus
PolicyConfiguration
Ownership
PolicyScope
ExceptionPolicy
EnforcementConfig
GateRule
RemediationPayload
ScanReport
ScanStatus
```

Core/domain packages must not depend on platform contracts.

### `platform/routes/*.py`

Own:

- FastAPI request/query/path/header binding;
- auth dependency binding;
- service invocation;
- service/domain → wire DTO conversion;
- HTTP exception translation;
- `X-Total-Count`;
- report/export projection;
- response-model declarations.

Routes do not own persistence or domain validation.

### `platform/services/*.py`

Own typed persistence/application results independent of HTTP.

Services must not import `platform.contracts`.

When a service needs a structured return value that is not already a domain
model, use a small frozen dataclass local to the appropriate service module.

### `platform/aggregates.py`

Owns aggregate query calculation only.

It must return aggregate data/domain records, not HTTP response models.

### `platform/packs.py`

`PackService` owns pack discovery, reading, validation, and mutation.

It must not depend on `platform.contracts`.

For reads:

- policies should be returned as domain `Policy` values;
- gates should be returned as domain `QualityGate` values;
- pack summaries and validation results should use small internal typed values.

The HTTP route converts these to transport DTOs.

---

## Request DTO migration

Move these existing definitions from `platform/app.py` into
`platform/contracts.py`:

```text
RepositoryCreate
WorkspaceLoadRequest
PolicyUpsertRequest
SuppressionCreate
SuppressionUpdate
BaselineSetRequest
```

`GateUpsertRequest` already lives in `contracts.py`.

Preserve the existing class names so OpenAPI component naming and Python-facing
compatibility remain as stable as possible.

### Compatibility import path

C14 removes the **definitions** from `platform.app`.

For compatibility, `platform.app` may re-export the moved request DTO names by
importing them from `platform.contracts`.

That re-export is a compatibility surface only:

- canonical owner: `platform.contracts`;
- introduced by: C14;
- reason: preserve the pre-C14 `conformdag.platform.app` import path;
- removal/deprecation decision: C30.

Modern route code must import DTOs directly from `platform.contracts`, not
through `platform.app`.

This re-export must not create a second definition.

### Request behavior

Do not globally enable `extra="forbid"` on request DTOs in C14 because the
current request models use Pydantic's existing extra-field behavior and C14 is
not an API strictness change.

Preserve the existing `PolicyUpsertRequest` partial/compatibility semantics,
including:

```text
deterministic_checks
configuration
check_kind
check_config
source metadata
ownership
scope
exceptions
enforcement
tags
preserve-on-omit behavior
legacy/canonical conflict handling
```

The existing beta compatibility fields remain deprecated and readable.
C30 owns compatibility removal policy.

### Gate request refinement

Change:

```python
rules: list[dict[str, Any]]
```

to:

```python
rules: list[GateRule]
```

for `GateUpsertRequest`.

This is explicitly required by C14 and uses the existing domain discriminator
on `GateRule`.

JSON remains unchanged.

---

## Response model policy

Define a transport response base:

```python
class PlatformResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Ordinary platform response DTOs inherit from this model.

This catches accidental transport-field leakage when routes build responses.

Do not apply this response-only configuration to request DTOs.

---

## Required response contracts

### Health

```python
class HealthResponse(PlatformResponse):
    status: Literal["ok"]
```

JSON remains:

```json
{"status": "ok"}
```

### Repository registration

```python
class RepositoryRegistrationResponse(PlatformResponse):
    id: str
    name: str
```

### Workspace load

```python
class WorkspaceLoadResponse(PlatformResponse):
    repositories_registered: int
```

The count must remain non-negative.

### Repository

```python
class RepositoryResponse(PlatformResponse):
    id: str
    name: str
    path: str
    policy_pack: str | None
    airflow_profile: str | None
    baseline_scan_id: str | None
```

Do not expose `RepositoryRow.created_at`; it is not in the current wire
contract.

### Scan transition

```python
class ScanTransitionResponse(PlatformResponse):
    scan_id: str
    status: ScanStatus
```

Used for queue and cancel responses.

### Scan status

```python
class ScanStatusResponse(PlatformResponse):
    scan_id: str
    repository_id: str
    status: ScanStatus
    created_at: datetime
    finished_at: datetime | None
    complete: bool | None
    result_fingerprint: str | None
    error: str | None
    gate_passed: bool | None
```

### Scan history

Keep the existing `ScanSummaryResponse`, with:

```text
scan_id
status
created_at
finished_at
result_fingerprint
complete
gate_passed
artifact_available
```

Body remains a JSON array.

`X-Total-Count` remains a response header rather than changing to a page
envelope.

### Baseline

```python
class BaselineResponse(PlatformResponse):
    repository_id: str
    baseline_scan_id: str
```

### Canonical scan report

Do not create a duplicate platform DTO.

`ScanReport` remains the canonical public report model and is the response model
for:

```text
GET /api/v1/scans/{scan_id}/report
```

This follows the architecture rule that `ScanReport` JSON is the canonical
serialized product result.

### Finding

Refine the existing `FindingResponse` to use typed existing domain values:

```python
class FindingResponse(PlatformResponse):
    policy_id: str
    policy_version: str
    status: FindingStatus
    severity: Severity
    file_path: str | None
    start_line: int | None
    end_line: int | None
    fingerprint: str
    explanation: str | None
    remediation: str | None
    fix: RemediationPayload | None
    suppressed: bool
    baseline_status: Literal["existing", "new"] | None
```

The JSON representation remains the same.

Do not use `dict[str, Any]` for `fix`.

### Suppression

```python
class SuppressionResponse(PlatformResponse):
    id: str
    policy_id: str
    fingerprint: str
    reason: str
    owner: str
    created_at: datetime
    expires_at: datetime
    source: str
```

### Overview/trends

Retain and make response-only strict:

```text
TrendPoint
OverviewScan
OverviewResponse
RepositoryTrendsResponse
```

Their JSON fields remain unchanged.

### Pack summary

```python
class PackSummaryResponse(PlatformResponse):
    name: str
    path: str
    id: str | None
    version: str | None
    policy_count: int
    error: str | None
```

### Pack validation

```python
class PackValidationResponse(PlatformResponse):
    valid: bool
    errors: list[str]
```

### Policy vocabulary response

Refine `PolicyVocabularyResponse`:

```python
class PolicyVocabularyResponse(PlatformResponse):
    deterministic_checks: list[str]
    configuration: PolicyConfiguration
    check_kind: str
    check_config: PolicyConfiguration
```

`check_kind` and `check_config` remain the beta compatibility projection.

### Policy response

Add:

```python
class PolicyResponse(PolicyVocabularyResponse):
    id: str
    title: str
    version: str
    status: LifecycleStatus
    severity: Severity
    tags: list[str]
    source_document: str
    source_section: str
    source_version: str | None
    invariant: str
    safe_path: str | None
    ownership: Ownership
    scope: PolicyScope
    exceptions: ExceptionPolicy
    enforcement: EnforcementConfig
```

Do not expose the domain `Policy` object directly as a FastAPI response model.

The route converts `Policy` into this flattened existing wire shape.

### Gate

Refine:

```python
class GateResponse(PlatformResponse):
    id: str
    rules: list[GateRule]
```

JSON remains unchanged.

### Policy mutation

```python
class PolicyMutationResponse(PlatformResponse):
    status: Literal["saved", "deleted"]
    policy_id: str
```

### Gate mutation

```python
class GateMutationResponse(PlatformResponse):
    status: Literal["saved", "deleted"]
    gate_id: str
```

Use separate policy/gate mutation models instead of one response with optional
unrelated identifier fields.

---

## Endpoint-to-contract matrix

The 25 specific C13 routes retain the same order and operation IDs.

Use these response contracts:

| Endpoint | Response |
| --- | --- |
| `GET /health` | `HealthResponse` |
| `POST /repos` | `RepositoryRegistrationResponse` |
| `POST /workspace/load` | `WorkspaceLoadResponse` |
| `GET /repos` | `list[RepositoryResponse]` |
| `POST /repos/{id}/scans` | `ScanTransitionResponse` |
| `POST /scans/{id}/cancel` | `ScanTransitionResponse` |
| `GET /scans/{id}` | `ScanStatusResponse` |
| `GET /repos/{id}/scans` | `list[ScanSummaryResponse]` |
| `PUT /repos/{id}/baseline` | `BaselineResponse` |
| `GET /scans/{id}/report` | `ScanReport` |
| `GET /scans/{id}/findings` | `list[FindingResponse]` |
| `GET /scans/{id}/export/{format}` | raw `Response` |
| `GET /suppressions` | `list[SuppressionResponse]` |
| `POST /suppressions` | `SuppressionResponse` |
| `PATCH /suppressions/{id}` | `SuppressionResponse` |
| `GET /overview` | `OverviewResponse` |
| `GET /repos/{id}/trends` | `RepositoryTrendsResponse` |
| `GET /packs` | `list[PackSummaryResponse]` |
| `GET /packs/{name}/policies` | `list[PolicyResponse]` |
| `PUT /packs/{name}/policies/{id}` | `PolicyMutationResponse` |
| `DELETE /packs/{name}/policies/{id}` | `PolicyMutationResponse` |
| `POST /packs/{name}/validate` | `PackValidationResponse` |
| `GET /packs/{name}/gates` | `list[GateResponse]` |
| `PUT /packs/{name}/gates/{id}` | `GateMutationResponse` |
| `DELETE /packs/{name}/gates/{id}` | `GateMutationResponse` |

The two API fallbacks continue using FastAPI's existing HTTP exception envelope.

C14 does not introduce a custom global error-envelope schema.

---

## Service/domain return types

Services must stop constructing `platform.contracts` models.

Use small immutable service records when no existing domain model fits.

### Repository service

Introduce internal values equivalent to:

```python
@dataclass(frozen=True)
class RepositoryRegistration:
    id: str
    name: str

@dataclass(frozen=True)
class RepositoryRecord:
    id: str
    name: str
    path: str
    policy_pack: str | None
    airflow_profile: str | None
    baseline_scan_id: str | None
```

`register_repository()` returns `RepositoryRegistration`.

`list_repositories()` returns `list[RepositoryRecord]`.

### Scan service

Introduce values equivalent to:

```text
ScanTransition
ScanStatusRecord
ScanSummaryRecord
FindingRecord
```

Use:

- `ScanStatus` for lifecycle state;
- `FindingStatus` for finding status;
- `Severity` for finding severity;
- `RemediationPayload | None` for finding fixes.

`Page[T]` remains an internal service pagination result.

### Baseline service

Return a typed `BaselineAssignment` rather than a dictionary.

### Suppression service

Return a typed `SuppressionRecord` rather than dictionaries.

### Aggregates

Replace the transport-model dependency with aggregate records equivalent to:

```text
TrendPointData
OverviewScanData
OverviewData
RepositoryTrendsData
```

`platform.aggregates` must no longer import `platform.contracts`.

### Pack service

Remove the `PolicyVocabularyResponse` dependency.

Use internal/domain values:

```text
PackSummaryData
PackValidationResult
Policy
QualityGate
```

Specifically:

- `list_packs()` → `list[PackSummaryData]`;
- `list_policies()` → `list[Policy]`;
- `list_gates()` → `list[QualityGate]`;
- `validate_pack()` → `PackValidationResult`.

Mutation methods remain authoritative and retain their existing semantics.

---

## Route conversion

Every route converts service/domain values to the appropriate response DTO
before returning.

Examples conceptually:

```python
record = repository_service.register_repository(...)
return RepositoryRegistrationResponse(id=record.id, name=record.name)
```

and:

```python
return [
    RepositoryResponse(
        id=item.id,
        name=item.name,
        path=item.path,
        policy_pack=item.policy_pack,
        airflow_profile=item.airflow_profile,
        baseline_scan_id=item.baseline_scan_id,
    )
    for item in records
]
```

Do not move conversion back into services.

Small private conversion helpers inside individual route modules are allowed
when they remove repeated field mapping.

Do not create a generic serializer or transport mapper framework.

---

## Pack route conversion

`routes/packs.py` performs the explicit domain-to-wire projection.

For one `Policy`, preserve the existing flattened fields:

```text
id
title
version
status
severity
tags
source_document
source_section
source_version
invariant
safe_path
ownership
scope
exceptions
enforcement
deterministic_checks
configuration
check_kind
check_config
```

Canonical values derive from:

```text
policy.enforcement.deterministic_checks
policy.configuration
```

Compatibility projections derive from the same canonical values:

```text
check_kind = policy.configuration.kind
check_config = policy.configuration
```

Do not create a second policy vocabulary registry.

---

## FastAPI response typing

Route handler return annotations must describe the explicit contract.

Use FastAPI `response_model=` where useful to make the intended public model
obvious, but do not introduce a different runtime JSON shape.

Raw export endpoints remain explicit `Response` objects and do not get a JSON
response model.

Preserve C13 handler names and registration order so operation IDs stay
unchanged.

---

## OpenAPI contract

C14 stabilizes the generated OpenAPI document through tests.

Do not create a new checked-in OpenAPI export mechanism in C14.

The repository currently has no checked-in platform OpenAPI artifact, and C31
owns generated TypeScript consumption.

Add OpenAPI inspection tests that prove:

1. all 25 specific `/api/v1` path/method operations remain present across the existing 20 unique specific API paths;
2. C13 operation IDs remain unchanged;
3. request bodies reference the intended request DTO components;
4. successful JSON responses reference the intended response DTO components;
5. list responses identify their typed item schema;
6. mutation routes retain the existing `Authorization` header dependency;
7. read routes do not accidentally acquire mutation auth;
8. pagination endpoints still return array bodies and use `X-Total-Count`;
9. no SQLAlchemy model such as `RepositoryRow`, `ScanRow`, `FindingRow`, or
   `SuppressionRow` appears in OpenAPI components;
10. platform response DTOs do not contain accidental unbounded
    `additionalProperties: true` objects.

Legitimate dynamic maps inside the canonical `ScanReport` or existing core
domain models are not considered accidental platform-contract leaks.

Review them separately rather than banning every `additionalProperties`
occurrence globally.

---

## Response-model tests

Add direct model tests for:

```text
repository registration
repository
workspace load
scan transition
scan status
scan summary
baseline
finding
suppression
pack summary
pack validation
policy
gate
policy mutation
gate mutation
overview
repository trends
health
```

Response models must reject unknown fields.

Request models retain their current extra-field semantics.

Add serialization tests proving typed enums/domain submodels still emit the
same JSON string/object values expected by current clients.

---

## Frontend contract alignment

`frontend/src/api.ts` remains hand-written until C31.

Update only the TypeScript declarations needed to match the now-explicit
backend contract.

Recommended refinements:

```text
Scan lifecycle status union
Finding status union
Severity union
RemediationPayload interface
Finding.fix → RemediationPayload | null
ReportFinding.fix → RemediationPayload | null
distinct PolicyMutationResponse
distinct GateMutationResponse
backend request optionality where currently broader than the frontend
```

Keep `GateRule` as the existing discriminated union.

Do not generate TypeScript from OpenAPI in C14.

Do not move business validation into the frontend.

No component redesign is required merely because the type definitions become
more precise.

---

## Core schema boundary

Do not add platform DTOs to `scripts/export_schemas.py`.

That script remains the exporter for the existing public core schemas.

C14 must run:

```text
mise run schema --check
```

and expect no core-schema diff unless an unintended core-model change occurred.

Platform wire-schema correctness is verified through FastAPI OpenAPI tests.

C31 later consumes the stable OpenAPI contract for generated frontend types.

---

## Compatibility requirements

C14 must preserve:

- all 25 C13 specific routes;
- both API fallbacks;
- C13 route ordering;
- C13 operation IDs;
- request field names;
- response field names;
- JSON array/envelope shapes;
- `X-Total-Count`;
- auth requirements;
- status codes;
- existing service error → HTTP mappings;
- export media types and bytes;
- policy canonical/legacy vocabulary;
- policy preserve-on-omit behavior;
- gate behavior;
- repository/workspace behavior;
- scan lifecycle/fencing;
- baseline behavior;
- suppression behavior;
- canonical `ScanReport` JSON.

The intentional contract changes are descriptive/typing changes in OpenAPI,
not product payload redesigns.

---

## C13 temporary seams

C13 introduced `session_factory_for()` as a typed route dependency seam and
retained a localized workspace-pack helper bridge.

C14 does not need to redesign these dependencies merely to type the wire
contract.

Do not expand C14 into general route-dependency cleanup.

If a minimal import change becomes necessary because DTOs move to
`contracts.py`, keep it mechanical and do not redesign application
composition.

---

## Test-first sequence

1. Characterize existing representative HTTP JSON for every response family.
2. Add direct tests for the new response DTOs; observe RED for missing models.
3. Add OpenAPI response-schema assertions; observe RED because responses are
   currently incompletely typed.
4. Add/centralize models in `platform/contracts.py`.
5. Move request DTO ownership from `app.py`.
6. Decouple C12 services from wire models.
7. Decouple `platform.aggregates`.
8. Decouple `PackService`.
9. Convert route outputs explicitly and add response typing.
10. Update the hand-written frontend types.
11. Re-run all compatibility, OpenAPI, platform, frontend, schema, build,
    coverage, and whitespace gates.
12. Obtain independent whole-branch review.

---

## Expected files

Primary modifications:

```text
src/conformdag/platform/contracts.py
src/conformdag/platform/app.py
src/conformdag/platform/routes/repositories.py
src/conformdag/platform/routes/scans.py
src/conformdag/platform/routes/suppressions.py
src/conformdag/platform/routes/overview.py
src/conformdag/platform/routes/packs.py
src/conformdag/platform/services/repositories.py
src/conformdag/platform/services/scans.py
src/conformdag/platform/services/baselines.py
src/conformdag/platform/services/suppressions.py
src/conformdag/platform/aggregates.py
src/conformdag/platform/packs.py
frontend/src/api.ts
tests/test_platform.py
```

Modify other frontend test files only when required by type changes.

No migration file is expected.

No checked-in core schema file is expected to change.

---

## Explicit non-goals

C14 does not include:

- generated TypeScript;
- OpenAPI file generation;
- API version changes;
- route splitting;
- route ordering changes;
- auth redesign;
- custom error-envelope redesign;
- persistence/schema changes;
- Alembic migrations;
- scan workflow changes;
- worker/runner changes;
- pack editing semantic changes;
- removal of C02 legacy policy fields;
- compatibility cleanup owned by C30;
- model package decomposition owned by C21;
- frontend API generation owned by C31;
- security redaction work owned by C15.

---

## Verification

Run at minimum:

```bash
mise run setup

mise exec -- uv run pytest \
  tests/test_platform.py \
  -k 'contract or openapi or repository or workspace or scan or baseline or finding or suppression or overview or trend or pack or policy or gate' \
  -x --tb=short

mise exec -- uv run pytest tests/test_platform.py -x --tb=short

cd frontend && npm test
cd frontend && npm run build
cd ..

mise run check
mise run test:coverage
mise run schema --check
mise run build
git diff --check
```

Also inspect generated `app.openapi()` for:

```text
correct request components
correct successful response components
typed gate rules
typed remediation payloads
no ORM components
no accidental free-form platform response objects
unchanged operation IDs
unchanged auth binding
```

Perform a scoped import audit proving:

```text
platform/services/*.py does not import platform.contracts
platform/aggregates.py does not import platform.contracts
platform/packs.py does not import platform.contracts
routes import DTOs directly from platform.contracts
```

---

## Independent review focus

Independent whole-branch review must inspect:

- JSON compatibility;
- OpenAPI request/response accuracy;
- accidental response filtering;
- request-validation behavior;
- policy legacy vocabulary preservation;
- policy preserve-on-omit behavior;
- gate-rule typing;
- remediation typing;
- service → contract dependency removal;
- aggregate → contract dependency removal;
- PackService → contract dependency removal;
- ORM leakage;
- route operation IDs;
- auth;
- pagination headers;
- frontend manual-type parity;
- C15/C21/C30/C31 scope containment.

All Critical and Important findings must be resolved before the C14 ledger can
move to `review`.

---

## Delivery workflow

Use the established docs-first workflow.

### Written specification gate

```text
1. Create this specification exactly.
2. Branch from current origin/main.
3. Commit only the specification.
4. Push.
5. Open a docs-only PR.
6. Verify remote exact head and CI.
7. Stop.
```

Do not materialize the implementation plan or modify product code until the
written specification is explicitly approved.

### Plan gate

After specification approval:

```text
1. Materialize the separately approved C14 implementation plan.
2. Stack its docs-only branch directly on the approved spec head.
3. Commit only the plan.
4. Push.
5. Open a separate plan PR.
6. Verify exact-head CI.
7. Stop.
```

### Product implementation

Only after both documentation gates are approved:

```text
latest origin/main
→ isolated feat/c14-platform-contracts worktree
→ carry exact approved spec + plan
→ verify byte-for-byte
→ execute sequentially
→ full local verification
→ implementation PR
→ exact-head CI
→ independent whole-branch review
→ fixes/re-review if required
→ ledger-only evidence commit
→ final PR-head CI
→ stop unmerged
```

---

## Completion criteria

C14 is complete when:

- `platform/contracts.py` is the sole definition owner of platform wire DTOs;
- request DTO definitions no longer live in `app.py`;
- every ordinary JSON API response has an explicit typed shape;
- `ScanReport` remains the canonical report response;
- gate rules use `GateRule`;
- finding fix data uses `RemediationPayload`;
- C12 services no longer depend on transport contracts;
- aggregates no longer depend on transport contracts;
- `PackService` no longer depends on transport contracts;
- routes explicitly convert service/domain values to wire DTOs;
- no ORM model appears in OpenAPI;
- no accidental unbounded platform response mapping remains;
- valid client JSON remains compatible;
- C13 route order and operation IDs remain unchanged;
- frontend manual types match the stable API;
- C31 generation remains deferred;
- local gates pass;
- exact-head CI passes;
- independent review has no unresolved Critical or Important findings;
- the implementation PR remains open and unmerged pending explicit
  authorization.
