# C64 — Publish the Final Consolidation Report

## Role and objective

You are the Build agent for C64. Close the program with evidence, metrics, compatibility notes, intentional limitations, and readiness assessment for MCP, dbt, report diff, scheduled scans, webhooks, and enterprise integrations.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C60–C63.
- Every accepted slice row, PR/evidence link, baseline metrics, security/architecture/threat reviews, release rehearsal, and final verification outputs.

## Current ownership and resulting owner

Consolidation status is currently distributed across PRs and progress notes. After this PR, `docs/consolidation/progress.md` becomes final evidence and `docs/consolidation/final-report.md` summarizes starting/ending SHAs, PRs, metrics, coverage, dependencies, packaging, compatibility, diagrams, limitations, and readiness.

## Interfaces

The report must state whether these criteria are demonstrably true: one application scan workflow, one check catalogue, thin adapters, isolated Airflow analysis, reusable services, typed platform contracts, shared redaction, filesystem/runtime/Git safety, Postgres coverage, true production coverage, audited release artifacts, current docs, and extension readiness.

## Expected files

- Create/modify: `docs/consolidation/final-report.md`, `progress.md`, `backlog.md`, and links to accepted PR/evidence artifacts.
- Do not mark a slice accepted without a command/result or independent review record.

## Test-first sequence

1. Validate that every C01–C64 row has a status, prompt, dependency outcome, and evidence.
2. Re-run final `mise run check` and required expensive gates from C63/C62/C60.
3. Reconcile metrics against `baseline.md`, separating measured changes from unavailable values.
4. Write the final report and run Markdown/link, placeholder, architecture, schema, package, security, and release checks.

## Allowed changes

- Final evidence/report/ledger updates and corrections required by final verification.

## Non-goals and prohibitions

- Do not claim future MCP/dbt/scheduler/webhook features are implemented.
- Do not hide blocked/split slices or failed evidence.
- Do not merge branches or publish artifacts as part of the report.

## Verification matrix

- All local and relevant expensive gates, historical audit replay, security/architecture reviews, package/release rehearsal, and link validation.

## Completion checklist and handoff

- [ ] Every C01–C64 slice has honest final status and evidence.
- [ ] Before/after metrics and intentional limitations are clear.
- [ ] Readiness claims are tied to existing interfaces, not folder names.
- [ ] Commit with `docs: publish consolidation final report`; open the final PR without merging.
