# C08 — Apply Platform Airflow Profile Overrides Implementation Plan

> **For agentic workers:** Execution method: Native, single-session. REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a registered platform repository's `airflow_profile` a validated override for core scan evaluation while preserving its string-valued API/workspace/storage surfaces and keeping runtime execution disabled unless project configuration independently enables it.

**Architecture:** Keep `AirflowProfile` validation and precedence within the existing application configuration boundary. API and workspace validators retain strings after checking them against the supported enum; the runner passes persisted strings through an application-owned coercion helper before constructing typed `ScanOverrides`. The runner passes the resolved profile to the existing `scan_repository()` argument and retains its current persistence, failure, and cancellation-fencing responsibilities until C10.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLAlchemy, pytest, Ruff, Pyright, `ruamel.yaml`, mise/uv.

**Spec:** `docs/consolidation/prompts/C08-airflow-profile.md`, plus the approved C08 design clarifications captured in this plan.

## Global Constraints

- Precedence for the effective Airflow profile is platform repository override → project `conformdag.yaml` value → model default.
- `RepositoryCreate.airflow_profile` and `WorkspaceRepository.airflow_profile` remain `str | None`; valid values remain the same strings at API and storage boundaries.
- The `repos.airflow_profile` database column remains `String(32)`; add no Alembic migration or column change.
- Persisted strings are explicitly coerced to `AirflowProfile` in application-owned code before entering `ScanOverrides`; do not trust dataclass annotations or Pydantic `model_copy(update=...)` to validate them.
- A platform profile affects static/core scan evaluation only. It does not enable Docker runtime execution or alter the project runtime image.
- The supported enum currently has one value; test platform-source presence and project fallback rather than inventing a second profile solely to make a distinct-value precedence test.
- Keep configuration resolution inside C07's application configuration path; C08 does not add a scan pipeline, worker-specific profile logic, or C10 runner delegation.
- Invalid legacy values raise a clear `ValueError` inside the runner's existing `PERSISTENT_FAILURES` path; preserve cancellation fencing so a cancellation remains the terminal state.
- Keep the supported profile set unchanged (`AirflowProfile.AIRFLOW_3_3_0`, value `"3.3.0"`).
- Run a separate independent reviewer after implementation. If the reviewer finds a Critical or Important issue, fix it, rerun focused and full verification, push the corrected head, and obtain a re-review of that corrected head before changing the C08 ledger row to `review`.
- Implementation commit: `fix: apply platform airflow profile overrides`; open the implementation PR without merging.

## Review Focus

1. A syntactically valid but unsupported API string such as `"4.0"` must be rejected with HTTP 422; test in Task 2.
2. A workspace containing an unsupported profile must fail workspace loading with `WorkspaceError`, while `"3.3.0"` remains a string; test in Task 2.
3. A historical database row containing an unsupported profile must fail clearly before core scanning; test in Task 3.
4. If cancellation races with validation of a historical invalid value, cancellation must remain the terminal state; test in Task 3.
5. A valid platform profile must reach core evaluation without enabling runtime execution or replacing `runtime.image`; test in Tasks 1 and 3.

---

### Task 1: Add application-owned profile coercion

**Files:**
- Modify: `src/conformdag/application/configuration.py`
- Modify: `src/conformdag/application/__init__.py`
- Test: `tests/application/test_configuration.py`

**Interfaces:**
- Produces: `coerce_platform_airflow_profile(value: str | None) -> AirflowProfile | None` in `application.configuration`, exported through `conformdag.application` for transport adapters.
- `None` stays `None`; the supported string becomes `AirflowProfile.AIRFLOW_3_3_0`; unsupported values raise `ValueError` with the bad value in a clear diagnostic.
- Keep `ScanOverrides.airflow_profile` typed as `AirflowProfile | None`; only a coerced value enters the override object.

- [x] **Step 1: Add coercion contract tests.**

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("3.3.0", AirflowProfile.AIRFLOW_3_3_0),
    ],
)
def test_coerce_platform_airflow_profile(raw: str | None, expected: AirflowProfile | None) -> None:
    assert coerce_platform_airflow_profile(raw) is expected


def test_coerce_platform_airflow_profile_rejects_unsupported_value() -> None:
    with pytest.raises(ValueError, match="unsupported Airflow profile.*4.0"):
        coerce_platform_airflow_profile("4.0")
```

- [x] **Step 2: Run the new tests and confirm they fail because the helper is not yet defined.**

Run: `mise exec -- uv run pytest tests/application/test_configuration.py -k coerce_platform_airflow_profile -x --tb=short`

Expected: collection or test failure identifying the missing `coerce_platform_airflow_profile` symbol.

- [x] **Step 3: Implement the helper in the application configuration module.**

```python
def coerce_platform_airflow_profile(value: str | None) -> AirflowProfile | None:
    if value is None:
        return None
    try:
        return AirflowProfile(value)
    except ValueError as exc:
        supported = ", ".join(profile.value for profile in AirflowProfile)
        raise ValueError(f"unsupported Airflow profile {value!r}; supported values: {supported}") from exc
