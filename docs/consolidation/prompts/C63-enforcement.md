# C63 — Enforce the Final Architecture Gates

## Role and objective

You are the Build agent for C63. Tighten the default project gates only after the architecture validator, import audit, configuration inventory, documentation, package, and release evidence are stable.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C41/C42/C46/C52/C62.
- `mise.toml`, CI workflows, schema/API generation tasks, dependency/privacy/security scripts, and all final verification artifacts.

## Current ownership and resulting owner

`mise run check` currently covers format, lint, typecheck, default tests, and pack validation. After this PR, it also includes the agreed architecture validator, generated API-type drift check, dependency inventory, and other cheap deterministic checks; expensive Postgres/Docker/browser/benchmark/review gates remain dedicated.

## Interfaces

The local default gate must be reproducible without Docker unless a documented project policy changes. Every added task has a clear exit code and does not mutate source/generated artifacts during check mode.

## Expected files

- Modify: `mise.toml`, CI workflow, scripts/validators, `AGENTS.md`, docs, and generated-check configuration.
- Do not change product behavior or add gates whose evidence is not stable.

## Test-first sequence

1. Run each candidate validator in check mode and record runtime/output.
2. Add failing CI/task assertions for stale architecture/API/dependency/inventory states.
3. Wire cheap deterministic checks into `mise run check`; keep expensive checks in named tasks/jobs.
4. Run local check twice from clean generated state and compare output.
5. Run the full final verification matrix.

## Allowed changes

- Task/CI enforcement, check-mode validators, docs, and generated-artifact drift checks.

## Non-goals and prohibitions

- Do not make checks mutate files silently.
- Do not hide failures behind `|| true`, broad skips, or network-only behavior.
- Do not add architecture exceptions without documentation and review.

## Verification matrix

- `mise run check`, architecture, API-type, inventory, schema, security/privacy, package, Postgres/runtime/browser/benchmark jobs as applicable.

## Completion checklist and handoff

- [ ] Cheap final invariants are enforced locally and in CI.
- [ ] Expensive gates remain visible and separate.
- [ ] Check mode is deterministic and non-mutating.
- [ ] Commit with `ci: enforce consolidation architecture gates`; open the PR without merging.
