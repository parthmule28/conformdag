# Application Scan Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one reusable application scan workflow and make the CLI delegate complete scan orchestration to it without changing report or CLI behavior.

**Architecture:** `application.scan.execute_scan()` composes one `scan_repository()` call with injected semantic/runtime dependencies, supplied operational suppressions, final application normalization, and gates for complete reports only. The CLI retains temporary composition needed for today's behavior and owns rendering/exit mapping; C07 replaces that composition and C10 migrates the platform runner.

**Tech Stack:** Python 3.12, frozen dataclasses, `typing.Protocol`, Pydantic v2 domain models, pytest, Typer CLI adapter, existing `mise`/`uv` toolchain.

**Spec:** `docs/superpowers/specs/2026-09-23-application-scan-design.md`

## Global Constraints

- Keep `ScanOptions` exactly to `repository_root`, `policy_pack`, and `airflow_profile`; pass phase-specific inputs separately as typed keyword arguments.
- After successful preflight, call `scan_repository()` exactly once; it remains the only core evaluation primitive and owns semantic evaluation and repository-local suppressions.
- Do not add reusable semantic/runtime configuration precedence or conflict resolution to C06; temporary CLI composition exists only for current behavior and C07 centralizes it.
- Run runtime only from a supplied enabled `ProjectRuntimeConfig` and an injected `RuntimeExecutor`; never construct Docker/runtime infrastructure in `application`.
- Apply only supplied operational suppressions in `application`; preserve existing local suppression provenance and do not report cross-layer matches as duplicate input entries.
- `execute_scan()` performs one final application-level `normalize_report()` after post-core mutations; retain the normalization already performed by `scan_repository()`.
- Evaluate gates only for complete final reports; embed the same non-`None` `GateResult` in both `ScanReport.gate_result` and `ScanExecutionResult.gate_result`.
- Keep `application` free of Typer, FastAPI, SQLAlchemy, MCP, Docker clients, transport binding, persistence, and exit-code behavior.
- Keep `src/conformdag/platform/runner.py` unchanged; C10 owns platform delegation.
- Preserve CLI output formats, report JSON, findings/fingerprints, offline defaults, baseline semantics, and exit precedence; `--no-evidence` is presentation-only.
- Do not change Pydantic schema models or schema files. Do not stage `.serena/`.
- Run `mise run check` before every implementation commit, as required by `AGENTS.md`.

## Review Focus

- **Core-call/semantic duplication:** a successful execution invokes the core once and semantic evaluation remains inside it; pin with a spy around the application import of `scan_repository()` and an injected provider.
- **Runtime preflight and incomplete core result:** invalid runtime preflight prevents core execution, while a valid runtime phase still runs after an incomplete core report; pin with a fake executor and call-order assertions.
- **Suppression source/provenance:** local provenance survives an active operational match, operational-list duplicates remain diagnosable, and expiry text does not claim a local suppression reopened; pin at reporting and application layers.
- **Baseline/gate completeness:** report and fingerprint baselines work, invalid incomplete baselines fail before scanning, and incomplete final reports never reach the gate evaluator; pin with gate spies.
- **CLI parity and transport ownership:** configured/explicit packs, semantic/runtime options, report renderers, evidence stripping, and exit codes stay stable while orchestration calls the service once; pin with existing CLI tests plus a delegation test.

---

## File Map

| File | Responsibility in C06 |
| --- | --- |
| `src/conformdag/application/__init__.py` | Public application API re-exports; no composition or side effects. |
| `src/conformdag/application/errors.py` | `ScanInputError` and `RuntimeExecutionError` application distinctions. |
| `src/conformdag/application/scan.py` | Typed options/results, `RuntimeExecutor`, preflight, core call, runtime/suppression phases, final normalization and gates. |
| `src/conformdag/reporting.py` | Narrowly preserve an already-suppressed finding's provenance when applying an operational suppression. |
| `src/conformdag/cli.py` | Temporary current-behavior composition, runtime adapter, service call, rendering and exit mapping. |
| `tests/application/test_scan.py` | Service contracts, phase ordering, inputs, outputs, and failure-mode tests. |
| `tests/test_reporting.py` | Direct suppression provenance and diagnostic regressions. |
| `tests/test_cli.py` | CLI delegation and output/exit compatibility. |
| `docs/consolidation/progress.md` | C06 review evidence after the implementation PR is ready. |

