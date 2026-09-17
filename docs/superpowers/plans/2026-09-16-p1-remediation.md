# P1 Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every confirmed P1 correctness blocker so P2 can build on reliable governance, platform, policy-persistence, analysis, and auto-fix behavior.

**Architecture:** Keep `scan_repository()` as the only evaluation path and make pack loading the single validation boundary. Establish durable scan/baseline state invariants before repairing worker lifecycle and persistence, then harden auto-fix and TaskFlow behavior against those invariants. Each task carries its own failing regression, focused gate, full check, coverage gate, commit, and independent review.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, SQLAlchemy/Alembic, PostgreSQL/SQLite, ruamel.yaml, React/TypeScript, pytest, Ruff, Pyright, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-16-p1-remediation-design.md`

## Global Constraints

- Preserve `scan_repository()` as the sole evaluation pipeline.
- Use strict TDD: each production behavior requires a focused test that is observed failing for the intended reason before implementation.
- `mise run check` and `mise run test:coverage` with at least 90% coverage are required for every task.
- Run `mise run schema:update` after Pydantic model changes and commit generated schemas.
- Pyright remains strict with zero errors; use no broad type-ignore comments.
- Use ruamel.yaml and existing typed project helpers; do not introduce PyYAML.
- Never write source changes unless fix verification completed with a complete parseable rescan.
- Do not add P2 UI features, semantic/BYOK configuration, OpenAPI cleanup, or unrelated refactoring.
- Do not push, merge, publish, or modify OpenCode configuration.

---

### Task 1: Authoritative Pack And Gate Validation

**Files:**
- Modify: `src/conformdag/policy.py`
- Modify: `src/conformdag/gates.py`
- Modify: `src/conformdag/cli.py`
- Modify: `src/conformdag/platform/packs.py`
- Test: `tests/test_policy.py`
- Test: `tests/test_gates.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: `CHECK_EVALUATORS: dict[str, DeterministicEvaluator]` and `validate_quality_gates(pack) -> list[str]`.
- Produces: `validate_policy_pack(pack: PolicyPack) -> list[str]`, called by `load_policy_pack()` after Pydantic and provenance validation.
- Guarantees: all CLI, scan, platform, workspace, and mutation callers reject unknown deterministic/hybrid checks and malformed gate references before evaluation.

- [ ] **Step 1: Add failing pack-boundary regressions**

```python
def test_load_policy_pack_rejects_unknown_deterministic_check(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path, deterministic_checks=["missing-check"])
    with pytest.raises(PolicyValidationError, match="unknown deterministic check"):
        load_policy_pack(pack_path, tmp_path)


def test_load_policy_pack_rejects_unknown_gate_policy(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path, gate_policy_ids=["AIR-MISSING-001"])
    with pytest.raises(PolicyValidationError, match="unknown policy ids"):
        load_policy_pack(pack_path, tmp_path)
```

- [ ] **Step 2: Verify the tests fail because loading currently omits registry/gate validation**

Run: `mise exec -- uv run pytest tests/test_policy.py -k "unknown_deterministic_check or unknown_gate_policy" -x --tb=short`

Expected: both packs load or fail later than `load_policy_pack()`.

- [ ] **Step 3: Implement one authoritative validation function**

```python
def validate_policy_pack(pack: PolicyPack) -> list[str]:
    from conformdag.evaluator import CHECK_EVALUATORS
    from conformdag.gates import validate_quality_gates

    issues = validate_quality_gates(pack)
    for policy in pack.policies:
        for check in policy.enforcement.deterministic_checks:
            if check not in CHECK_EVALUATORS:
                issues.append(f"{policy.id}: unknown deterministic check {check!r}")
    return issues
```

Call it from `load_policy_pack()` and remove duplicate CLI/PackService-only registry or gate checks where they no longer add information.

- [ ] **Step 4: Prove every entry point fails closed**

Add focused CLI `scan`, `validate-policies`, PackService validation, and workspace registration assertions that all surface `PolicyValidationError`/HTTP 422 for the same malformed pack.

Run: `mise exec -- uv run pytest tests/test_policy.py tests/test_cli.py tests/test_platform.py -k "unknown_check or unknown_gate" -x --tb=short`

Expected: PASS.

- [ ] **Step 5: Run gates and commit**

Run: `mise run check && mise run test:coverage`

Commit: `fix: fail closed on invalid policy packs`

---

### Task 2: Scan Completion, Gates, Baselines, And Suppressions

