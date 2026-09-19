# C33 — Split the Test Suite by Responsibility

## Role and objective

You are the Build agent for C33. Break the monolithic platform/CLI/check test files into cohesive modules without changing production behavior or reducing assertions.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C12–C14/C28.
- `tests/test_platform.py`, `tests/test_cli.py`, `tests/test_evaluator.py`, `tests/test_check_pack.py`, `tests/conftest.py`, and nested fixture patterns.
- The current source package layout after completed consolidation slices.

## Current ownership and resulting owner

`tests/test_platform.py` is 4,030 lines and covers API, services, persistence, runner, worker, migrations, gates, and frontend-serving behavior. `tests/test_cli.py` similarly combines command families. After this PR, test paths mirror production ownership and nested fixtures are local to their subsystem.

## Interfaces

Preserve test names and behavior where they are referenced by CI or backlog evidence. Reusable builders may expose typed helpers such as `PolicyPackBuilder` and `RepositoryFixtureBuilder`, but no giant test DSL.

## Expected files

- Create: `tests/platform/{conftest,test_app,test_repositories,test_scans,test_suppressions,test_packs,test_gates,test_aggregates,test_persistence,test_migrations,test_runner,test_worker,test_demo}.py` as needed by actual ownership.
- Create: `tests/cli/{test_scan,test_fix,test_policy,test_pack,test_agent,test_platform,test_benchmark}.py`.
- Create/split: `tests/checks/` and `tests/analysis/` modules where C04/C05 moved code.
- Modify: nested `conftest.py` files and imports; delete monoliths only after collection parity.

## Test-first sequence

1. Collect current tests and save the 410-test baseline plus selected/deselected behavior.
2. Move one cohesive class/function group at a time using test collection checks.
3. Run each new module focused, then compare total collection and pass counts to the baseline.
4. Remove duplicated fixture setup only after tests pass independently.
5. Run `mise run check`, coverage, and round-trip benchmark.

## Allowed changes

- Test file moves/splits, fixture locality, typed builders, imports, and test names where paths require updates.

## Non-goals and prohibitions

- Do not weaken assertions, skip failing tests, or change production behavior to fit a test split.
- Do not create global fixtures for one subsystem.
- Do not turn every repeated literal into a builder.

## Verification matrix

- `pytest --collect-only -q` count and default pass parity.
- Full default suite, coverage, and round-trip benchmark.
- Review that application behavior is not tested only through heavyweight HTTP adapters.

## Completion checklist and handoff

- [ ] Platform/CLI/check tests map to production ownership.
- [ ] Collection and pass counts are accounted for.
- [ ] Fixtures are local and typed.
- [ ] Commit with `test: split subsystem suites`; open the PR without merging.
