# C57 — Characterize Consolidation Performance

## Role and objective

You are the Build agent for C57. Measure performance before final cleanup so abstractions do not introduce unacceptable regressions, and optimize only where measurements identify a real bottleneck.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C35/C48/C56.
- Scan/application/check/cache/runtime/ingest/history/fix code, benchmark fixtures, Postgres queries, and current performance scripts.

## Current ownership and resulting owner

Performance evidence is not a single repeatable artifact. After this PR, a benchmark task measures cold scan, warm parse-cache scan, Ruff scan, large synthetic repository, platform ingest, history/trend query, and fix iteration.

## Interfaces

Record environment, repository size, cache state, iteration count, wall time, and memory where practical. Results are characterization, not an unstable hard gate unless a threshold is justified by baseline data.

## Expected files

- Create/modify: `scripts/benchmark_consolidation.py` or benchmark package, benchmark fixtures, `mise.toml`, and `docs/consolidation/performance.md`.
- Modify production code only for measured optimization with behavior tests.

## Test-first sequence

1. Run baseline measurements on the current consolidated state and save raw/summary output.
2. Add a repeatable command and fixtures for each scenario.
3. Profile the slowest meaningful path and apply one targeted optimization if justified.
4. Rerun correctness, round-trip, Postgres, runtime, and default gates.

## Allowed changes

- Benchmark tooling/docs and measured, tested optimizations.

## Non-goals and prohibitions

- Do not optimize for synthetic microbenchmarks at the expense of security/readability.
- Do not add flaky timing assertions to unit tests.
- Do not make production import benchmark code.

## Verification matrix

- Reproducible benchmark output, default/coverage, round-trip, Postgres/runtime as relevant.

## Completion checklist and handoff

- [ ] All requested scenarios have baseline measurements.
- [ ] Any optimization has before/after evidence and correctness tests.
- [ ] Environment and fixture assumptions are documented.
- [ ] Commit with `perf: characterize consolidation performance`; open the PR without merging.
