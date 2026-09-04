# ConformDAG Platform deploy guide

The platform is the self-hosted team server: the FastAPI dashboard API, a durable
scan worker, and Postgres, all behind Docker Compose. Registered repositories and
packs stay on local disk; the platform never clones or syncs git.

## Prerequisites

- Docker with the Compose plugin
- A workspace directory containing `conformdag-workspace.yaml` that registers the
  DAG repositories and policy packs the platform may access (see below)

## Configure

```bash
export CONFORMDAG_PLATFORM_TOKEN="$(openssl rand -hex 32)"
export CONFORMDAG_WORKSPACE_DIR="$HOME/conformdag-platform"
```

The workspace directory must contain `conformdag-workspace.yaml`; relative paths
inside it resolve against the workspace file's own location:

```yaml
schema_version: "1"
repositories:
  - name: core-dags
    path: dags/core
    policy_pack: policies/pack.yaml
```

## Run

```bash
docker compose -f deploy/docker-compose.yml up -d
```

The dashboard API is served on `http://127.0.0.1:8642/api/v1`. Bind it to a team
interface only when the exposure model is understood: reads are open and mutations
require the single-admin bearer token; there is no multi-user RBAC.

## Register and scan

```bash
curl -X POST http://127.0.0.1:8642/api/v1/workspace/load \
  -H "Authorization: Bearer $CONFORMDAG_PLATFORM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/workspace/conformdag-workspace.yaml"}'

REPO_ID=$(curl -s http://127.0.0.1:8642/api/v1/repos | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
curl -X POST http://127.0.0.1:8642/api/v1/repos/$REPO_ID/scans \
  -H "Authorization: Bearer $CONFORMDAG_PLATFORM_TOKEN"
```

The worker claims the queued scan, runs it in a subprocess with the same single
scan engine as the CLI, and ingests the canonical report. Abandoned runs are
reclaimed within an attempt budget; repeated scans of unchanged trees reuse the
content-hash parse cache.

## Review

- `GET /api/v1/repos/{id}/scans` — scan history
- `GET /api/v1/scans/{id}/findings?status=FAIL` — findings with file/line
- `GET /api/v1/scans/{id}/export/sarif|html|json` — exports are projections of the
  stored canonical report and remain byte-compatible with CLI exports
- `POST/PATCH /api/v1/suppressions` — platform-owner suppressions with audit fields;
  suppressed findings remain visible with their suppression state

The OpenAPI document at `GET /api/v1/docs` is the API contract; it is stable within
a major platform version.

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `CONFORMDAG_PLATFORM_DSN` | api, worker | Required database URL (Postgres in production) |
| `CONFORMDAG_PLATFORM_TOKEN` | api | Single-admin bearer token; unset disables mutations |
| `CONFORMDAG_PLATFORM_RETENTION_KEEP` | api, worker | Full report artifacts kept per repo (default 50) |
| `CONFORMDAG_WORKER_POLL_SECONDS` | worker | Idle poll interval (default 2.0) |
| `CONFORMDAG_WORKER_IDLE_SECONDS` | worker | Reclaim a running scan after this idle time (default 600) |
| `CONFORMDAG_WORKER_TIMEOUT_SECONDS` | worker | Hard subprocess timeout per scan (default 1800) |
| `CONFORMDAG_WORKER_MAX_ATTEMPTS` | worker | Reclaim budget before a scan is failed (default 3) |