**Files:**
- Modify: `src/conformdag/gates.py`
- Modify: `src/conformdag/platform/app.py`
- Modify: `src/conformdag/platform/runner.py`
- Modify: `src/conformdag/cli.py`
- Test: `tests/test_gates.py`
- Test: `tests/test_platform.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: validated packs from Task 1 and retained normalized `FindingRow` fingerprints.
- Produces: `eligible_baseline(session: Session, repository_id: str, scan_id: str) -> ScanRow | None` in `platform/db.py`, shared by API and runner.
- Guarantees: succeeded implies complete; baseline means same repository plus succeeded and complete; operational suppressions alter persisted findings before gates are evaluated.

- [ ] **Step 1: Add failing semantic and lifecycle regressions**

```python
def test_always_block_includes_nonblocking_semantic_failures() -> None:
    finding = make_finding(policy_id="AIR-SEM-001", enforcement="semantic", blocking=False)
    result = evaluate_gate(always_block_gate("AIR-SEM-001"), report(finding), None)
    assert result.passed is False


def test_runner_marks_incomplete_report_failed(platform_env: str, tmp_path: Path) -> None:
    scan_id = queue_repository_with_syntax_error(platform_env, tmp_path)
    assert execute_scan(scan_id, platform_env) == 1
    assert load_scan(platform_env, scan_id).status == "failed"
```

Add API/CLI cases rejecting queued, failed, cancelled, incomplete, and cross-repository baselines. Add a platform suppression case where a matching unexpired `SuppressionRow` makes the ingested finding suppressed and prevents gate failure.

- [ ] **Step 2: Verify focused red failures**

Run: `mise exec -- uv run pytest tests/test_gates.py tests/test_platform.py tests/test_cli.py -k "always_block or incomplete_report or baseline_eligibility or applies_platform_suppression" -x --tb=short`

Expected: failures reproduce current fail-open behavior.

- [ ] **Step 3: Implement shared baseline eligibility and suppression application**

```python
def eligible_baseline(session: Session, repository_id: str, scan_id: str) -> ScanRow | None:
    scan = session.get(ScanRow, scan_id)
    if scan is None or scan.repository_id != repository_id:
        return None
    if scan.status != "succeeded" or scan.complete is not True:
        return None
    return scan
```

Apply active suppression rows to canonical findings before `evaluate_pack_gates()` and `_ingest()`. For `AlwaysBlockRule`, select unsuppressed `FAIL` findings by policy ID without filtering on `finding.blocking`.

- [ ] **Step 4: Make incomplete runner results terminal failures**

Persist the normalized report for diagnostics, set `status="failed"`, set a concise parse/discovery error, skip gate evaluation, commit, and return nonzero. Re-check cancellation immediately before final state mutation.

- [ ] **Step 5: Run focused and full gates, then commit**

Run: `mise exec -- uv run pytest tests/test_gates.py tests/test_platform.py tests/test_cli.py -x --tb=short`

Run: `mise run check && mise run test:coverage`

Commit: `fix: enforce complete scan and baseline semantics`

---

### Task 3: Durable Worker Retry, Timeout, Cancellation, And Retention

**Files:**
- Modify: `src/conformdag/platform/db.py`
- Modify: `src/conformdag/platform/worker.py`
- Modify: `src/conformdag/platform/runner.py`
- Modify: `src/conformdag/platform/app.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: Task 2's terminal-state invariant.
- Produces: `RunnerOutcome` dataclass with `error: str`, `retryable: bool`, and `cancelled: bool`; `execute_claimed_scan()` returns this value.
- Guarantees: every claimed scan exits running state durably; cancellation wins; newest artifact survives retention.

- [ ] **Step 1: Add failing worker state-machine tests**

```python
def test_exhausted_abandoned_scan_is_committed_failed(platform_env: str) -> None:
    seed_stale_running_scan(platform_env, attempts=3)
    assert run_worker_once(factory(platform_env), platform_env, settings(max_attempts=3)) is None
    assert only_scan(platform_env).status == "failed"


def test_retention_zero_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlatformSettings(dsn="sqlite:///x", retention_keep=0)
```

Add timeout-with-attempts-left requeue, timeout-at-budget terminal failure, cancellation-during-child execution, and runner-completion-after-cancel tests.

- [ ] **Step 2: Verify focused red failures**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "exhausted_abandoned or timeout_requeues or cancellation_terminates or retention_zero" -x --tb=short`

Expected: stale failure rolls back, timeout fails immediately, child remains alive, and zero retention is accepted.

- [ ] **Step 3: Replace blocking `subprocess.run` with cancellable `Popen` polling**

```python
@dataclass(frozen=True)
class RunnerOutcome:
    error: str = ""
    retryable: bool = False
    cancelled: bool = False
