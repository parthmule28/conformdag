# C40 — Consolidate CI Verification Jobs

## Role and objective

You are the Build agent for C40. Align CI with local `mise` tasks and make verification tiers explicit without hiding expensive integration gates or duplicating command logic across workflows.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C35/C37–C39.
- `mise.toml`, all `.github/workflows/*.yml`, package/frontend/runtime/Postgres scripts, and release docs.

## Current ownership and resulting owner

Local tasks and CI commands can drift. After this PR, project tasks are the command source of truth; CI jobs invoke them with explicit services/markers. Desired conceptual jobs are static, unit, coverage, frontend, Postgres, runtime, benchmark, security, package, and browser.

## Interfaces

Preserve `mise run check` as the default local gate. Add dedicated tasks only for expensive gates and make their prerequisites/credentials/services visible.

## Expected files

- Modify: `.github/workflows/`, `mise.toml`, release/development docs, and CI helper scripts.
- Do not change product code or loosen a gate to make CI green.

## Test-first sequence

1. Compare local task commands to each workflow and list drift.
2. Add/update CI validation for default gate, coverage, frontend, Postgres, runtime, benchmark, security, package, and browser tiers.
3. Run local task commands and workflow syntax/action checks.
4. Exercise service jobs locally where practical and inspect artifact retention.
5. Run `mise run check`, inventory/security/package gates.

## Allowed changes

- Workflow/task deduplication, service setup, job names/dependencies, and documentation.

## Non-goals and prohibitions

- Do not make Docker/Postgres mandatory for the fast default gate without an explicit project decision.
- Do not duplicate long command sequences in YAML when a `mise` task can own them.
- Do not silently remove benchmarks/security/package verification.

## Verification matrix

- Local task runs, workflow syntax, package/security/privacy checks, and relevant integration jobs.

## Completion checklist and handoff

- [ ] Local and CI default gates match.
- [ ] Expensive jobs are explicit and separately observable.
- [ ] CI does not hide service failures or secrets.
- [ ] Commit with `ci: consolidate verification jobs`; open the PR without merging.
