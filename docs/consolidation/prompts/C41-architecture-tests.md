# C41 — Add Architecture Dependency Tests

## Role and objective

You are the Build agent for C41. Add a lightweight AST/import validator that enforces layer direction and becomes a project gate after the main application/service boundaries exist.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C12–C14/C24/C28.
- Current package layout, import graph, `pyproject.toml`, `mise.toml`, and CI tasks.
- Existing scripts/test conventions and all compatibility facades.

## Current ownership and resulting owner

No automated check currently prevents application/core code from importing adapters. After this PR, `scripts/verify_architecture.py` and its tests enforce forbidden edges such as application→Typer/FastAPI/SQLAlchemy, checks/analysis→platform, models→adapters, and security→platform/agent.

## Interfaces

The script accepts the repository root (default current directory), parses Python imports with AST, reports file/import/forbidden-layer details, and exits non-zero on violation. `mise run architecture` invokes it; CI may include it after this PR.

## Expected files

- Create: `scripts/verify_architecture.py`, `tests/test_architecture.py` or `tests/architecture/test_imports.py`.
- Modify: `mise.toml`, CI workflow, and docs for exceptions/facades.
- Do not add a large dependency graph framework.

## Test-first sequence

1. Add validator unit tests with temporary fixture packages containing allowed and forbidden imports.
2. Run the test and command to prove violations are detected.
3. Implement AST analysis and an explicit rule table for current packages.
4. Run the validator on the repository, document intentional facade/compat exceptions, and add the task to the appropriate local gate.
5. Run `mise run architecture`, `mise run check`, and full import/type tests.

## Allowed changes

- Lightweight script, rule table, fixtures, task/CI wiring, and documented exceptions.

## Non-goals and prohibitions

- Do not enforce style/complexity through this validator.
- Do not silence violations with broad package exclusions.
- Do not create cyclic imports to satisfy a test.

## Verification matrix

- Validator fixture tests and repository run.
- `mise run architecture`, default gate, Pyright, and package imports.
- Independent review of every exception.

## Completion checklist and handoff

- [ ] Forbidden dependency edges fail clearly.
- [ ] Intentional facades are explicit exceptions.
- [ ] Task is available locally and in CI at the agreed phase.
- [ ] Commit with `test: enforce architecture dependencies`; open the PR without merging.
