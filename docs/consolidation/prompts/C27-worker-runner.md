# C27 — Clean Worker and Runner Responsibilities

## Role and objective

You are the Build agent for C27. Make the worker exclusively responsible for process lifecycle and the runner exclusively responsible for claimed application execution, canonical ingestion, and fenced completion.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C10/C24–C26.
- `src/conformdag/platform/worker.py`, `runner.py`, persistence scan functions, application scan workflow, and platform logging.
- Existing worker/runner tests and Postgres/stress test contracts.

## Current ownership and resulting owner

Worker currently claims, launches, polls, heartbeats indirectly, cancels, retries, and retains; runner loads records, invokes scan, applies gates/suppressions, ingests, and transitions. After this PR, worker owns claim/subprocess/poll/heartbeat/cancel/timeout/retry/attempt budget; runner owns application request construction, canonical report ingestion, and fenced finish.

## Interfaces

Retain or improve typed `RunnerOutcome` and define explicit runner result data where tuple-like outcomes obscure error/retry/cancel state. The worker must not inspect findings/gates; the runner must not implement process polling.

## Expected files

- Modify: `platform/worker.py`, `runner.py`, persistence scan functions, `platform/logging.py`, and worker/runner tests.
- Create: focused `tests/platform/test_worker.py` and `test_runner.py` if C33 has split the suite.
- Do not change application scan semantics or HTTP routes.

## Test-first sequence

1. Add process-focused worker tests for launch failure, timeout, SIGTERM/SIGKILL, cancellation, retry budget, heartbeat, and graceful drain.
2. Add runner-focused tests for claimed status, application execution, ingestion, cancellation fencing, and terminal persistence.
3. Run current tests and compare ownership before cleanup.
4. Remove cross-layer leakage and make outcomes typed.
5. Run default, Postgres, stress, and coverage gates.

## Allowed changes

- Worker/runner boundary cleanup, typed outcomes, logging/correlation, and tests.

## Non-goals and prohibitions

- Do not let worker evaluate policies or gates.
- Do not let runner launch/retry child processes.
- Do not change claim fencing, timeout, retention, or cancellation guarantees.

## Verification matrix

- Worker/runner unit suites.
- Postgres integration and repeated stress scenarios.
- `mise run check`, coverage, and security/log privacy review.
- Independent review must trace child lifecycle versus application/persistence ownership and verify cancellation, attempt fencing, retry, and retention boundaries.

## Completion checklist and handoff

- [ ] Worker and runner responsibilities are independently testable.
- [ ] Late results cannot overwrite cancellation or a newer attempt.
- [ ] Correlation fields include scan ID and attempt.
- [ ] Commit with `refactor: separate worker and runner responsibilities`; open the PR without merging.
