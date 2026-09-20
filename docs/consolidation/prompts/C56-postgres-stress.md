# C56 — Run Postgres Concurrency and Stress Scenarios

## Role and objective

You are the Build agent for C56. Add a slower stress task that repeatedly exercises production Postgres worker claims, cancellation, stale reclaim, heartbeats, first boot, retention, and attempt fencing without making ordinary unit tests timing-fragile.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C26/C27/C55.
- Postgres fixtures, persistence transitions, worker/runner, migration lock, Compose/CI, and current integration suite.

## Current ownership and resulting owner

C26 proves individual production semantics; this PR adds repeated multi-worker/race scenarios and keeps them in a separate stress task such as `mise run test:stress`.

## Interfaces

Stress scenarios include 10 workers over queued scans, cancellation during execution, stale reclaim during heartbeat edges, parallel first boot/migrations, retention under concurrent completion, and attempt-budget exhaustion. Results report seed/iteration and preserve failure artifacts.

## Expected files

- Create/modify: `tests/stress/`, `mise.toml`, CI scheduled/manual workflow, Postgres/Compose fixtures, and stress docs.
- Do not change production timing constants merely to make stress pass; fix proven state bugs in persistence/worker.

## Test-first sequence

1. Add one deterministic stress scenario with bounded iterations and explicit cleanup.
2. Run it against real Postgres and observe flake/failure diagnostics.
3. Add remaining scenarios and repeat at least the configured seed count.
4. Run C26 integration, default gate, security, and worker/runner tests.

## Allowed changes

- Stress fixtures/task/CI scheduling, diagnostics, and proven concurrency fixes.

## Non-goals and prohibitions

- Do not turn ordinary tests into sleeps/races.
- Do not hide flaky failures by raising timeouts without evidence.
- Do not use SQLite for this stress contract.

## Verification matrix

- Dedicated `mise run test:stress` against Postgres, C26 suite, default gate, and evidence artifact.
- Independent review must inspect seeds, iteration bounds, cleanup, and whether failures prove database fencing rather than timing luck.

## Completion checklist and handoff

- [ ] Stress task is separate and reproducible with seed/iteration output.
- [ ] Worker ownership/cancellation/fencing remains correct under repetition.
- [ ] Failures preserve enough evidence to diagnose.
- [ ] Commit with `test: add postgres concurrency stress suite`; open the PR without merging.
