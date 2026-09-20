# C08 — Make the Platform Airflow Profile Override Effective

## Role and objective

You are the Build agent for C08. Use the persisted platform repository `airflow_profile` as a validated override in the normal application configuration path. Eliminate the inert configuration field without adding a new scan pipeline or database migration.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C07.
- `src/conformdag/models.py:AirflowProfile` and project runtime config.
- `src/conformdag/platform/db.py:RepositoryRow`, `src/conformdag/platform/app.py:RepositoryCreate`, `src/conformdag/platform/workspace.py`, and `src/conformdag/platform/runner.py`.
- `src/conformdag/application/configuration.py` and `application/scan.py`.
- `tests/test_platform.py`, `tests/test_config.py`, and workspace tests.

## Current ownership and resulting owner

The repository row, API request, and workspace model store `airflow_profile`, but runner execution currently ignores it. After this PR, application configuration resolution validates it as `AirflowProfile` and gives it precedence over the repository's `conformdag.yaml` value. Persisted invalid legacy data becomes a clear configuration failure.

## Interfaces

- Consumes: `RepositoryRow.airflow_profile`, workspace repository profile, `AirflowProfile`, and C07 effective configuration.
- Produces: a validated profile override passed to `execute_scan()`/`scan_repository()` through the existing typed option path.

## Expected files

- Modify: `src/conformdag/application/configuration.py`, `src/conformdag/platform/runner.py`, `src/conformdag/platform/app.py`, and `src/conformdag/platform/workspace.py` only where validation belongs.
- Test: add focused platform/configuration cases; retain current `tests/test_platform.py` until C33 splits it.
- Do not add an Alembic migration or change the `String(32)` column in this PR.

## Test-first sequence

1. Add tests proving repository override wins, omission uses project config, invalid API/workspace values are rejected, and invalid persisted historical data fails the scan clearly.
2. Run focused tests and confirm the stored value is currently ignored.
3. Validate at the API/workspace boundary and again at application resolution for defense in depth.
4. Pass the typed profile through the runner's application request and preserve all other precedence rules.
5. Run platform/config/application tests and `mise run check`.

## Allowed changes

- Typed validation and plumbing of the existing field.
- Clear configuration error reporting and regression tests.

## Non-goals and prohibitions

- Do not accept arbitrary strings in core evaluation.
- Do not change database schema, profile definitions, runtime image selection, or route shapes.
- Do not add profile-specific logic to the worker process.

## Verification matrix

- Focused API/workspace/application/runner tests.
- Full default gate and `mise run test:coverage`.
- Manual review of invalid persisted data handling.

## Completion checklist and handoff

- [ ] `airflow_profile` is no longer inert.
- [ ] API and workspace inputs reject invalid enum values.
- [ ] Historical invalid database values produce a structured failure.
- [ ] Commit with `fix: apply platform airflow profile overrides`; open the PR without merging.
