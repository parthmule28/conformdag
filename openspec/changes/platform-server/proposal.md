## Why

Governance teams need a durable team server, not a per-laptop CLI. Journey D
(dashboard review of findings, history, suppressions, export) is already a
1.0.0 MUST in `org-governance-1-0`, but that spec records product behavior only
— there is no architecture behind it. ADR 0003 now fixes the platform tier:
Docker Compose deployment, FastAPI backend with a stable versioned `/api/v1`,
SPA served from the same image, Postgres state store, and a separate worker
process for durable scan execution. This change turns those decisions into
reviewable capability requirements before implementation begins.

## What Changes

- Add the `platform-server` capability: workspace file model, durable worker
  scan execution with the existing single scan engine, stable versioned HTTP
  API, Postgres state plus canonical report artifacts, single-admin auth,
  suppression lifecycle management, Compose deployment, and large-repository
  parse caching.
- Modify one `org-governance-1-0` requirement per ADR 0003: the dashboard
  HTTP API becomes a stable, versioned compatibility surface (superseding the
  "MAY be unstable" stance). The non-goals amendments (single-admin auth scope,
  auto-PR relocation) are owned by the agent-harness change delta so each
  requirement is modified in exactly one change.
- The scan engine, canonical report JSON contract, and policy pack schema are
  NOT modified. The PyPI package remains a pure offline CLI tool; the platform
  ships as a Docker image.

## Capabilities

### New Capabilities

- `platform-server`: Team governance server behind ConformDAG — FastAPI +
  SPA dashboard + worker + Postgres in one Compose stack. Workspace YAML
  registration of local repos and packs, durable job queue with subprocess
  crash isolation, `/api/v1` OpenAPI contract, JSONB report artifacts with
  normalized findings, suppression lifecycle with audit fields, single-admin
  authentication for mutations, and content-hash parse caching for large
  repositories.

### Modified Capabilities

- `org-governance-1-0`: "Stable 1.0.0 contracts" now treats the dashboard HTTP
  API as stable, versioned (`/api/v1`), and compatible within a major version.
  The non-goals rewrite is intentionally left to the agent-harness change.

## Impact

- New `src/conformdag/platform/` (or `serve/`) package: FastAPI app, worker
  loop, job queue, Postgres models; Alembic migrations directory; SPA frontend
  directory compiled to static assets baked into the platform image.
- New Docker Compose files (api, worker, postgres) and deployment docs
  (deploy guide, upgrade/migration guide, threat model update).
- CLI gains `serve` and `worker` entry points; existing commands are
  unchanged.
- Core scan engine is unchanged — the single-engine requirement is inherited
  from `org-governance-1-0` and restated here as platform/CLI parity.