No task edits `src/conformdag/platform/runner.py` or changes product configuration precedence.

### Task 1: Add application contracts and the single-core scan path

**Files:**
- Create: `src/conformdag/application/__init__.py`
- Create: `src/conformdag/application/errors.py`
- Create: `src/conformdag/application/scan.py`
- Create: `tests/application/__init__.py`
- Create: `tests/application/test_scan.py`

**Interfaces:**
- Consumes: `scan.load_pack_for_scan()`, `scan.scan_repository()`, `SemanticProvider`, `AirflowProfile`, `ScanReport`, `GateResult`, `Suppression`, `ProjectRuntimeConfig`, and `ParseCache`.
- Produces: frozen `ScanOptions`, `BaselineInput`, and `ScanExecutionResult` with the exact spec fields; `RuntimeExecutor`; `execute_scan()` with the spec keyword inputs; `ScanInputError(ValueError)` and `RuntimeExecutionError(RuntimeError)`.

- [ ] **Step 1: Write contract and single-core-call tests.**

Use the existing `build_repository: Callable[[Path], Path]` fixture. Assert the options dataclass has no transport/config fields and spy on the application module's core import:

```python
def test_scan_options_has_only_the_c06_fields() -> None:
    assert [item.name for item in fields(ScanOptions)] == [
        "repository_root",
        "policy_pack",
        "airflow_profile",
    ]
    options = ScanOptions(Path("repo"))
    assert options.policy_pack is None
    assert options.airflow_profile is None
    assert ScanOptions.__dataclass_params__.frozen is True


def test_baseline_input_defaults_to_no_baseline() -> None:
    assert [item.name for item in fields(BaselineInput)] == ["report", "fingerprints"]
    baseline = BaselineInput()
    assert baseline.report is None
    assert baseline.fingerprints is None


def test_scan_execution_result_has_only_the_c06_fields() -> None:
    assert [item.name for item in fields(ScanExecutionResult)] == ["report", "gate_result"]
    assert ScanExecutionResult.__dataclass_params__.frozen is True


def test_execute_scan_calls_core_once_and_passes_semantic_inputs(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    calls: list[tuple[Path, Path | None, dict[str, object]]] = []

    def fake_scan(
        repository_root: Path,
        policy_pack: Path | None = None,
        **kwargs: object,
    ) -> ScanReport:
        calls.append((repository_root, policy_pack, kwargs))
        return _complete_report()

    monkeypatch.setattr("conformdag.application.scan.scan_repository", fake_scan)
    provider = _SemanticProvider()
    options = ScanOptions(root, airflow_profile=AirflowProfile.AIRFLOW_3_3_0)

    result = execute_scan(
        options,
        semantic_provider=provider,
        semantic_provider_name="test-provider",
        semantic_model="test-model",
        semantic_native_structured_output=True,
    )

    assert len(calls) == 1
    assert calls[0][0] == root.resolve()
    assert calls[0][2]["semantic_provider"] is provider
    assert calls[0][2]["airflow_profile"] is AirflowProfile.AIRFLOW_3_3_0
    assert result.report.complete is True
```

Define `_complete_report()` in this test module with a complete `ScanReport`, empty findings/issues, and valid `RunMetadata`; define `_SemanticProvider` with the same `evaluate_many()` contract used in `tests/test_scan.py`. Keep the tests independent of Docker and provider access.

Also add two integration cases that wrap the real core import with a call counter. With a fake provider returning `SemanticResponse` values, assert semantic findings and audit metadata come from the core result and the wrapper count is one. With a provider raising `SemanticProviderError`, assert the core result contains the existing structured semantic failure and the wrapper count is still one. This pins semantic success/failure to the single core path, rather than only checking that a provider argument was forwarded.

