## Why

ConformDAG's beta is a CLI linter. Airflow usage is concentrated in organizations (Apache 2022 survey: most users in companies with 200+ employees). A 1.0.0 Product Hunt release must be a usable **org governance product**: versioned org policy packs, a self-hosted dashboard, and an agent-assisted author/fix loop — not a generic community-standards toy and not a hosted SaaS.

ADR 0001 still defers dashboard as YAGNI. That bullet is wrong for 1.0.0 and must be superseded in writing before `workspace-and-serve` and `agent-pack-and-fix` are specified.

## What Changes

- Record the 1.0.0 product thesis as a capability spec (`org-governance-1-0`).
- Add ADR 0002 and point ADR 0001 principle 5 (no dashboard) as superseded in part.
- Rewrite [`docs/roadmap.md`](docs/roadmap.md) so 1.0.0 is local `serve` + dashboard + agent extras, not a future online multi-user service.
- **Dashboard is in 1.0.0** (journey D). Implementation lands in a later change; this change is the contract.
- MCP is **not** a 1.0.0 MUST (separate later change).
- No runtime code in this change.

## Capabilities

### New Capabilities

- `org-governance-1-0`: Product-level requirements for ConformDAG 1.0.0 — personas, golden journeys B/D (A as byproduct), git-native org packs, required `conformdag serve` dashboard, agent pack authoring and `fix`, GitHub Action, explicit non-goals (hosted SaaS, MCP-as-blocker, Airflow 2.x image, dbt, auto-PRs, telemetry).

### Modified Capabilities

None (no main specs exist yet).

## Impact

- Docs and ADRs only: `docs/adr/0001-architecture-principles.md`, new `docs/adr/0002-v1-product-thesis.md`, `docs/roadmap.md`, ADR index.
- Downstream OpenSpec changes (`workspace-and-serve`, `agent-pack-and-fix`, `github-action`) MUST satisfy this spec; they MUST NOT contradict it (dashboard cannot be dropped from 1.0.0).
