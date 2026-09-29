# C12 Platform Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in one native/single-session implementation context. No subagent-driven implementation. Steps use checkbox (`- [ ]`) syntax for tracking. Obtain an independent whole-branch review after implementation.

**Goal:** Move repository, scan, baseline, and suppression reads and mutations from FastAPI routes into independently callable platform services without changing the public API.

**Architecture:** Four service modules accept SQLAlchemy `Session` and transport-neutral inputs and return detached contract-ready values or canonical reports. Routes retain auth, request binding, HTTP errors, headers, and export projection; existing atomic DB transition primitives retain lifecycle ownership.

**Tech Stack:** Python 3.12, SQLAlchemy, FastAPI, Pydantic, pytest, SQLite real-session tests, mise/uv.

**Spec:** `docs/superpowers/specs/2026-09-29-c12-platform-services-design.md` (approved at `b53275994b4866190887b2a11c9453f3d3165434`).

## Global Constraints

- Four modules: `platform/services/{repositories,scans,baselines,suppressions}.py`; shared errors exported from `services/__init__.py`.
- No FastAPI, `Request`, `Response`, `HTTPException`, Typer, or transport auth imports in services; no route request models passed to services.
- Preserve all current HTTP paths, auth and 401/503, Pydantic/query validation, statuses/details, response shapes, headers, filters/order, export bytes, report JSON and outcomes.
- Preserve direct-registration directory/file checks and workspace-loading existence-only path-kind checks; both paths enforce `^[a-z0-9][a-z0-9._-]*$` names and platform Airflow-profile validity.
- Ordinary services may `flush()` but never commit; callers commit/rollback; `transition_scan_to_cancelled()` retains its atomic commit/rollback and fencing.
- No schema/migration, runner/worker, pack/workspace-architecture, or C13 route-module changes.

## Review Focus

- A workspace entry pointing to an existing file as repository path still registers, unlike direct registration: characterize and test both paths in Task 1.
- A direct non-HTTP caller supplies a malformed repository name: reject it in Task 1 without relying on route Pydantic.
- An invalid profile on a direct service call: reject without persisting in Task 1.
- A scan exists but its report artifact was pruned: both report and export keep 404 `scan report not available` in Task 2.
- A failed uniqueness flush poisons a session: caller rollback allows the next valid write in Tasks 1 and 4.

## File map

- Create `src/conformdag/platform/services/__init__.py`: shared service errors with message details.
- Create `repositories.py`: direct/workspace registration, listing, existence checks, aggregate wrappers.
- Create `scans.py`: queue, cancel, status/history/findings, report retrieval and service pagination/filter results.
- Create `baselines.py`: baseline eligibility and assignment.
- Create `suppressions.py`: list/create/update and conflict translation.
- Modify `src/conformdag/platform/app.py`: session/commit/rollback, service calls, status translation, transport projection only; keep route registration in place.
- Test `tests/test_platform_services.py` (new real-session tests), `tests/test_platform.py` (HTTP compatibility/characterization). Modify `db.py` only if two services genuinely require the same query primitive. Do not modify `contracts.py`, `workspace.py`, or `aggregates.py` without a demonstrated contract gap.

## Pre-implementation isolation (after plan approval)

- [ ] Wait for the approved plan's **exact-head CI** to pass; record the approved spec and plan commit SHAs. Do not treat this plan's publication as implementation approval.
- [ ] Fetch latest `origin/main`; use `using-git-worktrees` to create a separate `feat/c12-platform-services` implementation worktree based on that exact tip, without moving or deleting either docs-only branch.
- [ ] Carry **only** the approved C12 spec and plan documents onto the feature branch (for example, copy their blobs from the two approved commit SHAs and commit them as docs). Verify each carried file byte-for-byte against its approved Git blob with `git show <approved-sha>:<path>` and `cmp`; never bring unreviewed docs changes or other files along.
- [ ] Confirm the feature branch's base equals the fetched `origin/main`, both documents match the approved heads, the worktree has no unintended tracked/untracked changes, and existing `.serena/` in the docs worktree remains untracked and untouched. Then begin Task 1.

### Task 1: Repository service and workspace compatibility

**Files:** Create `services/__init__.py`, `services/repositories.py`, `tests/test_platform_services.py`; modify repository, workspace-load, overview, and trends handlers in `app.py`; extend `tests/test_platform.py`.

**Interfaces:** Export `ServiceError`, `NotFoundError`, `ConflictError`, `InvalidOperationError` (each initialized with a stable detail string). `register_repository(session: Session, *, name: str, path: str, policy_pack: str | None, airflow_profile: str | None) -> dict[str, str]`; `register_workspace_repositories(session: Session, repositories: Sequence[WorkspaceRepository]) -> int`; `list_repositories(session: Session) -> list[dict[str, str | None]]`; `require_repository(session: Session, repository_id: str) -> RepositoryRow`; `overview(session: Session, *, now: datetime, days: int) -> OverviewResponse`; `repository_trends(session: Session, *, repository_id: str, now: datetime, days: int) -> RepositoryTrendsResponse`. Workspace input is a validated workspace-domain model, never a route payload. Raise `InvalidOperationError` for direct path/name/profile validation and `ConflictError` for duplicate names.