```

Poll with the existing timeout as the hard deadline. Between bounded waits, query the scan status using a fresh session; terminate then kill after a short grace period when cancelled. Relay stderr exactly as current logging does.

- [ ] **Step 4: Commit every state transition and protect newest retention**

Commit the exhausted stale failure before returning from `run_worker_once()`. Requeue retryable failures only while `attempts < max_attempts`; otherwise mark failed. Validate `retention_keep >= 1` in both `PlatformSettings` and `WorkerSettings.from_environment()`, and make `retention_target_scan_ids()` defensively protect one newest row.

- [ ] **Step 5: Run focused/full/runtime gates and commit**

Run: `mise exec -- uv run pytest tests/test_platform.py -x --tb=short`

Run: `mise run check && mise run test:coverage && mise run test:runtime`

Commit: `fix: make worker scan transitions durable`

---

### Task 4: Compose Workspace And Migration Startup

**Files:**
- Modify: `deploy/docker-compose.yml`
- Modify: `src/conformdag/platform/db.py`
- Modify: `src/conformdag/platform/runner.py`
- Modify: `src/conformdag/cli.py`
- Modify: `src/conformdag/platform/app.py`
- Modify: `docs/platform-deploy.md`
- Test: `tests/test_platform.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Produces: `initialize_session_factory(url: str) -> sessionmaker[Session]` runs migrations once at API/worker startup; `create_session_factory(url: str)` only binds an engine.
- Guarantees: runners never race migrations; API and worker see `/workspace`; configured startup workspace failures abort startup visibly.

- [ ] **Step 1: Add failing startup ownership tests**

```python
def test_runner_does_not_run_migrations(monkeypatch: MonkeyPatch, platform_env: str) -> None:
    monkeypatch.setattr("conformdag.platform.db.run_migrations", fail_if_called)
    execute_scan(seed_running_scan(platform_env), platform_env)


def test_invalid_configured_workspace_fails_app_startup(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        create_app(settings(tmp_path), workspace_path=tmp_path / "missing.yaml")
```

Add a compose-structure assertion that both API and worker mount `${CONFORMDAG_WORKSPACE_DIR}` at `/workspace`.

- [ ] **Step 2: Verify tests fail on current startup behavior**

Run: `mise exec -- uv run pytest tests/test_platform.py tests/test_runtime.py -k "runner_does_not_run_migrations or configured_workspace or compose_workspace" -x --tb=short`

- [ ] **Step 3: Separate migration initialization from factory creation**

```python
def create_session_factory(url: str) -> sessionmaker[Session]:
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def initialize_session_factory(url: str) -> sessionmaker[Session]:
    run_migrations(url)
    return create_session_factory(url)
```

Use initialization in `serve`, `worker`, `doctor`, and tests that create fresh databases. Use the pure factory in runner subprocesses. Do not use `Base.metadata.create_all()`.

- [ ] **Step 4: Fix Compose and startup failure behavior**

Mount the same workspace read/write in API and worker. Let explicitly configured workspace parsing/loading errors propagate instead of silently starting with no packs; document the startup contract.

- [ ] **Step 5: Run platform/runtime/full gates and commit**

Run: `mise exec -- uv run pytest tests/test_platform.py tests/test_runtime.py -x --tb=short`

Run: `mise run check && mise run test:coverage && mise run test:runtime`

Commit: `fix: serialize platform startup and workspace loading`

---

### Task 5: Lossless And Concurrent Policy Persistence

**Files:**
- Modify: `src/conformdag/platform/app.py`
- Modify: `src/conformdag/platform/packs.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Test: `tests/test_platform.py`
- Test: `frontend/src/App.test.tsx` if present, otherwise add API-shape coverage to the existing frontend test location.

**Interfaces:**
- Consumes: Task 1 authoritative pack validation.
- Produces: a typed `PolicyUpsertRequest` capable of creating a complete policy and updating an existing policy without losing source version, ownership, enforcement, scope, exceptions, invariant, or safe path.
- Guarantees: one `PackService` instance serializes pack mutations and each write uses a unique same-directory temporary file.

- [ ] **Step 1: Add failing round-trip and concurrency tests**

```python
def test_dashboard_policy_update_preserves_contract_metadata(client: TestClient, tmp_path: Path) -> None:
    before = load_registered_policy(client, "AIR-DET-001")
    save_dashboard_policy(client, before, title="Updated")
    after = load_registered_policy(client, "AIR-DET-001")
    assert after.source.version == before.source.version
    assert after.ownership == before.ownership
    assert after.invariant == before.invariant