Add a preflight case with a provider but no model and assert `ScanInputError` is raised before the core spy is called.

- [ ] **Step 2: Run the test before adding the package.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py -x --tb=short`

Expected: collection fails because `conformdag.application` does not exist. Keep the test; do not weaken it to make the pre-implementation run pass.

- [ ] **Step 3: Add the public types, errors, and minimal service.**

In `application/scan.py`, define the dataclasses exactly as follows and use typed imports from core modules:

```python
@dataclass(frozen=True)
class ScanOptions:
    repository_root: Path
    policy_pack: Path | None = None
    airflow_profile: AirflowProfile | None = None


@dataclass(frozen=True)
class BaselineInput:
    report: ScanReport | None = None
    fingerprints: frozenset[str] | None = None


@dataclass(frozen=True)
class ScanExecutionResult:
    report: ScanReport
    gate_result: GateResult | None
```

Add the typed `RuntimeExecutor.validate(root, config, include, exclude) -> None` and `RuntimeExecutor.execute(root, config, policy_ids, include, exclude) -> tuple[list[RuntimeObservation], str]` protocol from the spec. Define the fully annotated `execute_scan()` signature exactly as it appears in the spec, including `Sequence[Suppression]` and `ParseCache | None`. Resolve `root`, load `(config, pack)` via `load_pack_for_scan(root, options.policy_pack)`, reject an incomplete baseline and simultaneous baseline report/fingerprints before core execution, and reject a supplied semantic provider without a model using `ScanInputError`. Call `scan_repository()` exactly once with `root`, `options.policy_pack`, the four semantic inputs, `options.airflow_profile` unchanged, and `parse_cache`; return the report and `None` gate result at this foundation stage. Do not add semantic enablement or configuration precedence.

In `application/errors.py`, define only:

```python
class ScanInputError(ValueError):
    """Raised when an application scan input or preflight is invalid."""


class RuntimeExecutionError(RuntimeError):
    """Raised by a runtime adapter when runtime execution cannot complete."""
```

Re-export the public options, result, protocol, service, and errors from `application/__init__.py`; importing the package must not initialize adapters or execute a scan.

- [ ] **Step 4: Run the application contract tests.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py -x --tb=short`

Expected: the exact-field, baseline-default, and one-core-call tests pass; semantic arguments are forwarded to that call without an application-side semantic phase.

- [ ] **Step 5: Commit the independently tested application foundation.**

Run `mise run check` before committing.

```bash
git add src/conformdag/application tests/application
git commit -m "feat: add application scan contracts"
```

### Task 2: Preserve suppression provenance in the reporting helper

**Files:**
- Modify: `src/conformdag/reporting.py:apply_suppressions`
- Modify: `tests/test_reporting.py`

**Interfaces:**
- Consumes: existing `Finding.suppressed`, `Finding.suppression`, and the supplied `Suppression` sequence.
- Produces: an idempotent provenance rule: a matching active operational suppression does not replace the provenance of a finding already suppressed by core; diagnostics continue to describe duplicate/unmatched/expired entries in the supplied list.

- [ ] **Step 1: Add the failing local-plus-operational provenance test.**

Use `_finding()` and `_suppression()` in `tests/test_reporting.py`. Create distinct active local and operational suppressions with the same policy/fingerprint, attach the local one to a copied finding, and assert:

```python
current = datetime(2026, 7, 30, tzinfo=UTC)
finding = _finding()
local = _suppression(finding.fingerprint, current + timedelta(days=1)).model_copy(
    update={"reason": "repository-local waiver"}
)
operational = _suppression(finding.fingerprint, current + timedelta(days=2))
suppressed = finding.model_copy(update={"suppressed": True, "suppression": local})
result, issues = apply_suppressions([suppressed], [operational], current)

assert result[0].suppressed is True
assert result[0].suppression is local
assert issues == []
```

