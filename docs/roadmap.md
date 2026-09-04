# Roadmap

## Beta foundation

- [x] Bootstrap the Python/mise project and public schemas.
- [x] Implement six deterministic Airflow policies and canonical report formats.
- [x] Add the constrained, maintained Airflow 3.3.0 runtime profile; exclude the EOL 2.11.2 candidate from beta publication.
- [x] Wire opt-in BYOK semantic evaluation for four semantic policies.
- [x] Build a 240-case deterministic benchmark and CI release gates.
- [x] Configure protected-main review, PyPI trusted publishing, and staged release jobs.
- [x] Record provider-backed integration measurements and semantic accuracy limitations.
- [x] Publish `0.1.0b1` after all release evidence is reviewed. Published 2026-08-01 to
  PyPI and GHCR from tag `v0.1.0-beta.1`; see the [release checklist](release.md).
- [x] Bundle a community policy pack with `--policy-pack community` (PR #11).

## 1.0.0 (org governance product)

See [ADR 0002](adr/0002-v1-product-thesis.md) and
[ADR 0003](adr/0003-v1-agentic-platform-architecture.md), plus OpenSpec
`org-governance-1-0`. Shape: two tiers — the PyPI package stays a pure
offline tool; a Docker Compose platform serves governance teams. The agent is
a tool user of the deterministic engine: codemods generate fixes, an
LLM-verifier reviews them, humans merge the PRs. Not a ConformDAG-hosted
SaaS. Quality-first with no external date: 1.0.0 ships only when all four
capability changes land and the release gates pass.

- [x] Publish `0.1.0b2` (bridge): exactly current `main` — bundled community
  pack and provenance fixes plus release chores; no new features. (Deferred to
  the next release train; the bridge content is already on `main`.)
- [x] Phase 1 — fix engine (`fix-engine-and-codemods`): codemod registry,
  verify-by-rescan, agent-readable findings, round-trip benchmark gate. Implemented
  on `main` (2026-09-02); all gates green.
- [x] Phase 2 — platform (`platform-server`): `serve` + worker + Postgres +
  SPA, stable `/api/v1`, single-admin auth, suppression lifecycle. Implemented
  with Alembic migrations and the dashboard SPA scaffold.
- [x] Phase 3 — agent (`agent-harness`): triage, LLM-verifier, auto-PR via
  App token (never merges), policy-review local mode. Implemented.
- [x] Phase 4 — distribution (`distribution-and-ci`): `pack pull`
  (git-native), composite GitHub Action with SARIF and blocking semantics. Implemented.
- [ ] Publish `1.0.0`.

## After 1.0.0

- MCP server (first v1.x follow-up per ADR 0003).
- SSO pack download via OAuth device flow (RFC 8628); platform-backed pack
  source behind `pack pull`.
- Signed/versioned policy bundle distribution (OCI/HTTP) if demand emerges.
- Dashboard multi-user roles if self-hosted teams require it.
- dbt support after Airflow quality and demand gates pass.
- Additional exporters and repository integrations.