def test_concurrent_policy_updates_do_not_lose_changes(pack_service: PackService) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(apply_distinct_update, ["AIR-DET-001", "AIR-DET-002"]))
    assert both_updates_are_present(pack_service)
```

Add invalid source-section rejection before write and unique temporary-file cleanup assertions.

- [ ] **Step 2: Verify focused red failures**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "preserves_contract_metadata or concurrent_policy_updates or invalid_source_section" -x --tb=short`

- [ ] **Step 3: Implement typed lossless merge and validation-before-write**

For existing policies, start from `existing.model_dump(mode="json")`, update only fields supplied by the request, preserve `source.version`, and validate the source section against source text before calculating its hash. For new policies, require complete ownership, scope, exceptions, enforcement, configuration, and source data in the API model.

- [ ] **Step 4: Serialize mutations and use unique atomic temp files**

Create a `threading.RLock` on each `PackService`; hold it across load-modify-validate-write for upsert/delete. Use `tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False)` followed by `os.replace()` and targeted cleanup.

- [ ] **Step 5: Align frontend types and payload construction**

Represent `invariant`, `source.version`, ownership, enforcement, scope, and exceptions explicitly in `frontend/src/api.ts`; do not derive invariant from `check_config`. Preserve unchanged fields in edit requests.

- [ ] **Step 6: Run backend/frontend/full gates and commit**

Run: `mise exec -- uv run pytest tests/test_platform.py -x --tb=short`

Run: `npm run build` in `frontend/`

Run: `mise run check && mise run test:coverage`

Commit: `fix: preserve policy contracts on concurrent saves`

---

### Task 6: Verified Auto-Fix Safety

**Files:**
- Modify: `src/conformdag/fixing/specs.py`
- Modify: `src/conformdag/fixing/codemods.py`
- Modify: `src/conformdag/fixing/engine.py`
- Test: `tests/test_fixing.py`
- Test: `tests/test_roundtrip.py`

**Interfaces:**
- Produces: `apply_spans()` rejects multiple distinct edits sharing any insertion/replacement coordinate; `_verify_patches()` verifies only when `ScanReport.complete is True`.
- Guarantees: malformed generated source and conflicting edits become residuals; `--apply` never writes them.

- [ ] **Step 1: Add failing unsafe-apply regressions**

```python
def test_apply_spans_rejects_distinct_zero_width_insertions_at_same_offset() -> None:
    spans = [EditSpan(1, 3, 1, 3, ', owner="a"'), EditSpan(1, 3, 1, 3, ', owner="b"')]
    with pytest.raises(ValueError, match="conflicting edit spans"):
        apply_spans("DAG()\n", spans)


def test_incomplete_verification_never_applies(tmp_path: Path) -> None:
    outcome = run_fix(repository_with_owner('bad"owner'), apply=True)
    assert outcome.applied_files == []
    assert outcome.residuals
    ast.parse((tmp_path / "dags/example.py").read_text())
```

- [ ] **Step 2: Verify tests fail by reproducing invalid Python writes**

Run: `mise exec -- uv run pytest tests/test_fixing.py -k "zero_width or incomplete_verification" -x --tb=short`

- [ ] **Step 3: Reject coordinate conflicts and quote literals safely**

Deduplicate only identical `EditSpan` values. Treat any remaining spans with equal `(start_line, start_col, end_line, end_col)` or overlapping ranges as conflicts. Render Python strings with `repr(value)`, never manual quote interpolation.

- [ ] **Step 4: Require complete verification**

When `_scan_patched_copy()` returns `complete=False`, verify no candidate file, create residuals with the scan issue message, and stop refinement. Before `_apply_verified()`, parse each verified Python content with `ast.parse()` as a defense-in-depth assertion.

- [ ] **Step 5: Run fix/roundtrip/full gates and commit**

Run: `mise exec -- uv run pytest tests/test_fixing.py tests/test_roundtrip.py -x --tb=short`

Run: `mise run check && mise run test:coverage`

Commit: `fix: prevent unsafe verified patches`

---

### Task 7: TaskFlow Identity, Resolution, And Fixability

**Files:**
- Modify: `src/conformdag/analysis.py`
- Modify: `src/conformdag/evaluator.py`
- Modify: `src/conformdag/fixing/codemods.py`
- Test: `tests/test_analysis.py`
- Test: `tests/test_check_pack.py`
- Test: `tests/test_fixing.py`