Add cases proving a duplicate within the supplied operational list still emits `SUPPRESSION_DUPLICATE`, while one local-plus-operational match does not, and an expired operational match leaves local provenance intact while its diagnostic does not claim the finding was reopened.

- [ ] **Step 2: Run the new reporting cases and confirm the provenance failure.**

Run: `mise exec -- uv run pytest tests/test_reporting.py -k 'provenance or already_suppressed' -x --tb=short`

Expected: the active operational match fails because the helper currently replaces `finding.suppression`.

- [ ] **Step 3: Keep existing findings unchanged and skip replacement for already-suppressed matches.**

In the helper's active-suppression branch, update only matching findings whose `suppressed` flag is false. Continue iterating every supplied entry so duplicate/unmatched/expired diagnostics are preserved. For an expired entry whose matching findings are all already suppressed, retain the `SUPPRESSION_EXPIRED` code but use accurate wording that does not say a finding was reopened; preserve the existing expired message for an unsuppressed match. Do not turn a cross-layer identity match into a duplicate input entry.

The active branch should have this shape:

```python
for position in candidate_indexes:
    finding = result[position]
    if not finding.suppressed:
        result[position] = finding.model_copy(update={"suppressed": True, "suppression": suppression})
```

- [ ] **Step 4: Run reporting and core scan regressions.**

Run: `mise exec -- uv run pytest tests/test_reporting.py tests/test_scan.py -x --tb=short`

Expected: provenance, expiration, local suppression, finding, and scan behavior pass.

- [ ] **Step 5: Commit the reporting seam.**

Run `mise run check` before committing.

```bash
git add src/conformdag/reporting.py tests/test_reporting.py
git commit -m "fix: preserve suppression provenance"
```

### Task 3: Compose the injected runtime phase

**Files:**
- Modify: `src/conformdag/application/scan.py`
- Modify: `tests/application/test_scan.py`

**Interfaces:**
- Consumes: `RuntimeExecutor`, supplied `ProjectRuntimeConfig`, core report policy IDs, and project scan include/exclude globs.
- Produces: pre-scan runtime validation; post-core execution, observations, digest, metadata, and the specified structured runtime failures.

- [ ] **Step 1: Add fake-executor tests for phase order and runtime outcomes.**

Create a typed fake executor whose `validate()` and `execute()` append to an event list. Test that an enabled config yields `validate → core → execute`; the execution receives the same config, configured globs, and sorted unique evaluated/skipped policy IDs. Return deliberately unsorted observations and assert the final report uses the existing stable order. Cover a `PASS` observation/digest, a nonfatal `FAIL` observation, an `ERROR` observation that makes the report incomplete with fatal `RUNTIME_OBSERVATION_ERROR`, and `RuntimeExecutionError` becoming fatal `RUNTIME_EXECUTION_ERROR` with an incomplete report. Also assert runtime still executes when the core report is already incomplete, an enabled config without an executor fails before the core call, and a validation `ScanInputError` fails before the core call.

- [ ] **Step 2: Run the runtime application tests and verify they fail before implementation.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py -k runtime -x --tb=short`

Expected: runtime events are missing; no test invokes Docker or the real runtime adapter.

- [ ] **Step 3: Execute only the supplied runtime config through the injected protocol.**

When `runtime_config is None` or `runtime_config.enabled` is false, skip runtime. For an enabled supplied config, require `runtime_executor`, call `validate()` before `scan_repository()`, and call `execute()` after the one core result even when that report is incomplete. Pass the project config's include/exclude lists and `sorted(set(report.policies_evaluated + report.policies_skipped))`. Sort observations by the same stable key as `runtime.normalize_runtime_observations()`—`(policy_id, status.value, message or "")`—without importing the runtime adapter module into `application`; append fatal runtime-observation issues for `FindingStatus.ERROR`; update `run.runtime_profile`, `run.runtime_image_digest`, and the existing `resolved_configuration["runtime"]` fields (`enabled`, `airflow_profile`, `supported_profile`, `network_enabled`, and `timeout_seconds`). Catch only `RuntimeExecutionError` from execution, add a fatal `RUNTIME_EXECUTION_ERROR`, and mark the report incomplete; likewise mark it incomplete when an `ERROR` observation produces a fatal `RUNTIME_OBSERVATION_ERROR`. Let unrelated failures propagate.

Keep runtime invocation behind the protocol and do not instantiate an executor in application code:

```python
if runtime_config is not None and runtime_config.enabled:
    if runtime_executor is None:
        raise ScanInputError("enabled runtime requires a RuntimeExecutor")
    runtime_executor.validate(root, runtime_config, config.scan.include, config.scan.exclude)
    observations, image_digest = runtime_executor.execute(
        root,
        runtime_config,
        sorted(set(report.policies_evaluated + report.policies_skipped)),
        config.scan.include,
        config.scan.exclude,
    )
