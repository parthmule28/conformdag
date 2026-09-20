# C10 — Delegate Platform Scans to the Application Workflow

## Role and objective

You are the Build agent for C10. Remove the platform runner's duplicate complete scan orchestration and make it a persistence/process adapter around `application.execute_scan()`. This is a critical ownership change: prove report parity before deleting runner logic.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C06–C09.
- `src/conformdag/platform/runner.py` in full, especially `execute_scan`, `_apply_platform_suppressions`, `_ingest`, and baseline loading.
- `src/conformdag/application/scan.py`, `application/configuration.py`, `src/conformdag/scan.py`, `src/conformdag/gates.py`, and `src/conformdag/reporting.py`.
- `src/conformdag/platform/db.py`, `worker.py`, and `tests/test_platform.py` runner/gate/suppression/retention cases.

## Current ownership and resulting owner

The runner currently loads config/packs, calls `scan_repository`, applies platform suppressions, normalizes, resolves baselines, evaluates gates, ingests, and transitions state. After this PR, the application workflow owns gate evaluation, operational suppression application, final normalization, and scan outcome; the runner owns claimed-record loading, baseline/suppression adapters, ingestion, cancellation fencing, and state completion.

## Interfaces

- Consumes: `execute_scan()` and `ScanExecutionResult`, `BaselineInput`, canonical `Suppression`, typed scan state, and repository row data.
- Produces: one platform execution path whose canonical pre-persistence report matches the CLI/application report for equivalent inputs.

## Expected files

- Modify: `src/conformdag/platform/runner.py`, `src/conformdag/platform/db.py` adapter calls, and `tests/test_platform.py`/new application parity tests.
- Modify: `src/conformdag/application/scan.py` only for missing explicit ports.
- Do not move ORM models or split FastAPI routes; C24/C13 own those changes.

## Test-first sequence

1. Add a golden parity test comparing CLI/application execution and platform-runner execution before persistence, excluding only timestamps and platform metadata.
2. Add regression tests for retained baseline fingerprints, active/expired suppressions, incomplete reports, cancellation races, and gate results.
3. Run the focused tests against the current duplicated runner and record the expected behavior.
4. Replace runner orchestration with an application request, explicit baseline/suppression conversion, canonical ingestion, and fenced transition.
5. Run application, runner, worker, platform gate/suppression/retention tests, `mise run check`, coverage, and the Postgres gate when configured.

## Allowed changes

- Runner dependency wiring, adapter conversion, ingestion sequencing, and parity/regression tests.
- Move only business logic proven to belong in `application.scan`.

## Non-goals and prohibitions

- Do not keep a second gate evaluator or suppression implementation in the runner.
- Do not weaken cancellation fencing, retention, or report ingestion.
- Do not introduce SQLAlchemy into application code.

## Verification matrix

- Application/platform golden parity.
- Existing platform runner/worker/gate/suppression/retention suite.
- `mise run check`, coverage, and Postgres concurrency checks.
- Independent reviewer must trace every former runner responsibility to exactly one new owner.

## Completion checklist and handoff

- [ ] Runner delegates complete execution to `execute_scan()`.
- [ ] Baseline and platform suppression inputs use canonical application types.
- [ ] Incomplete reports are never marked successful.
- [ ] Cancellation cannot be overwritten by a late result.
- [ ] Commit with `refactor: delegate platform scans to application`; open the PR without merging.
