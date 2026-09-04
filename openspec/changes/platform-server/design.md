## Context

ADR 0003 decides the platform tier: the PyPI package stays a pure offline tool,
and the team platform is a Docker Compose stack (FastAPI backend, SPA dashboard
served from the same image, Postgres state store, separate worker process).
`org-governance-1-0` already requires journey D (dashboard review without CLI)
but deliberately did not choose frameworks, storage, or process model — those
were deferred to this change. ADR 0002 decision 9 allowed an unstable dashboard
API; ADR 0003 supersedes that in part with a stable versioned `/api/v1`.

## Goals / Non-Goals

**Goals:**

- Specify the platform server as an implementable capability: workspace file,
  durable scan execution, stable `/api/v1`, Postgres state, single-admin auth,
  suppression lifecycle, Compose deploy, large-repo performance.
- Amend exactly two `org-governance-1-0` requirements to match ADR 0003 and
  leave every other requirement untouched.
- Keep the canonical report JSON as the sole export contract; platform state is
  an operational store, not a second findings format.

**Non-Goals:**

- Multi-user RBAC, org management, or SSO (single admin only).
- Remote git sync or cloning of DAG/policy repositories.
- Agent harness, PR automation, or any agent features (separate change:
  `agent-harness`).
- Changing the scan engine, report JSON schema, or pack schema.

## Decisions

1. **Two processes behind one image.** The platform image runs as `api` or
   `worker`; Postgres is the only stateful dependency. No Redis, no Celery —
   the job queue is a Postgres table claimed with `SELECT ... FOR UPDATE
   SKIP LOCKED`. Alternative: a broker + worker framework. Rejected — one more
   stateful service to operate for a single-team deployment.

2. **Scans run in subprocesses.** The worker forks a subprocess per scan for
   crash isolation, with timeout, retry, and cancellation; job state lives in
   Postgres so it survives worker restarts. Alternative: in-process execution.
   Rejected — a segfault or hang in parsing must not take the worker down.

3. **`/api/v1` is a compatibility surface.** The API is versioned under
   `/api/v1`, documented via OpenAPI, and treated as stable within a major
   platform version (ADR 0003 supersedes ADR 0002 decision 9's instability
   allowance). Breaking changes require a new major version path.

4. **SPA compiled to static assets.** A TypeScript SPA is built to static
   assets baked into the platform image and served by the API process — no
   CORS, no separate frontend service. Final framework choice is an open
   question; the contract only requires a static bundle.

5. **Postgres schema with report duality.** Tables: `repos`, `scans`,
   `findings` (normalized for query and trends), report JSONB artifacts,
   `suppressions`, `jobs`. Exports (SARIF/HTML/JSON) are projections of the
   stored canonical report and remain byte-compatible with CLI exports. The
   report JSON stays the file-export artifact; Postgres is not a new report
   format.

6. **Alembic from day one.** Every schema change ships as an Alembic migration;
   there is no hand-written DDL path. Upgrade docs assume `alembic upgrade
   head` runs as part of image startup or deploy.

7. **Single-admin auth.** Mutation endpoints (trigger scans, edit
   suppressions) require an admin token/session held by the platform owner.
   Read endpoints may be open on localhost deployments; the documented bind
   posture states the exposure model per endpoint class. No multi-user RBAC.

8. **Workspace YAML at an explicit path.** The workspace file defaults to
   `./conformdag-workspace.yaml` and registers local DAG repo paths plus the
   policy pack path. Relative paths resolve against the workspace file's
   location, not the process CWD. The platform never clones or syncs git.

9. **Content-hash parse cache.** The worker caches per-file AST parse results
   keyed on file content hash; repeated scans of unchanged trees skip
   reparsing. The cache is a performance optimization only — it MUST NOT
   change scan output.

10. **SPA is React + Vite + TypeScript with TanStack Query/Router and
    Tailwind.** The typed API client is generated from FastAPI's OpenAPI
    schema (openapi-typescript), so the stable `/api/v1` contract mechanically
    becomes frontend types. Alternative: SvelteKit. Rejected — SSR machinery
    we would never use and a smaller contributor pool for an OSS project.

11. **Retention: normalized findings forever, report artifacts bounded.**
    Normalized findings and aggregates are small rows and are kept
    indefinitely (trends are the governance value); full JSONB report
    artifacts keep the last 50 scans per repo by default (configurable),
    pruned by a worker retention job, latest never deleted.

12. **Suppression split: git things stay in git, operational things in
    Postgres.** Pack suppressions remain declarative policy-as-data
    (versioned, expiring per today's model). Platform suppressions are a
    separate audited layer (who/when/why/expiry) applied at ingestion;
    effective state is the union, and the dashboard shows each suppression's
    source. Platform-owner edits touch only platform suppressions; editing a
    pack-owned suppression from the UI prompts a policy-pack PR via the
    agent harness rather than writing into git.

## Risks / Trade-offs

- [Postgres-as-queue reaches scale limits] → Acceptable for team deployments;
  SKIP LOCKED keeps claim contention low; a broker can be added behind the
  jobs interface later without changing the API.
- [Subprocess-per-scan adds latency] → Crash isolation and hard timeouts are
  worth milliseconds at governance-scan cadence; the parse cache claws back
  wall-clock time on repeat scans.
- [Stable API is a maintenance tax] → Required by ADR 0003 for external agent
  integration; contained by keeping `/api/v1` thin over the report contract.
- [Normalized findings drift from report JSON] → Findings are ingestions of
  the canonical report, never an independent pipeline; parity is test-enforced
  (dashboard SARIF equals CLI SARIF).
- [SPA baked into the image slows frontend iteration] → Dev mode proxies to a
  local dev server; production ships the static bundle only.

## Migration Plan

- Implement behind new entry points (`conformdag serve`, `conformdag worker`);
  existing CLI behavior and the PyPI offline tool are untouched, so there is
  no runtime migration for existing users.
- The first platform deploy creates the schema via the Alembic baseline
  migration; subsequent deploys run pending migrations before the API accepts
  traffic.
- The two `org-governance-1-0` requirement modifications take effect when this
  change is applied; docs referencing the unstable-API stance are updated in
  the docs tasks.

## Open Questions

None — resolved at planning (2026-09-02); see decisions 10–12.
