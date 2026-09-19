# Roadmap

## Portfolio build (current plan)

The goal: a portfolio-grade product — great experience first, a legible story second,
code quality as the process guarantee. No release dates; sub-projects ship when done.

### Success criteria, in order

1. **Product experience** — the dashboard is beautiful and complete; no dead ends.
2. **Story** — an outsider runs one command, sees the enforcement loop, and understands why the product matters.
3. **Code quality** — TDD throughout, no known bugs, architecture a reviewer would praise.

### Global decisions (approved 2026-09-05)

| Decision | Choice |
|---|---|
| UI scope | Full design system + expanded surface: overview page, repo detail pages, scan detail views with filterable findings |
| Demo | `mise run demo` with seeded realistic data + guided tour overlay + README leading with the demo |
| Feature scope | dbt check pack → MCP server → report diff → scheduled scans + webhooks (in that order) |
| Testing | Backend TDD (red→green→refactor); frontend covered by Playwright e2e on golden journeys |
| Quality gates | Gates live **in the policy pack** (versioned, git-native); baselines live in the platform (per-repo operational state) |
| Gate rule types | `no-new-findings`, `max-severity`, `max-findings`, `always-block`, `failure-rate` |
| Ruff | Composed, not competed with — a `ruff-air` check kind maps AIR violations into findings |
| Process | One sub-project at a time: spec → plan → implement → green gates → commit |

### TDD workflow

1. Red test first (watch it fail for the right reason)
2. Minimal implementation
3. Refactor under green (pyright strict, 0 errors)
4. Full gate: `mise run check` + `mise run test:coverage` (≥90% is the safety net)
5. Test + implementation committed together, conventional-commit message

### Sub-projects

```
P1  Foundation (backend TDD)
    Fix audit findings: pack-service wiring, atomic pack writes, org-pack updates,
    fixability matrix, HTTP timeouts, worker graceful shutdown, structured logging,
    pagination, retention wiring, CORS. DX commands: policy hash, policy new,
    doctor, init→workspace. Quality-gate engine + baseline scans. Ruff AIR adapter.

P2  Design system + UI surface
    Type scale, tokens, component library, light/dark. Overview page (aggregate
    stats + trend charts), repo detail pages, scan detail views with filterable
    findings. Quality-gate configuration + reporting UI. Domain tags on policies.
    Golden journeys as Playwright e2e.

P3  Demo story (shipped)
    mise run demo: seeded realistic repos + scans + suppressions. Guided tour
    overlay (finding → policy → fix payload → suppression → export). README
    rewrite leading with the demo.

P4  dbt check pack (Phase 1)
    models-have-tests, descriptions, naming contracts reading manifest.json.
    New check kinds + evaluators + configs. Establishes the multi-family
    check pattern.

P5  MCP server
    conformdag mcp: scan/fix/explain/policy tools for AI coding assistants.
    Makes the agent story visible in the demo.

P6  Ops features
    report diff (two scans, what changed), scheduled scans (cron per repo),
    webhooks (Slack + generic HTTP).

P7  Check pack wave 2
    Operational checks: sla-defined, pool-bounded, max-active-runs-bounded,
    depends-on-past-policy, deferrable-usage.

P8  Impact graph view (stretch)
    Force-directed graph: policy → repositories → findings; "change this policy,
    these DAGs are affected" on the policy editor.
```

P4/P5/P6/P7/P8 are independent of the UI work and interleave once P1 is stable.

### Shipped so far

- `0.1.0b1` soak release (PyPI + GHCR images + GitHub Release)
- v1 platform: single scan engine, fix engine with verify-by-rescan, agent harness
  (triage → codemod → LLM verifier → human-merged PR), platform server
  (FastAPI + Postgres + worker + Alembic), dashboard SPA, composite GitHub Action,
  `pack pull`, round-trip benchmark gate
- Check pack wave 1: 11 deterministic check kinds including TaskFlow decorator
  analysis, start-date-freshness, catchup-policy, module-scope-variables,
  sensitive-logging, dynamic-dag-factory (branch `feat/policy-management`)
- Policy management backend (PackService + /api/v1/packs CRUD + auto-hash)
- Dashboard 2.0: dark theme, navigation, policies page, suppression management
- AGENTS.md for OpenCode sessions
- P3 demo story: `mise run demo` disposable local launcher, seeded platform
  scenario (repos, scans, findings, gates, suppressions), guided browser tour,
  and demo-first documentation (README + user guide)