- [ ] **Step 1: Write characterization and failing tests.** In `test_platform.py`, characterize workspace load of an existing file as repo path and an existing directory as policy-pack path, relative resolution, skip-existing count and stored values. In `test_platform_services.py`, assert direct invalid names (`"Bad Name"`, `""`), wrong path kinds, invalid profile, duplicate name/detail, normalized paths, ordered list, workspace skip/count, no commit before caller commit, failed-flush rollback/recovery, and missing trends repository (`"repository not registered"`).
- [ ] **Step 2: Run red tests.** `mise exec -- uv run pytest tests/test_platform_services.py tests/test_platform.py -k 'workspace or repository' -x --tb=short`; existing characterization must pass before refactoring; new service imports/tests fail because service modules are absent.
- [ ] **Step 3: Implement service and delegate handlers.** Validate direct paths with `Path.resolve()` plus `is_dir()`/`is_file()`, workspace paths through `load_workspace()`'s existing existence-only contract; use the shared name pattern and `coerce_platform_airflow_profile()`. Preserve HTTP 422 path details and duplicate 409; route opens session and commits or rolls back, service may flush. Keep pack registration/workspace loading and aggregates implementation in existing owners.
- [ ] **Step 4: Verify.** Run the same filtered command; expect PASS. Run `mise exec -- uv run pytest tests/test_platform_services.py -x --tb=short`; expect PASS.
- [ ] **Step 5: Commit.** `git add src/conformdag/platform/services src/conformdag/platform/app.py tests/test_platform_services.py tests/test_platform.py && git commit -m 'refactor: extract repository platform service'`.

### Task 2: Scan reads and queue/cancel service

**Files:** Create `services/scans.py`; modify scan handlers plus `_load_report` and `_finding_payload` in `app.py`; extend both test files.

**Interfaces:** `queue_scan(session: Session, repository_id: str) -> dict[str, str]`; `cancel_scan(session: Session, scan_id: str) -> dict[str, str]`; `scan_status(session: Session, scan_id: str) -> dict[str, object]`; `scan_history(session: Session, repository_id: str, *, limit: int, offset: int) -> Page[ScanSummaryResponse]`; `load_report(session: Session, scan_id: str) -> ScanReport`; `scan_findings(session: Session, scan_id: str, *, filters: FindingFilters, limit: int, offset: int) -> Page[FindingResponse]`. Define service-owned frozen `FindingFilters` with `status`, `severity`, `policy_id`, `file_path`, `suppressed`, `baseline_status` optional fields and generic/focused `Page[T]` with `items: list[T]`, `total: int`. Keep `FindingResponse`/`ScanSummaryResponse` existing contract values, not HTTP objects. `load_report` preserves the route's collapsed unavailable-report detail.

- [ ] **Step 1: Write failing real-session and HTTP tests.** Assert missing repository queue 404 detail, dashboard trigger/queued status, missing scan cancel 404, terminal/racing cancellation 409 with `"scan already {status}"`, typed transition use, history descending timestamp+id/count/pagination, finding filter case normalization/order/count/baseline-status including no usable baseline, absent scan versus pruned report 404 detail, and exact JSON/SARIF/HTML export bytes. Include route `X-Total-Count` and auth regression.
- [ ] **Step 2: Run red tests.** `mise exec -- uv run pytest tests/test_platform_services.py tests/test_platform.py -k 'scan or finding or export' -x --tb=short`; new service tests fail before extraction.
- [ ] **Step 3: Implement service and delegate handlers.** Move SQL/filter/projection data out of routes, keep response headers and export format/media construction in `app.py`. Invoke `transition_scan_to_cancelled()` verbatim; its commit/rollback is the sole transaction exception. Preserve the 404 `"scan report not available"` mapping for absent scan and absent artifact.
- [ ] **Step 4: Verify.** Re-run filtered tests and `mise exec -- uv run pytest tests/test_platform_services.py -x --tb=short`; expect PASS.
- [ ] **Step 5: Commit.** `git add src/conformdag/platform/services/scans.py src/conformdag/platform/app.py tests/test_platform_services.py tests/test_platform.py && git commit -m 'refactor: extract scan platform service'`.

### Task 3: Baseline service

**Files:** Create `services/baselines.py`; modify baseline handler in `app.py`; extend both test files.

**Interfaces:** `set_baseline(session: Session, repository_id: str, scan_id: str) -> dict[str, str]`; call existing `eligible_baseline()`; repository existence comes from Task 1's `require_repository()`.