```

Import the helper from `application.configuration` in `application/__init__.py` and add it to `__all__`. Do not change the resolver's precedence rules or mutate any runtime fields in this task.

- [x] **Step 4: Run the focused configuration tests.**

Run: `mise exec -- uv run pytest tests/application/test_configuration.py -x --tb=short`

Expected: all configuration resolver and coercion tests pass, including the existing platform-profile test that verifies `runtime.enabled` and `runtime.image` are preserved.

- [x] **Step 5: Commit the tested application boundary.**

```bash
git add src/conformdag/application/configuration.py src/conformdag/application/__init__.py tests/application/test_configuration.py
git commit -m "feat: validate platform airflow profile values"
```

### Task 2: Validate API and workspace inputs without changing their string contract

**Files:**
- Modify: `src/conformdag/platform/app.py:RepositoryCreate`
- Modify: `src/conformdag/platform/workspace.py:WorkspaceRepository`
- Test: `tests/test_platform.py` API registration and workspace loader tests

**Interfaces:**
- Both Pydantic models keep `airflow_profile: str | None` and the existing maximum length of 32.
- Each field validator calls `coerce_platform_airflow_profile(value)` for validation and returns the original string unchanged.
- API clients continue to send a string; the database continues to persist a string.

- [x] **Step 1: Add failing HTTP API tests for invalid and valid values.**

Add a registration test that posts `airflow_profile: "4.0"` (within the length bound) and asserts HTTP 422. Add a valid `"3.3.0"` case that verifies the `RepositoryRow` stores exactly the string and `GET /api/v1/repos` returns the same string.

- [x] **Step 2: Run the API tests and confirm unsupported values are currently accepted.**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'airflow_profile' -x --tb=short`

Expected: the unsupported-value test fails because `max_length=32` alone accepts `"4.0"`.

- [x] **Step 3: Add a failing workspace test.**

Load a workspace with an existing repository directory and `airflow_profile: "4.0"`; assert `load_workspace()` raises `WorkspaceError` after C08 validation. The quoted value is required: unquoted YAML `4.0` is a number and may already fail the current `str | None` field validation. Extend the supported-value workspace case to assert the loaded field remains the string `"3.3.0"`.

- [x] **Step 4: Run the workspace tests and confirm the invalid value is currently accepted.**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'workspace_loader_resolves_relative_paths or workspace_rejects_unsupported_airflow_profile' -x --tb=short`

Expected: the unsupported-profile test fails before validator implementation.

- [x] **Step 5: Add field validators that preserve the supplied string.**

Use this pattern in both `RepositoryCreate` and `WorkspaceRepository`:

```python
@field_validator("airflow_profile")
@classmethod
def validate_airflow_profile(cls, value: str | None) -> str | None:
    coerce_platform_airflow_profile(value)
    return value
```

Import `coerce_platform_airflow_profile` from `conformdag.application`. Leave the field annotation, `max_length`, API property type, database model, and migration history unchanged.

- [x] **Step 6: Run the focused API and workspace tests.**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'airflow_profile or workspace_loader_resolves_relative_paths or workspace_rejects_unsupported_airflow_profile' -x --tb=short`

Expected: invalid API/workspace strings are rejected; supported values remain strings through model, route, and storage boundaries.

- [x] **Step 7: Commit the input-boundary validation.**

```bash
git add src/conformdag/platform/app.py src/conformdag/platform/workspace.py tests/test_platform.py
git commit -m "fix: validate platform airflow profile inputs"
```

### Task 3: Apply the validated platform profile in runner core evaluation

**Files:**
- Modify: `src/conformdag/platform/runner.py:execute_scan`
- Modify: `tests/test_platform.py` runner profile and configuration-failure tests
- Test: `tests/application/test_configuration.py` if an explicit fallback assertion is needed

**Interfaces:**
- The runner calls `coerce_platform_airflow_profile(repository.airflow_profile)` inside its existing configuration-resolution `try` block.
- It passes the resulting `AirflowProfile | None` into `ScanOverrides(airflow_profile=...)` and `resolve_effective_configuration()`.
- It calls the existing core path with `scan_repository(repository_root, effective.resolved_policy_pack, airflow_profile=effective.runtime.airflow_version, parse_cache=...)`.
- It does not invoke `execute_scan()`, enable runtime execution, alter the project image, or move runner responsibilities owned by C10.

- [x] **Step 1: Update the valid-profile runner test to assert core receives the enum.**

Change `test_runner_uses_resolved_pack_without_wiring_stored_profile` to assert that its fake `scan_repository` receives `airflow_profile=AirflowProfile.AIRFLOW_3_3_0` when the registered repository carries `"3.3.0"`. Set the project runtime to `enabled: false` with a pinned image and no profile; keep the project pack resolution, gate pack, successful status, and assert that no runtime adapter is invoked. The existing application configuration test continues to pin that a platform profile preserves `runtime.enabled` and `runtime.image`.