```

- [ ] **Step 4: Run runtime and application tests.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py tests/test_runtime.py -x --tb=short`

Expected: fake application executors and existing runtime adapter tests pass without requiring Docker for the application tests.

- [ ] **Step 5: Commit runtime composition.**

Run `mise run check` before committing.

```bash
git add src/conformdag/application/scan.py tests/application/test_scan.py
git commit -m "feat: compose injected scan runtime"
```

### Task 4: Apply operational suppressions and recover only waived evaluation incompleteness

**Files:**
- Modify: `src/conformdag/application/scan.py`
- Modify: `tests/application/test_scan.py`

**Interfaces:**
- Consumes: `Sequence[Suppression]` as an explicit `execute_scan()` keyword and `reporting.apply_suppressions()`.
- Produces: operational suppression diagnostics and narrowly recomputed completeness without moving repository-local suppression out of core.

- [ ] **Step 1: Add application tests for provenance and error waiver boundaries.**

Patch the application import of `scan_repository()` to return a core report that already contains a locally suppressed finding with a concrete `Suppression` object. Supply an active operational suppression for the same identity and assert the resulting finding remains suppressed, retains the identical local suppression object, and has no cross-layer duplicate diagnostic. Add an unresolved `ERROR` finding with its fatal `EVALUATION_ERROR`; after an active operational match, assert only that fatal evaluation issue is removed and completeness is recomputed. Add a companion case with an unrelated fatal parse/runtime issue and assert the report remains incomplete. With no operational suppressions, assert core suppression/completeness state is left unchanged.

- [ ] **Step 2: Run the focused application suppression tests.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py -k suppression -x --tb=short`

Expected: the current service does not yet apply the explicit operational inputs.

- [ ] **Step 3: Apply supplied suppressions after runtime and preserve unrelated fatal issues.**

When the operational sequence is non-empty, snapshot whether the core report has unsuppressed `ERROR` findings, call `apply_suppressions()` on its findings with the supplied items, and append the returned diagnostics. If all such errors are now suppressed, remove only fatal `EVALUATION_ERROR` issues generated for those unresolved findings and recompute `complete` from the remaining fatal issues. Never remove parse, provider, or runtime issues. If no operational inputs were supplied, do not call the helper or alter core suppression state.

Use the before/after unresolved-error sets to keep recovery narrow:

```python
had_unresolved_errors = any(
    finding.status is FindingStatus.ERROR and not finding.suppressed
    for finding in report.findings
)
findings, suppression_issues = apply_suppressions(report.findings, list(operational_suppressions))
remaining_errors = [
    finding for finding in findings
    if finding.status is FindingStatus.ERROR and not finding.suppressed
]
issues = list(report.issues)
complete = report.complete
if had_unresolved_errors and not remaining_errors:
    issues = [
        issue
        for issue in issues
        if not (
            issue.code == "EVALUATION_ERROR"
            and issue.phase == "evaluation"
            and issue.fatal
        )
    ]
    complete = not any(issue.fatal for issue in issues)
