# C37 — Audit Dependency Ownership

## Role and objective

You are the Build agent for C37. Produce an accurate direct/development dependency inventory, remove only proven unused dependencies, and make dependency drift detectable.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C35.
- `pyproject.toml`, `uv.lock`, `docs/dependency-inventory.md`, import graph, build scripts, frontend package manifests, and CI workflows.

## Current ownership and resulting owner

Direct dependencies are declared but their owners and install surfaces are documented separately. After this PR, each Python/frontend/tool dependency has owner, reason, install surface, and dev/runtime classification; an inventory check detects lockfile/manifest drift.

## Interfaces

Keep runtime dependencies minimal and preserve the platform extra. Use `deptry` or an equivalent audit as an analysis tool only; the repository's inventory script/task is the source of truth if already present.

## Expected files

- Modify: `docs/dependency-inventory.md`, `pyproject.toml`, `uv.lock`, frontend package manifests, `mise.toml`, and inventory scripts only for proven findings.
- Create: a focused dependency consistency test/script if the current one does not cover all surfaces.
- Do not remove a dependency based solely on an unused-import heuristic when it owns packaging/runtime behavior.

## Test-first sequence

1. Run the existing inventory task if one is present; otherwise perform the direct manifest/lockfile audit that this PR will turn into the inventory task, then run `deptry`, `pip-audit`, and frontend install/build checks.
2. Map every direct dependency to imports/scripts/package assets.
3. Remove or reclassify only proven unused entries and refresh the lockfile.
4. Run clean setup in an isolated environment and verify CLI/platform/frontend imports.
5. Run the inventory task created or retained by this PR, `mise run security`, `mise run check`, and package smoke.

## Allowed changes

- Inventory documentation, dependency declarations/lockfile, and consistency checks.

## Non-goals and prohibitions

- Do not upgrade unrelated dependencies for convenience.
- Do not move platform packages into core or dev-only packages into production.
- Do not store secrets in dependency/config files.

## Verification matrix

- Inventory/lockfile consistency, pip-audit, gitleaks, default gate, frontend build, and installed-wheel import smoke.

## Completion checklist and handoff

- [ ] Every direct dependency has an owner and reason.
- [ ] Removed dependencies are proven unused.
- [ ] Clean setup reproduces the lockfile.
- [ ] Commit with `chore: audit dependency ownership`; open the PR without merging.
