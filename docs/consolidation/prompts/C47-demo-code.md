# C47 — Separate Demo Construction from Production Package Code

## Role and objective

You are the Build agent for C47. Determine whether platform demo fixture construction is public production behavior; if it is only developer/demo support, move it under a devtools/demo surface while retaining production-faithful execution.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C28/C38.
- `src/conformdag/platform/demo.py` if present, demo scripts/tasks, package configuration, tests, Compose files, and docs.

## Current ownership and resulting owner

Demo code may be bundled with the production platform package even when it only constructs synthetic scenarios. After this PR, synthetic fixture construction belongs in `devtools/demo/` or an explicitly documented demo package; the real Alembic/worker/runner/scan/platform/frontend path remains unchanged.

## Interfaces

Preserve the documented demo command and user-visible scenario behavior. Production code may expose only the minimal hook required to boot the real services.

## Expected files

- Move/create: demo fixture builders under `devtools/demo/` or the established development location.
- Modify: `mise.toml`, demo tests/docs, packaging include rules, and imports.
- Do not delete demo behavior or replace real execution with mocks.

## Test-first sequence

1. Search all imports/entry points and run the current demo/test path when one exists; if no demo task exists, define the documented `mise run demo` task as part of this slice before continuing.
2. Add a clean-package assertion proving fixture construction is not required by ordinary runtime imports.
3. Move synthetic construction and update task/import paths.
4. Run demo, platform, worker/runner, frontend, package, and default checks.

## Allowed changes

- Demo location, task wiring, package inclusion, tests, and docs.

## Non-goals and prohibitions

- Do not alter production scan semantics or remove real service execution.
- Do not include developer-only dependencies in the wheel.
- Do not use demo fixtures to bypass migrations or security boundaries.

## Verification matrix

- The demo task defined or retained by this PR, package smoke, platform/SPA boot, and the default gate.

## Completion checklist and handoff

- [ ] Demo fixture ownership is explicit.
- [ ] Production package no longer carries proven developer-only code.
- [ ] Demo remains production-faithful.
- [ ] Commit with `refactor: isolate demo fixtures`; open the PR without merging.