report = report.model_copy(
    update={
        "findings": findings,
        "issues": [*issues, *suppression_issues],
        "complete": complete,
    }
)
```

- [ ] **Step 4: Run service, reporting, and platform characterization tests.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py tests/test_reporting.py tests/test_platform.py -x --tb=short`

Expected: application provenance/recovery cases and existing C06-unmodified platform runner suppression behavior pass.

- [ ] **Step 5: Commit operational suppression behavior.**

Run `mise run check` before committing.

```bash
git add src/conformdag/application/scan.py tests/application/test_scan.py
git commit -m "feat: apply operational scan suppressions"
```

### Task 5: Add final normalization, baseline evaluation, and complete-only gates

**Files:**
- Modify: `src/conformdag/application/scan.py`
- Modify: `tests/application/test_scan.py`

**Interfaces:**
- Consumes: the loaded `PolicyPack`, `BaselineInput`, final mutated report, `normalize_report()`, and `evaluate_pack_gates()`.
- Produces: one final application normalization, complete-only gates, and matching embedded/direct gate results.

- [ ] **Step 1: Add normalization and gate-order tests.**

Spy on the application module's `normalize_report()` and `evaluate_pack_gates()` references, delegating normalization to the real function. Assert the final application normalizer is called once after runtime/suppression changes both when runtime is disabled and enabled. Assert the gate spy sees the normalized report and the supplied baseline report or fingerprint set. Return a `GateResult` from the spy and assert `result.gate_result is result.report.gate_result`. For an incomplete report, assert the gate spy is never called and both gate-result fields are `None`. For a pack with no quality gates, assert the direct and embedded results stay `None`.

- [ ] **Step 2: Add baseline validation and both supported baseline-shape tests.**

Test a complete `BaselineInput(report=...)` and a `BaselineInput(fingerprints=frozenset(...))`; verify the correct form reaches `evaluate_pack_gates()`. Test that an incomplete baseline and a baseline containing both forms raise `ScanInputError` before the core spy is called.

- [ ] **Step 3: Run the gate/baseline tests to confirm missing behavior.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py -k 'baseline or gate or normalize' -x --tb=short`

Expected: final normalization/gate assertions fail until the service performs these steps.

- [ ] **Step 4: Normalize once at the application layer, then gate complete reports only.**

After runtime and operational suppressions, call application `normalize_report(report)` once. If and only if the normalized report is complete, call `evaluate_pack_gates()` with the loaded pack, normalized report, optional baseline report, and `set(baseline.fingerprints)` when fingerprints were supplied. For a non-`None` result, use one `GateResult` object in both the copied report and `ScanExecutionResult`; otherwise return `None` in both. Preserve core normalization inside `scan_repository()` and do not alter gate/fingerprint algorithms.

Keep the final call order explicit:

```python
final_report = normalize_report(report)
gate_result = None
if final_report.complete:
    gate_result = evaluate_pack_gates(
        pack,
        final_report,
        baseline.report if baseline is not None else None,
        baseline_fingerprints=(
            set(baseline.fingerprints)
            if baseline is not None and baseline.fingerprints is not None
            else None
        ),
    )
if gate_result is not None:
    final_report = final_report.model_copy(update={"gate_result": gate_result})
