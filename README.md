# ConformDAG

Enforce your organization's Airflow engineering standards — as versioned policy
packs, with deterministic verification, verified fixes, and a self-hosted
governance server.

ConformDAG scans Apache Airflow DAG repositories against versioned YAML policy
packs. Source analysis is offline and non-executing by default; Dockerized
Airflow import validation and BYOK semantic review are explicit opt-ins. One
scan engine produces one versioned JSON report; terminal, SARIF, and
self-contained HTML are projections of it.

## The loop

```
org standards → policy pack (git) → scan (CLI / CI / dashboard)
→ deterministic fixes → LLM semantic verification → pull request (human merges)
→ governance dashboard: history, trends, suppressions
```

- **`conformdag scan`** evaluates the pack and produces the canonical report
  with machine-readable remediation payloads.
- **`conformdag fix`** proposes deterministic patches, verifies them by
  re-scanning an isolated copy, and writes only verified patches (`--apply`).
- **`conformdag agent run`** runs the agentic loop: triage (no LLM), fix, verify
  (model-agnostic, OpenAI-compatible endpoint), then a branch and pull request.
  The agent never merges — humans do.
- **The platform** is the self-hosted team server (Docker Compose): dashboard
  API, durable scan worker, Postgres, findings history, and suppression
  management.
- **The GitHub Action** runs blocking scans in CI and uploads SARIF.

## Install and quick start

ConformDAG requires Python 3.12. With Python and uv managed through mise:

```bash
mise use python@3.12 uv@0.12.0
mise exec -- uvx --from conformdag==1.0.0b1 conformdag version
```

Try it on any Airflow repository with the bundled **community** pack — no
organization setup needed:

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan \
  --path /path/to/airflow/dags \
  --policy-pack community \
  --format terminal
```

### Fix findings

Dry run prints a unified diff identical to what would be written; nothing is
touched without `--apply`, and only re-scan-verified patches are ever written:

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag fix --path .
mise exec -- uvx --from conformdag==1.0.0b1 conformdag fix --path . --apply
```

### Run the agentic fix loop

Configure an OpenAI-compatible endpoint and a GitHub App installation token,
then let the agent open a human-merged pull request:

```bash
export CONFORMDAG_AGENT_BASE_URL="https://api.openai-compatible-endpoint.example/v1"
export CONFORMDAG_AGENT_MODEL="your-model"
export CONFORMDAG_MODEL_API_KEY="..."
export CONFORMDAG_GITHUB_TOKEN="..."   # GitHub App installation token
export CONFORMDAG_GITHUB_REPO="owner/repo"
mise exec -- uvx --from conformdag==1.0.0b1 conformdag agent run --path . --open-pr
```

See the [user guide](docs/user-guide.md#agentic-fix-loop) for the safety model:
deterministic triage and generation, a strict verifier verdict schema, and
credential redaction before any content leaves the host.

### Enforce in CI

```yaml
- uses: parthmule28/conformdag@v1.0.0-beta.1
  with:
    policy-pack: community   # or a path, or a git URL pulled with pack pull
```

Blocking findings fail the job and the SARIF lands in code scanning.

### Run the governance platform

```bash
export CONFORMDAG_PLATFORM_TOKEN="$(openssl rand -hex 32)"
export CONFORMDAG_WORKSPACE_DIR="$HOME/conformdag-platform"
docker compose -f deploy/docker-compose.yml up -d
```

Full instructions, including workspace registration and the API contract, are in
the [platform deploy guide](docs/platform-deploy.md).

## Organization packs are the product

The `community` pack is a try-now path. Production governance runs on your
organization's own pack in git: stable policy IDs with provenance, versioned
contracts, expiring exceptions, and a golden path of a central policy repo
consumed by DAG repositories. Author packs with

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag init
mise exec -- uvx --from conformdag==1.0.0b1 conformdag validate-policies --path policies/pack.yaml
```

and pull them anywhere with `conformdag pack pull <git-url>`.

## Honest limitations

- Semantic and agent evaluation are integration-verified, not accuracy-baselined:
  the public benchmark has no redistributable labelled semantic corpus. The
  deterministic and round-trip gates are the accuracy-neutral floor.
- The dashboard SPA covers repo status, scan triggering, history, findings,
  suppression management, and exports; there is no multi-user RBAC, and none is
  planned for 1.0.
- A maintained Airflow 2.x runtime image is not shipped; supply your own
  digest-pinned image with `--runtime-image` outside the supported profile.
- dbt support, OCI policy bundles, and SSO pack download are post-1.0 work; MCP
  for IDE agents is the first v1.x follow-up.

## Development

The project uses [mise](https://mise.jdx.dev/) as its tool and task entry point:

```bash
mise install
mise run setup
mise run check
```

Run the CLI from a checkout through the locked uv environment:

```bash
mise exec -- uv run conformdag scan --path examples/sample-repository --policy-pack community
```

See the [user guide](docs/user-guide.md) for operational usage, the
[architecture](docs/architecture.md) for trust boundaries and data flow, the
[platform deploy guide](docs/platform-deploy.md) for the team server, and the
[release checklist](docs/release.md) for publication evidence.

## License

Apache-2.0. See [LICENSE](LICENSE).
