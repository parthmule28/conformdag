# C46 — Inventory Configuration and Environment Variables

## Role and objective

You are the Build agent for C46. Produce a complete inventory of `CONFORMDAG_*` variables and configuration sources, remove obsolete entries only with proof, and keep secrets environment-only and out of domain functions.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C07/C22/C45.
- Repository-wide environment reads, config models, platform settings, worker settings, semantic provider, runtime, Compose, CI, docs, and tests.

## Current ownership and resulting owner

Environment reads are distributed across CLI/config/platform/worker/semantic/runtime. After this PR, `docs/configuration.md` or `docs/development.md` has a table with variable, secret status, consumer, default, and required condition; application/configuration owns non-secret precedence while adapters resolve secrets.

## Interfaces

Maintain existing variable names unless deprecation evidence exists. Never store API keys, admin tokens, or DSN credentials in `EffectiveScanConfiguration` or serialized report metadata.

## Expected files

- Create/modify: `docs/configuration.md`, config inventory script/tests, `src/conformdag/config.py`, platform settings/worker/semantic/runtime adapters, Compose/CI only for proven stale variables.
- Do not alter unrelated deployment configuration.

## Test-first sequence

1. Search all `os.environ`/settings reads and build the inventory table.
2. Add tests for defaults, required values, secret absence, invalid values, and precedence.
3. Remove/reclassify only proven obsolete variables and update docs/tasks.
4. Run config/platform/worker/semantic/runtime/CLI tests and privacy checks.

## Allowed changes

- Inventory docs/checks, config reads, deprecation notes, and regression tests.

## Non-goals and prohibitions

- Do not move secret resolution into domain/application models.
- Do not silently change defaults or make optional semantic mode required.
- Do not print environment values in diagnostics.

## Verification matrix

- Inventory consistency, config tests, `mise run privacy`, security, default gate, and package/Compose smoke.

## Completion checklist and handoff

- [ ] Every environment variable has a documented owner and lifecycle.
- [ ] Secrets remain environment-only and unlogged.
- [ ] Obsolete values are removed only with evidence.
- [ ] Commit with `docs: inventory configuration sources`; open the PR without merging.