- [x] **Step 2: Add runner fallback and legacy-invalid tests before changing the runner.**

Add one case with no repository override and project `runtime.airflow_version: "3.3.0"`; assert core receives that profile. Add one case with neither value; assert the runner explicitly passes `airflow_profile=None`. For a persisted `"4.0"` row, assert `execute_scan()` returns failure, the scan becomes `failed` with an unsupported-profile diagnostic, and the fake core scanner is never called.

- [x] **Step 3: Run the focused runner tests and confirm the missing behavior.**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'runner_uses_resolved_pack or runner_uses_project_airflow_profile or runner_invalid_persisted_airflow_profile' -x --tb=short`

Expected: the platform profile is not present in the core call, and the historical invalid profile is not rejected before scanning.

- [x] **Step 4: Add the invalid-profile cancellation-race regression.**

Make the coercion test seam cancel the running scan immediately before invoking the real coercion on `"4.0"`. Assert the runner returns the cancellation outcome and the stored scan remains `cancelled`; the error must not overwrite cancellation.

- [x] **Step 5: Wire coercion and the effective profile through the existing runner path.**

Within the current `try` block, coerce `repository.airflow_profile`, include it in `ScanOverrides`, resolve the effective configuration, then pass `effective.runtime.airflow_version` to `scan_repository`. Leave the `PERSISTENT_FAILURES` catch, failure transition, `_was_cancelled` behavior, baseline/gate logic, and ingestion path intact.

- [x] **Step 6: Run focused configuration and runner tests.**

Run:

```bash
mise exec -- uv run pytest tests/application/test_configuration.py tests/test_config.py -x --tb=short
mise exec -- uv run pytest tests/test_platform.py -k 'airflow_profile or runner_uses_resolved_pack or runner_uses_project_airflow_profile or runner_invalid_persisted_airflow_profile or runner_invalid_profile_after_cancel' -x --tb=short
```

Expected: platform profile reaches core as an enum; project fallback remains effective; unsupported historical data fails before core scanning; cancellation remains terminal; no test observes Docker runtime being enabled by the profile.

- [x] **Step 7: Run the complete required verification before committing.**

Run, in order:

```bash
mise run check
mise run test:coverage
mise run schema --check
git diff --check
```

Expected: the full gate and coverage gate pass; schema exports remain synchronized; whitespace check is clean. Manually confirm the staged diff has no database model or Alembic migration change and that `runtime.image` and `runtime.enabled` are not modified by the platform override.

- [x] **Step 8: Commit the implementation with the required message.**

```bash
git add src/conformdag/application/configuration.py src/conformdag/application/__init__.py src/conformdag/platform/app.py src/conformdag/platform/workspace.py src/conformdag/platform/runner.py tests/application/test_configuration.py tests/test_platform.py
git commit -m "fix: apply platform airflow profile overrides"
```

### Task 4: Prepare the implementation PR and review evidence

**Files:**
- Modify: `docs/consolidation/progress.md` C08 row after the implementation PR exists

**Interfaces:**
- The implementation PR remains open and unmerged at handoff.
- The C08 progress row changes from `planned` to `review`, cites the real PR/base/head and required verification evidence, and does not claim acceptance before merge.

- [ ] **Step 1: Push the implementation branch and open the PR without merging.**

Push `docs/c08-airflow-profile`, then open a `main`-based PR titled `fix: apply platform airflow profile overrides`. Include API/workspace validation, typed application coercion, runner/core pass-through, invalid persisted-row handling, cancellation fencing, no schema migration, full-gate/coverage/schema evidence, and the intentional non-enabling of runtime execution. Wait for the implementation-head CI and a separate independent review; address findings before recording the review row. If any Critical or Important issue is reported, fix it, rerun focused and full verification, push the corrected head, and obtain a re-review of that corrected head before changing the C08 ledger row to `review`.

- [ ] **Step 2: Record the C08 review row after the PR number and implementation commit are known.**

Change only the C08 row in `docs/consolidation/progress.md` to `review`. Record the implementation commit, PR base, focused test counts, `mise run check`, coverage, schema/whitespace results, and implementation-head CI evidence available at that point. State that the PR is open and unmerged; do not mark it accepted. Do not place a self-referential final PR head or a CI run that has not yet completed in this commit.

- [ ] **Step 3: Commit and push the review-evidence row.**

```bash
git add docs/consolidation/progress.md
git commit -m "docs: record C08 airflow profile review evidence"
git push
```

- [ ] **Step 4: Re-run the final-head checks and stop at review.**

Wait for the final PR head's required CI checks; verify the head SHA and check run IDs; report the PR URL, final head SHA, implementation commit, focused/full test counts, coverage, schema result, and any skipped opt-in jobs. Leave the PR unmerged. After a later authorized merge, record `accepted`, the final PR head, and the actual merge commit in a separate docs-only ledger follow-up.
