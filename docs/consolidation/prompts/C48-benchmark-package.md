# C48 — Split Benchmark Concerns

## Role and objective

You are the Build agent for C48. Organize benchmark models, runners, metrics, semantic benchmarking, and reporting without allowing production code to import benchmark code or changing the public benchmark dataset contract.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C35/C37.
- `src/conformdag/benchmark.py`, `benchmark_semantic.py`, `roundtrip.py`, benchmark fixtures/manifests, CLI benchmark command, and benchmark tests.

## Current ownership and resulting owner

Benchmark logic is split across top-level modules and command code. After this PR, a cohesive `src/conformdag/benchmark/` package owns models, runner, metrics, semantic runner, and reporting; production scanner/fixer modules remain independent.

## Interfaces

Preserve benchmark manifest hashes, 240-case public benchmark behavior, 80-case fix round-trip population, CLI command options, and semantic model/cache validation. Benchmark package may import production application/core code; production code must not import benchmark.

## Expected files

- Create: `src/conformdag/benchmark/` modules and compatibility facade(s).
- Remove old benchmark modules only after import/CLI parity.
- Modify: benchmark CLI adapter, fixtures/manifests, `tests/test_benchmark.py`, `tests/test_roundtrip.py`, and semantic benchmark tests.

## Test-first sequence

1. Add import/CLI parity and manifest hash tests.
2. Run benchmark and round-trip tests before movement.
3. Move models/runner/metrics/semantic/reporting groups and retain facades.
4. Run all 240 benchmark cases, 80 round-trip cases, semantic benchmark checks, and default gate.

## Allowed changes

- Benchmark package movement, facade exports, command imports, tests, and docs.

## Non-goals and prohibitions

- Do not let production modules import benchmark modules.
- Do not change fixture admission, hash, case counts, or benchmark labels.
- Do not make benchmark network calls part of the default suite.

## Verification matrix

- Benchmark manifest/admission/hash tests.
- Full deterministic benchmark, round-trip benchmark, semantic benchmark, default gate, and coverage.

## Completion checklist and handoff

- [ ] Benchmark ownership is cohesive and one-way dependent.
- [ ] Dataset and round-trip counts remain unchanged.
- [ ] Old imports/CLI behavior remain compatible.
- [ ] Commit with `refactor: split benchmark package`; open the PR without merging.
