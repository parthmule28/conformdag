## 1. Workspace file model and validation

- [ ] 1.1 Define the workspace YAML schema (registered DAG repo paths, policy pack path) as Pydantic models
- [ ] 1.2 Resolve relative paths against the workspace file location and reject missing/unreadable targets with actionable errors
- [ ] 1.3 Default the workspace path to `./conformdag-workspace.yaml` when the operator supplies none
- [ ] 1.4 Verify no code path clones or syncs remote git (repo paths are local-only)
- [ ] 1.5 Unit tests: schema validation, relative-path resolution, missing-file errors

## 2. FastAPI skeleton, /api/v1, OpenAPI

- [ ] 2.1 Scaffold `src/conformdag/platform/` (or `serve/`) with an app factory and dependency wiring
- [ ] 2.2 Mount all platform endpoints under `/api/v1` with versioned response models
- [ ] 2.3 Serve the generated OpenAPI document and docs UI from the running API
- [ ] 2.4 Mount the compiled SPA as static assets from the same process (no CORS)
- [ ] 2.5 API contract tests that pin `/api/v1` request/response shapes

## 3. Postgres schema and Alembic baseline

- [ ] 3.1 Create the Alembic environment wired to the platform settings
- [ ] 3.2 Baseline migration creating `repos`, `scans`, `findings` (normalized), report JSONB artifacts, `suppressions`, and `jobs` tables
- [ ] 3.3 Index findings for repo/policy/file/line queries and trend aggregation
- [ ] 3.4 Migration test: baseline applies cleanly to an empty database and upgrades from the previous released image

## 4. Worker process and job queue

- [ ] 4.1 Add the `conformdag worker` entry point (poll loop, graceful shutdown)
- [ ] 4.2 Job claim via `SELECT ... FOR UPDATE SKIP LOCKED` with visibility timeout reclaim
- [ ] 4.3 Execute scans as subprocesses of the worker (crash isolation, exit-code capture)
- [ ] 4.4 Enforce per-job timeout and retry policy from job configuration
- [ ] 4.5 Implement cancellation: cancel flag honored by the API, worker terminates the subprocess and marks the job cancelled
- [ ] 4.6 Job state transitions persisted so a worker restart reclaims in-flight jobs

## 5. Parse cache

- [ ] 5.1 Implement per-file AST parse caching keyed on content hash in the worker
- [ ] 5.2 Store the cache in Postgres (or a configurable local directory) with size/eviction bounds
- [ ] 5.3 Test: repeated scans of unchanged trees skip reparsing; cache does not alter canonical report output

## 6. Scan ingestion and report artifacts

- [ ] 6.1 Store each completed scan's canonical report JSON as a JSONB artifact
- [ ] 6.2 Ingest findings into normalized rows (repo, scan, file, line, policy, severity, status)
- [ ] 6.3 Apply suppressions during ingestion and record suppression state on findings
- [ ] 6.4 Test: SARIF/HTML/JSON exports generated from stored artifacts match CLI exports for the same scan

## 7. SPA scaffold and dashboard pages

- [ ] 7.1 Scaffold the TypeScript SPA with build tooling producing a static bundle for the platform image
- [ ] 7.2 Repo status page: registered repos, last scan state, next actions
- [ ] 7.3 Findings page: file/line, policy contract, severity, suppression state, filters
- [ ] 7.4 Scan history page: per-repo scan list with job status (queued/running/done/failed/cancelled)
- [ ] 7.5 Trends page: findings over time from normalized findings (by repo/policy/severity)
- [ ] 7.6 Suppression management page: create/edit/expire with audit fields visible
- [ ] 7.7 Export from the dashboard: SARIF, HTML, and canonical JSON downloads

## 8. Single-admin auth

- [ ] 8.1 Admin token/session bootstrap (generated secret, documented rotation)
- [ ] 8.2 Require admin auth on mutation endpoints (trigger scan, create/edit/expire suppression, cancel job)
- [ ] 8.3 Decide and implement read-endpoint posture (open on localhost bind; documented for remote binds)
- [ ] 8.4 Test: anonymous requests to mutation endpoints are rejected

## 9. Docker Compose deployment

- [ ] 9.1 Build the single platform image with API + worker entrypoints and baked SPA assets
- [ ] 9.2 Compose file wiring `api`, `worker`, and `postgres` with healthchecks and volume for Postgres data
- [ ] 9.3 Run Alembic migrations as part of stack startup before the API serves traffic
- [ ] 9.4 Mount or configure the workspace file path into both api and worker containers

## 10. Documentation

- [ ] 10.1 Deploy guide: Compose bring-up, workspace file, bind posture, admin token setup
- [ ] 10.2 Upgrade and migration guide: image pulls, Alembic behavior, Postgres volume backups
- [ ] 10.3 Threat model update covering the new endpoints, auth posture, and subprocess execution
- [ ] 10.4 API reference linking the served OpenAPI document for `/api/v1`

## 11. Tests

- [ ] 11.1 API contract tests covering every `/api/v1` route (auth gating, shapes, error cases)
- [ ] 11.2 Worker durability tests including kill-mid-scan recovery (job reclaimed or retried per policy)
- [ ] 11.3 Cancellation and timeout tests (cancel takes effect; hung subprocess is killed and retried)
- [ ] 11.4 Platform/CLI parity tests: canonical report JSON and SARIF identical for the same inputs
- [ ] 11.5 Compose smoke test: full stack passes journey D end to end
