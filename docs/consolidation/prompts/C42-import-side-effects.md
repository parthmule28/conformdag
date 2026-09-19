# C42 — Audit Import-Time Side Effects

## Role and objective

You are the Build agent for C42. Prove that importing core, application, semantic, platform, and future adapter packages does not migrate databases, start threads, create clients, execute Docker, inspect secrets unnecessarily, or mutate the filesystem.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C41.
- Package `__init__.py` files, `platform/db.py`/persistence, worker, runtime, semantic provider/cache, CLI, and future package facades.
- Existing import/smoke tests and startup code.

## Current ownership and resulting owner

Import-time behavior is not centrally documented. After this PR, each package's import contract is tested, and side effects occur only in explicit factories/commands (`create_session_factory`, `run_worker`, provider construction, Docker execution, CLI app invocation).

## Interfaces

Add clean-environment import smoke tests for `conformdag.application`, `analysis`, `checks`, `semantic`, `runtime`, `platform`, `agent`, and CLI package/facade. Tests must patch/deny filesystem, subprocess, thread, network, and DB side effects where needed.

## Expected files

- Create/modify: `tests/test_imports.py` or `tests/architecture/test_imports.py`, package initializers, and docs if a side effect needs relocation.
- Do not change explicit startup or command behavior.

## Test-first sequence

1. Add import smoke tests with side-effect sentinels.
2. Run them and identify any current violations.
3. Move side effects behind explicit functions/factories without changing behavior when invoked.
4. Run import tests, architecture validator, default gate, runtime/platform smoke as applicable.

## Allowed changes

- Import initializers, lazy factory boundaries, smoke tests, and documentation.

## Non-goals and prohibitions

- Do not hide required startup migrations or worker initialization.
- Do not read secrets merely to import a provider class.
- Do not introduce global clients/threads.

## Verification matrix

- Clean import suite, architecture task, default gate, package import smoke.

## Completion checklist and handoff

- [ ] Major packages import without operational side effects.
- [ ] Explicit startup/command behavior remains available.
- [ ] Failures identify the import and side effect.
- [ ] Commit with `fix: remove import-time side effects`; open the PR without merging.
