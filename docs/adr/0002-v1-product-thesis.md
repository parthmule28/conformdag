# ADR 0002: ConformDAG 1.0.0 product thesis

## Status

Accepted (2026-08-29)

Decisions 9 (dashboard HTTP API may be unstable) and 10 (automatic pull request
creation excluded) are **superseded in part** by
[ADR 0003](0003-v1-agentic-platform-architecture.md): the platform exposes a
stable, versioned `/api/v1`, and auto-PR is in scope with the agent never
merging.

## Context

The public beta is a local CLI that scans Airflow repositories against versioned
policies. Apache Airflow's 2022 survey indicated most users work in organizations
with 200+ employees. Org policy is not a generic community standards document.
ADR 0001 deferred dashboard and related platform features (YAGNI). 1.0.0 is a
Product Hunt target for a **whole product** usable by platform teams, not a
CLI-only increment.

Normative behavior lives in OpenSpec capability `org-governance-1-0`
(`openspec/changes/v1-product-thesis/specs/org-governance-1-0/spec.md` until
archived).

## Decision

1. **Org-first.** Production story is an org policy pack in git. `community` is
   try-now only.
2. **Journeys.** 1.0.0 MUST complete platform bootstrap (B) and dashboard review
   (D). Author CLI fix (A) is a byproduct.
3. **Dashboard is a 1.0.0 MUST.** Documented deploy is **Docker Compose**.
   `conformdag serve` (or the compose stack) hosts a self-hosted OSS web UI that
   includes **agent/semantic findings and explanations** when BYOK is enabled,
   not a deterministic-only viewer. No ConformDAG-operated SaaS. This supersedes
   ADR 0001 principle 5 **only** for dashboard; plugins and multi-pack
   composition stay YAGNI until a later ADR.
4. **Git-native packs.** Central policy repo + documented submodule/path
   consumption. Human git commit/tag. No OCI bundle pull in 1.0.0.
5. **One scan engine.** CLI, dashboard, and GitHub Action call the existing scan
   orchestration. Deterministic FAIL is the verifier; agents cannot override it.
6. **Agent in 1.0.0.** Pack authoring from org markdown and confirmed `fix`.
   Optional extra + BYOK. Offline scan without the extra remains required.
7. **GitHub Action in 1.0.0.** Scan, SARIF, fail on blocking findings.
8. **MCP is not a 1.0.0 MUST.**
9. **Stable contracts.** Pack YAML, scan report JSON, public CLI
   `scan` / `serve` / `fix` / `validate-policies`. Dashboard HTTP API may be
   unstable.
10. **Out of 1.0.0.** Hosted SaaS, dashboard auth/RBAC, auto-PRs, autonomous DAG
    creation, runtime orchestration, dbt, Airflow 2.x maintained image, telemetry.

## Consequences

- Next OpenSpec changes (`workspace-and-serve`, `agent-pack-and-fix`,
  `github-action`) MUST satisfy `org-governance-1-0`. They MUST NOT ship 1.0.0
  without the dashboard.
- Roadmap language must describe self-hosted `serve`, not a future online
  multi-user service as the 1.0.0 shape.
