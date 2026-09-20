# C34 — Move Behavior Tests to the Lowest Useful Layer

## Role and objective

You are the Build agent for C34. Reduce adapter-level duplication by proving domain/application behavior directly and keeping HTTP/CLI tests focused on translation, auth, rendering, and exit mapping.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C06/C10/C12/C33.
- Application services/workflow, route modules, CLI modules, current test splits, and the C01–C32 progress evidence.

## Current ownership and resulting owner

The same scenarios are often exercised through platform TestClient, CLI invocation, and core tests. After this PR, application tests thoroughly own baseline/gate/runtime/suppression behavior; HTTP tests own request/auth/status/wire translation; CLI tests own argument/render/exit mapping; future MCP tests will own protocol mapping only.

## Interfaces

No production API change is required. The test contract is a layer matrix documented in `tests/README.md` or `docs/development.md`:

```text
application: governance behavior
HTTP: binding/auth/status/wire response
CLI: argument/render/exit adapter
worker: process lifecycle
runner: application/persistence adapter
```

## Expected files

- Modify: `tests/application/`, `tests/platform/`, `tests/cli/`, `tests/platform/test_runner.py`, and `docs/development.md`.
- Remove only duplicate tests whose behavior is now pinned at a lower layer and whose adapter assertions remain elsewhere.
- Do not change production code unless a missing seam prevents correct isolation.

## Test-first sequence

1. Inventory repeated scenarios and assign one authoritative test layer.
2. Add direct application/service tests for baseline/gate/runtime/suppression and error behavior.
3. Narrow HTTP/CLI tests to translation assertions and run them.
4. Delete only proven duplicate coverage after comparing failure detection.
5. Run default, coverage, Postgres, runtime, frontend, and round-trip gates relevant to touched areas.

## Allowed changes

- Test relocation/deduplication, test helpers, development documentation, and small dependency-injection seams.

## Non-goals and prohibitions

- Do not reduce total meaningful coverage.
- Do not make adapters call private internals merely to avoid creating a service seam.
- Do not turn integration tests into timing-dependent unit tests.

## Verification matrix

- Layered test suites and coverage comparison.
- `mise run check`, coverage, and relevant Postgres/runtime/browser gates.

## Completion checklist and handoff

- [ ] Every major behavior has a lowest-useful-layer owner.
- [ ] Adapter tests still cover wire/exit/auth translation.
- [ ] Test count changes are explained.
- [ ] Commit with `test: align tests with application boundaries`; open the PR without merging.
