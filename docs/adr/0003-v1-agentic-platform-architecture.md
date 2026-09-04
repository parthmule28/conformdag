# ADR 0003: Agentic platform architecture

## Status

Accepted (2026-09-02)

## Context

ADR 0002 set the 1.0.0 thesis: org-first product, git-native packs, self-hosted
`serve` dashboard as a release MUST, agent pack authoring plus
confirmation-gated `fix`, and auto-PRs as a non-goal. The product owner has now
adopted a revised, quality-first vision with no external launch date: a
two-tier product (offline PyPI tool plus Docker Compose governance platform)
with agentic enforcement in which the agent is a tool user of ConformDAG, never
the verifier.

Normative behavior lives in OpenSpec capability `org-governance-1-0`.

## Decision

1. **Two tiers.** The PyPI package stays a pure offline tool for any engineer.
   A Docker Compose "platform" is the team server for governance teams.
2. **Agent as tool user.** The agent reads the canonical report JSON,
   understands findings, and fixes policy violations using deterministic
   codemods — it never invents patches for mechanical fixes. An LLM-verifier
   (OpenAI-compatible endpoint) reviews the diff plus re-scan report for
   semantic sanity. The agent then pushes a branch and opens a PR via a GitHub
   App; it NEVER merges — humans merge. Deterministic re-scan remains the sole
   compliance verifier. The agent also reviews policies themselves (fail rates,
   suppression rates, stale suppressions, never-firing policies) and can draft
   policy-pack PRs.
3. **Auto-PR in scope.** Moves from ADR 0002 non-goal to an explicit goal.
   Supersedes ADR 0002 decision 10 in part.
4. **Report JSON is the agent contract.** Findings must be self-contained
   enough for a model to act on: remediation payloads with concrete values from
   pack config, code anchors, fix hints. Output verbosity is a release concern.
5. **Platform.** FastAPI backend with a stable, versioned, documented HTTP API
   (`/api/v1`) — supersedes ADR 0002 decision 9's instability allowance. The
   SPA dashboard is served as static assets from the same platform image (no
   CORS). Postgres is the state store (findings history, JSONB report
   artifacts, suppressions, durable job queue); the canonical report JSON
   remains the file-export artifact contract. A separate `conformdag worker`
   process executes scans in subprocesses (crash isolation, timeout, retry,
   cancellation), claiming jobs via `SELECT ... FOR UPDATE SKIP LOCKED`.
   Per-file AST parse caching keyed on content hash supports large codebases.
   Alembic migrations from day one.
6. **Auth.** Single-admin authentication for the platform, needed for
   suppression editing by the platform owner. No multi-user RBAC in this
   release.
7. **Pack distribution.** Git-native `conformdag pack pull <git-url>` first;
   git is the auth boundary, so private repos and deploy keys work. SSO login
   for CLI pack download is DEFERRED: when the platform gains real auth, use
   OAuth 2.0 Device Authorization Grant (RFC 8628), the headless-CLI standard.
   The pull interface must let a platform-backed source slot in later.
8. **Model-agnostic agents.** OpenAI-compatible endpoints are the only
   provider surface.
9. **MCP promoted.** From "after 1.0.0" to a v1.x follow-up; agent-as-tool-user
   makes MCP the canonical interface for external agents.

## Consequences

- ADR 0002 decisions 9 and 10 are **superseded in part** by this ADR: the
  platform exposes a stable, versioned `/api/v1`, and auto-PR is in scope with
  the agent-never-merges constraint.
- The OpenSpec changes `fix-engine-and-codemods`, `platform-server`, and
  `agent-harness` MUST satisfy this ADR.
- Roadmap must be updated to reflect quality-first phasing: Phase 1 core fix
  engine (no LLM needed), Phase 2 platform server, Phase 3 agent harness,
  Phase 4 distribution/integrations (pack pull, GitHub Action, MCP, SSO last).
- The deterministic-scan-is-the-verifier principle from ADR 0002 is unchanged
  and extended to the agent: the agent cannot override deterministic FAILs.