**Interfaces:**
- Produces: `TaskRecord.dag_line: int | None` links TaskFlow tasks to a concrete `DagRecord.line`; unresolved decorator arguments are omitted from `TaskRecord.values` and marked uncertain rather than stored as `None`.
- Guarantees: reused aliases cannot cross-contaminate defaults; dynamic values do not silently pass; advertised autofix kinds match supported AST forms.

- [ ] **Step 1: Add failing TaskFlow and start-date regressions**

```python
def test_reused_dag_alias_uses_nearest_concrete_dag_defaults() -> None:
    model = analyze_source(TWO_WITH_DAG_BLOCKS_REUSING_ALIAS)
    assert [effective_retries(model, task) for task in model.tasks] == [1, 5]


def test_unresolved_taskflow_retries_do_not_mask_dag_defaults() -> None:
    report = scan_source("@task(retries=RETRIES)\ndef work(): ...", dag_retries=5)
    assert retry_finding(report).status is FindingStatus.ERROR
```

Add missing `start_date` failure, dynamic `datetime(YEAR, 1, 1)` non-crash, and TaskFlow retry fixability tests.

- [ ] **Step 2: Verify focused red failures**

Run: `mise exec -- uv run pytest tests/test_analysis.py tests/test_check_pack.py tests/test_fixing.py -k "reused_dag_alias or unresolved_taskflow or missing_start_date or dynamic_datetime or taskflow_retry" -x --tb=short`

- [ ] **Step 3: Link tasks to concrete DAG records**

Track the current `DagRecord.line` on the with-context stack and store it on `TaskRecord.dag_line`. Resolve defaults by line first; retain `dag_name` only for reporting compatibility. Add the model field and regenerate schemas only if it belongs to a Pydantic public model; these analysis records are dataclasses and should not alter schemas.

- [ ] **Step 4: Preserve uncertainty and make evaluation total**

Only store decorator values when `_literal_value()` resolves them; track unresolved keyword names separately. Emit an ERROR/NEEDS_REVIEW finding instead of substituting zero/default values. Make start-date freshness fail missing dates and safely return uncertainty for nonliteral datetime components without raising `TypeError`.

- [ ] **Step 5: Implement TaskFlow retry codemods**

Extend retry-bounds target resolution to locate the `@task(...)` decorator on
the failing decorated function line. Replace an existing `retries=` keyword or
insert one in the decorator call using the same `SET_KWARG` payload semantics as
operator calls. The end-to-end test must prove the finding is classified
AUTOFIX, `generate_spans()` returns a span, and verify-by-rescan removes the
finding without changing the function body.

- [ ] **Step 6: Run analysis/fix/full gates and commit**

Run: `mise exec -- uv run pytest tests/test_analysis.py tests/test_check_pack.py tests/test_fixing.py -x --tb=short`

Run: `mise run check && mise run test:coverage`

Commit: `fix: resolve TaskFlow context and fixability safely`

---

### Task 8: P1 Remediation Acceptance

**Files:**
- Modify: `.superpowers/sdd/2026-09-16-p1-remediation/progress.md`
- Create: `.superpowers/sdd/2026-09-16-p1-remediation/acceptance-report.md`
- Test: all existing test and validation surfaces.

**Interfaces:**
- Consumes: Tasks 1-7 and the original readiness audit.
- Produces: requirement-to-evidence matrix and final Ready/Not Ready verdict.

- [ ] **Step 1: Re-run each original blocker reproduction**

Run the focused regression nodes added by Tasks 1-7 and record command/output in the acceptance report. Every Critical and Important item in `.superpowers/sdd/2026-09-05-p1-foundation/p1-readiness-audit.md` must map to a passing test or an explicit, spec-supported out-of-scope ruling.

- [ ] **Step 2: Run complete verification**

Run: `mise run check`

Run: `mise run test:coverage`

Run: `mise run schema --check`

Run: `mise run test:runtime`

Run: `npm run build` in `frontend/`

Expected: every command exits zero; coverage is at least 90%; no root `.coverage.cachyos*` artifacts remain after test processes finish.

- [ ] **Step 3: Run independent whole-branch review**

Generate a review package from the recorded remediation merge base to HEAD. Give the reviewer the remediation spec, this plan, both readiness audits, all task reports/reviews, and the complete diff. Fix all Critical/Important findings in one consolidated fix wave followed by one scoped re-review.

- [ ] **Step 4: Record final decision**

The acceptance report lists task commits, exact verification evidence, deferred Minor findings, every ruling and cost if wrong, and an explicit P1 readiness decision. Do not start P2, push, merge, publish, or delete recovery evidence.
