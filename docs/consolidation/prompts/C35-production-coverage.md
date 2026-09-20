# C35 — Measure True Production Coverage

## Role and objective

You are the Build agent for C35. Remove broad production coverage exclusions incrementally and add meaningful tests for CLI, runtime, semantic, benchmark, and benchmark-semantic code until the real production source remains at or above 90% coverage.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C33–C34.
- `pyproject.toml` coverage configuration and every current omitted module.
- `src/conformdag/cli.py` or CLI package, `runtime/`, `semantic/`, `semantic_evaluator`, `benchmark.py`, `benchmark_semantic.py`, and their tests.

## Current ownership and resulting owner

The configured report omits six production surfaces. After this PR, omissions are removed only as each module receives boundary-appropriate tests; integration-only code may use focused mocked adapters plus dedicated real integration gates.

## Interfaces

Keep `--cov=conformdag --cov-fail-under=90` as the gate. Record the true total and branch coverage in progress evidence; do not replace exclusions with lower thresholds.

## Expected files

- Modify: `pyproject.toml` coverage omit list.
- Create/modify: `tests/cli/`, `tests/runtime/`, `tests/semantic/`, `tests/benchmark/`, and application tests.
- Do not alter production behavior solely to make an uncovered branch easier to test.

## Test-first sequence

1. Run coverage with current omissions and save the report.
2. Remove one omission and add tests for command mapping, Docker argument/manifest boundaries, provider/cache/schema failures, benchmark manifests/metrics, and error paths.
3. Run the focused suite and inspect missing branches.
4. Repeat until every removal has meaningful tests and the gate remains at least 90%.
5. Run full default, runtime, semantic, benchmark, round-trip, privacy, and package checks as applicable.

## Allowed changes

- Coverage configuration, boundary mocks/fixtures, tests, and small testability seams.

## Non-goals and prohibitions

- Do not broad-exclude difficult code or mark tests skipped to improve the number.
- Do not execute repository Python or make semantic/network calls in default tests.
- Do not remove integration gates because unit mocks exist.

## Verification matrix

- `mise run test:coverage` with the actual production source.
- Runtime, semantic, benchmark, CLI, round-trip, privacy, and default gates.

## Completion checklist and handoff

- [ ] Omitted production modules are removed or individually justified with a documented integration boundary.
- [ ] True production coverage is at least 90%.
- [ ] New tests assert behavior, not line execution only.
- [ ] Commit with `test: cover production modules`; open the PR without merging.