return ScanExecutionResult(report=final_report, gate_result=gate_result)
```

- [ ] **Step 5: Run the complete application/gate/reporting focus.**

Run: `mise exec -- uv run pytest tests/application/test_scan.py tests/test_gates.py tests/test_reporting.py tests/test_scan.py -x --tb=short`

Expected: application call order, baseline variants, complete-only gate behavior, and existing core report contracts pass.

- [ ] **Step 6: Commit baseline, normalization, and gate ownership.**

Run `mise run check` before committing.

```bash
git add src/conformdag/application/scan.py tests/application/test_scan.py
git commit -m "feat: evaluate scan baselines and gates"
```

### Task 6: Make `cli.scan` a composition and presentation adapter

**Files:**
- Modify: `src/conformdag/cli.py:scan`
- Modify: `tests/test_cli.py`
- Retain unchanged: `src/conformdag/platform/runner.py`

**Interfaces:**
- Consumes: `ScanOptions`, `BaselineInput`, `ScanExecutionResult`, `execute_scan()`, the `RuntimeExecutor` protocol, and application errors.
- Produces: CLI-local semantic/runtime composition and adapters; one service call; existing presentation and exit behavior.

- [ ] **Step 1: Add a service-delegation test and preserve CLI baseline cases.**

Before changing orchestration, add the delegation test and retain the existing tests for preview, semantic validation, mutually exclusive runtime flags, baseline parse/incompleteness, pack resolution, renderers, no-evidence, and gate/legacy exit codes as the compatibility oracle. The delegation test monkeypatches `conformdag.cli.execute_scan` with `raising=False`, using a typed stub that records inputs and returns a valid `ScanExecutionResult`; assert one service call with `ScanOptions`, `BaselineInput`, semantic inputs or `None`, and a runtime adapter/config only when current CLI/project configuration enables runtime. Before the migration, the test must reach its assertion with zero calls, not fail during monkeypatch setup. Add a presentation regression asserting `--no-evidence` strips evidence from rendered output without mutating the service report or its result fingerprint.

- [ ] **Step 2: Run the CLI characterization suite before changing orchestration.**

Run: `mise exec -- uv run pytest tests/test_cli.py -x --tb=short`

Expected: existing characterization tests pass and the new delegation assertion fails because the service stub receives zero calls.

- [ ] **Step 3: Add the CLI runtime adapter and map current inputs to application types.**

Implement a private CLI adapter satisfying `RuntimeExecutor`. Its `validate()` calls `build_runtime_manifest(root, config, [], include, exclude)` and translates `RuntimePhaseError` to `ScanInputError`; its `execute()` calls `execute_runtime(...)` and translates `RuntimePhaseError` to `RuntimeExecutionError`. Keep URL validation, API-key lookup, semantic provider/cache construction, and current CLI/project option composition in the CLI. Pass the constructed provider (or `None`) and its model/provider/structured-output metadata separately. Pass the constructed enabled runtime config with the adapter; set `ScanOptions.airflow_profile` to its profile only when runtime is enabled, matching the current `scan_repository()` call. Do not add `semantic_enabled` or reusable precedence logic.

Implement the typed adapter methods with this behavior:

```python
class _CliRuntimeExecutor:
    def validate(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        include: list[str],
        exclude: list[str],
    ) -> None:
        try:
            build_runtime_manifest(root, config, [], include, exclude)
        except RuntimePhaseError as exc:
            raise ScanInputError(str(exc)) from exc

    def execute(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        policy_ids: list[str],
        include: list[str],
        exclude: list[str],
    ) -> tuple[list[RuntimeObservation], str]:
        try:
            return execute_runtime(root, config, policy_ids, include, exclude)
        except RuntimePhaseError as exc:
            raise RuntimeExecutionError(str(exc)) from exc
