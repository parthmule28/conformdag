# C28 — Split the CLI into Adapter Modules

## Role and objective

You are the Build agent for C28. Split the 1,000-line Typer module after application, policy, platform, and registry logic has reusable owners. Keep `conformdag.cli:app` and every supported command stable.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C06/C12/C16.
- Full `src/conformdag/cli.py`, project script entry point in `pyproject.toml`, application services, policy editing/loading, platform services, agent modules, benchmark modules, and CLI tests.

## Current ownership and resulting owner

`cli.py` currently composes Typer commands and contains policy scaffolding, scan/fix orchestration, runtime, agent, platform, and benchmark behavior. After this PR, `cli/app.py` registers commands; `cli/common.py` owns small shared presentation/exit helpers; command modules own only argument mapping and rendering.

## Interfaces

Preserve `conformdag.cli:app` entry point and command names/options. The command modules call application/policy/platform/agent/benchmark services and return/print their results; they do not evaluate governance rules.

## Expected files

- Create: `src/conformdag/cli/__init__.py`, `app.py`, `common.py`, `scan.py`, `fix.py`, `policy.py`, `pack.py`, `agent.py`, `platform.py`, `benchmark.py`.
- Replace: `src/conformdag/cli.py` with a compatibility facade first; build and smoke-test the wheel with the facade in place, then decide whether changing the script target is necessary.
- Modify: `tests/cli/` or current CLI tests and `pyproject.toml` only if entry-point target must change.

## Test-first sequence

1. Add command registration/help/import parity tests and capture current exit/output behavior.
2. Run all CLI tests before movement.
3. Move command groups after their business logic has an application/service owner; preserve option defaults and aliases.
4. Run command-specific tests and installed package `conformdag --help`/version smoke.
5. Run `mise run check`, coverage, pack validation, and package build smoke.

## Allowed changes

- CLI file movement, registration, argument mapping, rendering helpers, and test split.

## Non-goals and prohibitions

- Do not create a generic CLI framework.
- Do not put runtime/gate/policy mutation logic back into command modules.
- Do not silently change command names, entry points, or exit codes.

## Verification matrix

- Full CLI tests and command help snapshots.
- `mise run check`, coverage, `mise run build`, and isolated wheel smoke.

## Completion checklist and handoff

- [ ] CLI modules are transport adapters only.
- [ ] `conformdag.cli:app` remains importable.
- [ ] Installed-wheel entry point works.
- [ ] Commit with `refactor: split CLI adapters`; open the PR without merging.