- [ ] **Step 1: Write failing tests.** Assert missing repository 404 `"repository not registered"`, missing/cross-repository scan 404 `"scan not found for this repository"`, queued/running/failed/cancelled or `complete=False` 409 `"scan is not eligible as a baseline: it must be a succeeded, complete scan"`, eligible succeeded+complete assignment visible only after caller commit, and matching HTTP behavior.
- [ ] **Step 2: Run red tests.** `mise exec -- uv run pytest tests/test_platform_services.py tests/test_platform.py -k baseline -x --tb=short`; new service tests fail.
- [ ] **Step 3: Implement baseline service and delegate route.** Service mutates without committing; route commits. Keep DB eligibility primitive authoritative and no new baseline schema.
- [ ] **Step 4: Re-run filtered tests.** Same command; expect PASS.
- [ ] **Step 5: Commit.** `git add src/conformdag/platform/services/baselines.py src/conformdag/platform/app.py tests/test_platform_services.py tests/test_platform.py && git commit -m 'refactor: extract baseline platform service'`.

### Task 4: Suppression service

**Files:** Create `services/suppressions.py`; modify suppression handlers and `_suppression_payload` in `app.py`; extend both test files.

**Interfaces:** `list_suppressions(session: Session) -> list[dict[str, object]]`; `create_suppression(session: Session, *, policy_id: str, fingerprint: str, reason: str, owner: str, expires_at: datetime) -> dict[str, object]`; `update_suppression(session: Session, suppression_id: str, *, reason: str | None, owner: str | None, expires_at: datetime | None) -> dict[str, object]`. `SuppressionCreate.expires_at` is required; `SuppressionUpdate` fields are optional and explicit `None` currently means unchanged. `ConflictError` translates only the identifiable unique key.

- [ ] **Step 1: Write failing tests.** Assert chronological list, created `source="platform"` and audit/expiry fields, same `(policy_id, fingerprint)` 409 `"suppression already exists for this policy finding"`, different keys accepted, missing update 404 `"suppression not found"`, omitted/null update unchanged, explicit updates applied, failed-flush rollback then successful insert, and HTTP auth/response parity.
- [ ] **Step 2: Run red tests.** `mise exec -- uv run pytest tests/test_platform_services.py tests/test_platform.py -k suppression -x --tb=short`; new service tests fail.
- [ ] **Step 3: Implement service and delegate routes.** Use `flush()` for uniqueness and stable returned values; caller commits/rolls back. Keep Pydantic parsing in route and no change to operational suppression application.
- [ ] **Step 4: Re-run filtered tests.** Same command; expect PASS.
- [ ] **Step 5: Commit.** `git add src/conformdag/platform/services/suppressions.py src/conformdag/platform/app.py tests/test_platform_services.py tests/test_platform.py && git commit -m 'refactor: extract suppression platform service'`.

### Task 5: Integration, review, and handoff

**Files:** Modify only the C12 row in `docs/consolidation/progress.md` **after** exact implementation-head CI and independent review; touch service/route tests for discovered parity gaps, not unrelated modules.

- [ ] **Step 1: Audit boundary.** Search service imports for `fastapi`, `starlette`, `Request`, `Response`, `HTTPException`, `typer`; search targeted `app.py` handlers for `select(`, `session.get(`, SQL mutation and domain eligibility. Confirm aggregate implementation remains in `aggregates.py`, no new migration, no runner/worker/pack changes.
- [ ] **Step 2: Run full local verification.** `mise run setup`, `mise exec -- uv run pytest tests/test_platform_services.py tests/test_platform.py -x --tb=short`, `mise run check`, `mise run test:coverage`, `mise run schema --check`, `git diff --check`; verify migration/platform tests included and record any unavailable external gate. Fix regressions before claiming completion.
- [ ] **Step 3: Commit, push, and open implementation PR.** Keep useful task commits; add the final product/integration commit as `refactor: extract platform services` to satisfy the C12 prompt. Push the feature branch from its isolated worktree and open an implementation PR against `main`. Do not update the ledger yet.
- [ ] **Step 4: Verify the implementation head and review independently.** Wait for exact implementation-head CI. Obtain an independent whole-branch review focused on service usability without FastAPI, SQL-free route business logic, transaction ownership, and exact HTTP compatibility. Fix Critical/Important findings; if amended, rerun local gates and exact-head CI, then obtain independent re-review when needed.
- [ ] **Step 5: Record evidence last.** Only after the preceding CI/review gate, update **only** the C12 ledger row to `review` with actual local commands/results, implementation-head CI run/SHA, independent review findings, compatibility notes, and outstanding limitations. Make a ledger-only commit, push, await **final PR-head CI**, and stop with the PR open/unmerged. After a separately user-authorized merge and passing post-merge `main` CI, record `accepted` in separate acceptance bookkeeping, not in this implementation PR.

## Execution handoff

This is a docs-only plan for review, not authorization to start product work. After written plan approval and exact-head CI, use native single-session `executing-plans` in the isolated worktree and follow Tasks 1 → 2 → 3 → 4 → integration. Independent whole-branch review follows implementation; no subagent-driven implementation. Preserve the existing `.serena/` files in the docs worktree.