```

- [ ] **Step 4: Parse baseline JSON before calling the service and delegate the full workflow.**

Convert valid baseline JSON to `BaselineInput(report=...)` before `execute_scan()` so incomplete baselines fail before the core call. Replace inline `scan_repository`, `execute_runtime`, runtime report mutation, normalization, and `evaluate_pack_gates` calls with one `execute_scan()` invocation. Use `execution.report` and `execution.gate_result` for the existing renderer and exit mapper. Keep format/destination validation, preview, evidence-stripping on a report copy, terminal progress, rendering, and the exact fatal/gate/blocking/runtime exit precedence in `cli.scan`. Remove only imports made unused by the move.

- [ ] **Step 5: Run CLI tests and focused scan/application integrations.**

Run: `mise exec -- uv run pytest tests/test_cli.py tests/application/test_scan.py tests/test_scan.py tests/test_runtime.py tests/test_gates.py tests/test_reporting.py -x --tb=short`

Expected: delegation, output formats, semantic/runtime errors, baseline/gate behavior, and legacy exits pass. The runtime CLI tests continue to patch the runtime adapter functions at their CLI-owned seam.

- [ ] **Step 6: Verify C10 and package boundaries remain untouched.**

Run: `git diff -- src/conformdag/platform/runner.py` and inspect `src/conformdag/application/` imports.

Expected: the runner has no diff; application imports no CLI, FastAPI, SQLAlchemy, MCP, Docker, or provider-construction adapter.

- [ ] **Step 7: Commit CLI delegation.**

Run `mise run check` before committing.

```bash
git add src/conformdag/cli.py tests/test_cli.py
git commit -m "refactor: delegate CLI scans to application"
```

### Task 7: Verify report parity, update the ledger, and prepare C06 review

**Files:**
- Modify: `docs/consolidation/progress.md`
- Verify: application, CLI, core scan, runtime, gates, reporting, fixing, and package-boundary tests.

**Interfaces:**
- Consumes: completed `execute_scan()` and the existing CLI's canonical report and exit contract.
- Produces: high-risk parity evidence, full quality-gate evidence, a pushed implementation branch/PR, and a factual C06 `review` ledger row; no merge.

- [ ] **Step 1: Compare pre-change CLI report behavior with application results.**

Before the CLI migration, use `CliRunner().invoke(app, ["scan", ...])` and the builders in `tests/test_cli.py` to capture canonical JSON for deterministic, fake-semantic, fake-runtime, repository-suppression, baseline, and gated repositories under `/tmp/conformdag-c06-before/`. Patch the existing CLI provider/runtime seams for semantic/runtime cases. After migration, run the same harness into `/tmp/conformdag-c06-after/`, also call `execute_scan()` for the same inputs, and diff the JSON after excluding only `run.timestamp` or other invocation metadata proven volatile. Confirm stable finding order/identity, report and finding fingerprints, runtime metadata, suppression provenance, `gate_result`, and exit precedence. Record exact commands and results for the ledger; investigate any difference rather than broadening the exclusion set. Keep the temporary harness and captures out of the product diff.

- [ ] **Step 2: Run focused suites, full checks, coverage, schema, and whitespace gates.**

Run:

```bash
mise exec -- uv run pytest tests/application/test_scan.py tests/test_cli.py tests/test_scan.py tests/test_runtime.py tests/test_gates.py tests/test_reporting.py tests/test_fixing.py tests/test_roundtrip.py -x --tb=short
mise run check
mise run test:coverage
mise run schema --check
git diff --check
```

Expected: focused and full tests pass, the 90% coverage threshold is met, strict Pyright and Ruff pass, policy packs/inventory validate, schemas are synchronized, and the default suite includes the autofix round-trip population.

- [ ] **Step 3: Request independent high-risk review of the whole implementation diff.**

Give the reviewer the approved spec, base/head SHAs, and report parity evidence. Ask them to trace single-core-call semantics, suppression provenance/completeness recovery, complete-only gates, CLI parity, forbidden application dependencies, and the unchanged C10 runner. Resolve verified Critical/Important findings and record any deferred Minor observations.

- [ ] **Step 4: Commit and publish the implementation for review without merging.**

Run `mise run check` before committing. After all checks pass, stage only C06 source and tests; keep `.serena/` unstaged. Commit with `feat: add application scan workflow`, push the branch, verify the remote SHA and CI, and open the implementation PR targeting `main`. Do not merge it.

- [ ] **Step 5: Record the real PR and verification evidence in the ledger.**

After the implementation PR exists, change C06 from `planned` to `review`; add the pushed branch, actual PR link, implementation commit SHA, focused/full/coverage/schema results, independent-review outcome, and compatibility notes. Run `mise run check` before committing, stage only `docs/consolidation/progress.md`, commit with `docs: record C06 application scan review evidence`, push, and verify the remote head. Do not mark C06 accepted before human merge authority and merge evidence.
