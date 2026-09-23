# C07 Effective Scan Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve scan settings once into `EffectiveScanConfiguration`, then make the CLI and platform pack seam consume that result without allowing the core scanner to replace an explicitly resolved Airflow profile.

**Architecture:** `application.configuration` owns source precedence and produces complete typed project, runtime, semantic, and policy-pack values. The CLI constructs adapters from those values and calls `application.scan.execute_scan()` with the configuration; the application passes its effective profile explicitly to `scan_repository()`. Core callers that omit the profile keep the legacy project-config fallback. C07 removes duplicate CLI config/pack selection and the platform runner's independent project-versus-repository pack choice. It retains `scan_repository()` project-config reads for discovery controls and repository-local suppressions. The platform runner's remaining orchestration and persisted platform profiles stay deferred to C10 and C08, respectively.

**Tech Stack:** Python 3.12, Pydantic v2, frozen dataclasses, Typer, pytest, Ruff, Pyright, `mise`, and `uv`.

**Spec:** `docs/superpowers/specs/2026-09-23-effective-scan-configuration-design.md`

## Global Constraints

- Apply precedence in this order: explicit invocation → platform repository override → project file → model defaults.
- `None` means that an override layer has no value; `False` is a supplied boolean that overrides `True` below it.
- Keep semantic API keys, GitHub tokens, platform admin tokens, and database DSNs out of both configuration value objects.
- The resolver does not read environment variables, import adapters, or open network connections.
- `execute_scan()` receives required `EffectiveScanConfiguration` and uses it as its only source of resolved scan settings.
- `runtime.enabled` controls the optional runtime phase; the effective Airflow profile is passed to core whether runtime is enabled or disabled.
- Preserve omitted-versus-explicit profile semantics: omitted direct calls use project-config fallback; C07 application calls explicitly pass a profile, including `None`.
- Keep `scan_repository()` project-config reads for discovery controls and repository-local suppressions; an explicit C07 pack/profile prevents those reads from making a second pack/profile precedence choice.
- An explicit CLI `--runtime-image` clears lower-precedence Airflow profiles for that invocation. This is an intentional C07 precedence correction, not a C06 parity assertion.
- Keep the persisted `RepositoryRow.airflow_profile` entirely unwired until C08; keep platform semantic/runtime phase execution and remaining orchestration in C10.
- Preserve CLI reports, fingerprints, renderers, output, and exit codes for every characterized case except the explicit `--runtime-image` precedence correction above.
- Do not change report, policy, project configuration, or platform database schemas; do not stage `.serena/`.
- Before any product-code edit, establish a complete clean `mise run check` on the approved C07 branch. Run the full gate again before every implementation commit and before publishing implementation evidence.

## Review Focus

- **Invocation precedence and selector clearing:** an invocation value must beat platform/project values, explicit `False` must survive, and `--runtime-image` must clear a lower Airflow profile. Pin this in resolver matrix tests and the named CLI regression in Task 3.
- **Core profile omission semantics:** omitted profile and explicitly supplied `None` must select different behavior. Pin both in core tests and the application explicit-`None` forwarding test in Task 2.
- **Path origin:** invocation-relative, project-relative, and workspace-resolved policy-pack paths must resolve to the intended absolute file. Pin invocation/project cases in Task 1 and platform reuse in Task 4.
- **Secrets and lazy adapters:** configuration resolution must not read or retain credentials, and semantic/runtime adapters must be constructed only for enabled phases. Pin the value-object boundary in Task 1 and adapter behavior in Task 3.
- **Platform boundary:** persisted Airflow profile and project semantic/runtime settings must not activate platform phases; the resolver-selected pack must feed both scan and gate loading. Pin this in Task 4 with a stored profile value and pack-path spies.

---

## File Map

| File | C07 responsibility |
| --- | --- |
| `src/conformdag/application/configuration.py` | New resolver, partial overrides, and effective configuration value objects. |
| `src/conformdag/application/__init__.py` | Re-export the public configuration types and resolver alongside the existing application API. |
| `src/conformdag/application/scan.py` | Require effective configuration and pass its pack, phase values, and explicit profile to core. |
| `src/conformdag/scan.py` | Distinguish omitted `airflow_profile` from explicitly supplied `None`. |
| `src/conformdag/cli.py` | Translate CLI options once, resolve configuration, construct adapters from it, call the application service, and retain presentation/exit mapping. |
| `src/conformdag/platform/runner.py` | Resolve the platform pack once and reuse it for core scan and gate pack loading; do not read the stored profile. |
| `tests/application/test_configuration.py` | Source precedence, special runtime selector mapping, path origin, defaults, and secret boundary. |
| `tests/application/test_scan.py` | Effective-configuration service contract, adapter gating, and explicit profile forwarding. |
| `tests/test_scan.py` | Legacy omission fallback and explicit-`None` core profile behavior. |
| `tests/test_cli.py` | CLI resolution/adapters, the intentional runtime-image correction, and C06 compatibility. |
| `tests/test_platform.py` | Platform pack reuse and proof that stored profile and project phase settings remain unwired. |

## Task 1: Establish the implementation baseline and add the resolver

**Files:**

- Create: `src/conformdag/application/configuration.py`
- Modify: `src/conformdag/application/__init__.py`
- Create: `tests/application/test_configuration.py`

**Interfaces:**

- Consumes: `load_project_config()`, `resolve_configured_policy_pack()`, `ProjectConfig`, `ProjectRuntimeConfig`, `ProjectSemanticConfig`, and `AirflowProfile`.
- Produces: frozen `ScanOverrides`, frozen `EffectiveScanConfiguration`, and `resolve_effective_configuration(repository_root, *, invocation_overrides, platform_overrides, invocation_working_directory)`.

The resolver signature is:

```python
def resolve_effective_configuration(
    repository_root: Path,
    *,
    invocation_overrides: ScanOverrides = ScanOverrides(),
    platform_overrides: ScanOverrides = ScanOverrides(),
    invocation_working_directory: Path | None = None,
) -> EffectiveScanConfiguration: ...
```

- [ ] **Step 1: Re-establish and record the complete baseline gate before editing product code.**

Run from the approved worktree:

```bash
mise run check
```

Expected: format check, lint, Pyright, the full non-runtime pytest suite, policy validation, and inventory all complete successfully. If the command fails, stalls, or cannot complete because of the environment, diagnose and rerun it until a complete result is available; do not begin product-code edits or describe an incomplete run as passing.

- [ ] **Step 2: Capture C06 CLI report and exit behavior before any product-code edit.**

Use the existing `CliRunner` fixtures in `tests/test_cli.py` to capture canonical reports and exit codes under `/tmp/c07-c06-before/` for deterministic, fake-semantic, fake-runtime-profile, repository-suppression, baseline, and gate scans. Fix provider/runtime responses and timestamps at the existing test seams so replayed reports are comparable. Keep all capture helpers and outputs outside the repository. Do not include the lower-project-profile plus `--runtime-image` case in this parity set; Task 3 pins it as the intentional C07 correction.

- [ ] **Step 3: Add resolver contract tests before adding the module.**

In `tests/application/test_configuration.py`, write tests for a no-config repository, project-file values, and a parameterized precedence matrix for `policy_pack`, `airflow_profile`, `runtime_image`, `semantic_enabled`, `semantic_base_url`, `semantic_model`, and `semantic_structured_output`. Include explicit `False` against project `True` and platform `True`, and assert each selected value comes from invocation, platform, project, and defaults in the corresponding case.

Use this shape for the layer assertions:

```python
result = resolve_effective_configuration(
    root,
    invocation_overrides=ScanOverrides(semantic_enabled=False),
    platform_overrides=ScanOverrides(semantic_enabled=True),
)

assert result.semantic.enabled is False
```

Add cases asserting conflicting invocation selectors raise `ValueError`, an invocation profile selector enables runtime and clears the lower image, an invocation image selector enables runtime and clears lower profiles, and a platform profile value alone does not enable runtime or clear the project image.

- [ ] **Step 4: Run the new resolver tests to observe the missing-module failure.**

Run: `mise exec -- uv run pytest tests/application/test_configuration.py -x --tb=short`

Expected: collection fails because `conformdag.application.configuration` has not been created. Keep the tests and continue with the implementation.

- [ ] **Step 5: Implement the typed resolver and export its public values.**

In `configuration.py`, define the exact design fields:

```python
@dataclass(frozen=True)
class ScanOverrides:
    policy_pack: Path | None = None
    airflow_profile: AirflowProfile | None = None
    runtime_image: str | None = None
    semantic_enabled: bool | None = None
    semantic_base_url: str | None = None
    semantic_model: str | None = None
    semantic_structured_output: bool | None = None


@dataclass(frozen=True)
class EffectiveScanConfiguration:
    project: ProjectConfig
    resolved_policy_pack: Path
    runtime: ProjectRuntimeConfig
    semantic: ProjectSemanticConfig
```

Load `root / "conformdag.yaml"` through `load_project_config()`. Resolve each ordinary override by first non-`None` value in invocation/platform/project/default order and build complete runtime/semantic models with `model_copy(update=...)`. For an invocation selector, set `runtime.enabled=True` and clear its sibling target; reject simultaneous profile and image selectors. A platform profile only supplies the profile field. Resolve an invocation-relative explicit pack with `from_cli=True` and `invocation_working_directory`; resolve project-relative and already workspace-resolved paths from `root`. Resolve bundled references through the existing policy helper. Keep resolver imports limited to application, config, models, and policy primitives.

Re-export `ScanOverrides`, `EffectiveScanConfiguration`, and `resolve_effective_configuration` in `application/__init__.py`. Do not add any key, token, DSN, environment, provider, or platform field.

- [ ] **Step 6: Pin path origins, defaults, and secret exclusion.**

Add resolver tests that select a relative CLI pack from a separate invocation directory, a project-relative pack from the repository root, an absolute workspace-resolved platform pack unchanged, and a bundled pack reference using existing helper behavior. Set a sentinel API key in the environment, resolve configuration, and assert neither dataclass field lists nor serialized values contain the sentinel or credential/DSN fields.

- [ ] **Step 7: Run the resolver and config-focused tests.**

Run: `mise exec -- uv run pytest tests/application/test_configuration.py tests/test_config.py -x --tb=short`

Expected: the full four-layer matrix, selector rules, path origins, defaults, and secret-boundary checks pass.

- [ ] **Step 8: Run the full repository gate and commit the resolver.**

Run: `mise run check`

Expected: every task in the repository check completes successfully. Then commit only the resolver, its export, and its tests with `feat: add effective scan configuration resolver`. Do not stage `.serena/`.

## Task 2: Make the application and core honor explicit effective profiles

**Files:**

- Modify: `src/conformdag/scan.py`
- Modify: `src/conformdag/application/scan.py`
- Modify: `src/conformdag/application/__init__.py`
- Modify: `tests/test_scan.py`
- Modify: `tests/application/test_scan.py`

**Interfaces:**

- Consumes: `EffectiveScanConfiguration`, the resolver from Task 1, the existing `RuntimeExecutor`, and `ScanOptions` repository context.
- Produces: `execute_scan(options: ScanOptions, configuration: EffectiveScanConfiguration, *, semantic_provider, semantic_provider_name, runtime_executor, baseline, operational_suppressions, parse_cache) -> ScanExecutionResult`; `ScanOptions` has only `repository_root`.

The post-C07 signature is:

```python
def execute_scan(
    options: ScanOptions,
    configuration: EffectiveScanConfiguration,
    *,
    semantic_provider: SemanticProvider | None = None,
    semantic_provider_name: str | None = None,
    runtime_executor: RuntimeExecutor | None = None,
    baseline: BaselineInput | None = None,
    operational_suppressions: Sequence[Suppression] = (),
    parse_cache: ParseCache | None = None,
) -> ScanExecutionResult: ...
```

- [ ] **Step 1: Add core tests for omitted and explicit profile arguments.**

In `tests/test_scan.py`, create a configured repository with `runtime.airflow_version: "3.3.0"` and spy on `ruff_rules_for_policies()` while returning an empty rule set. Assert an omitted `airflow_profile` selects the configured profile, while `airflow_profile=None` passes `None` to the rule selector. Keep the tests independent of Docker and the actual Ruff binary.

- [ ] **Step 2: Add application tests for the required configuration contract.**

Update `tests/application/test_scan.py` to construct `EffectiveScanConfiguration` and assert `execute_scan()` calls core once with `configuration.resolved_policy_pack` and `airflow_profile=configuration.runtime.airflow_version`, including when that value is `None` and runtime is disabled. Assert runtime preflight/execution uses `configuration.runtime` and `configuration.project.scan.include/exclude`; assert semantic model and structured-output values come from `configuration.semantic` when a provider is injected.

Add a test that enabled project runtime with no injected executor omits runtime execution, while an injected executor for a disabled runtime phase is rejected. Add the corresponding semantic adapter-gating cases. Preserve baseline, operational suppression, normalization, gate, and parse-cache coverage.

- [ ] **Step 3: Implement omitted-versus-explicit semantics in the core API.**

Use a private enum sentinel so the public parameter remains strictly typed:

```python
class _AirflowProfileUnset(Enum):
    TOKEN = 0


_AIRFLOW_PROFILE_UNSET = _AirflowProfileUnset.TOKEN
```

Set `scan_repository(..., airflow_profile: AirflowProfile | None | _AirflowProfileUnset = _AIRFLOW_PROFILE_UNSET, ...)`. Select the project fallback only when `isinstance(airflow_profile, _AirflowProfileUnset)`; otherwise use the supplied value exactly, including `None`. Keep policy-pack, discovery, suppressions, evaluation, and report behavior unchanged.

- [ ] **Step 4: Replace C06 application configuration inputs with the effective object.**

Change `ScanOptions` to:

```python
@dataclass(frozen=True)
class ScanOptions:
    repository_root: Path
```

Require `configuration` as the second positional argument to `execute_scan()`. Remove `semantic_model`, `semantic_native_structured_output`, and `runtime_config` from its keyword inputs. Load the gate pack from `configuration.resolved_policy_pack`, pass that same absolute path to `scan_repository()`, pass the explicit effective profile on every core call, and derive semantic/runtime phase data from `configuration.semantic` and `configuration.runtime`. Preserve the existing report normalization, suppression, baseline, gate, error, and adapter ordering rules. Do not invoke the resolver from inside `execute_scan()`.

- [ ] **Step 5: Run core and application contract tests.**

Run: `mise exec -- uv run pytest tests/test_scan.py tests/application/test_scan.py -x --tb=short`

Expected: omission keeps legacy project fallback; explicit `None` stays `None`; the application passes the effective profile on one core call and keeps phase adapters separate from configuration.

## Task 3: Move CLI scan composition to the resolver and pin the intentional correction

**Files:**

- Modify: `src/conformdag/cli.py:scan`
- Modify: `tests/test_cli.py`

**Interfaces:**

- Consumes: resolver, `ScanOverrides`, `EffectiveScanConfiguration`, the new `ScanOptions`, and the required-config `execute_scan()` from Tasks 1 and 2.
- Produces: a CLI scan adapter that resolves once, constructs provider/runtime adapters from effective values, calls the application once, and retains presentation/exit ownership.

- [ ] **Step 1: Add the profile-correction regression against the saved C06 oracle.**

Use the saved `/tmp/c07-c06-before/` cases from Task 1 for exact parity comparison. Add a test named `test_runtime_image_clears_project_profile_for_core_scan` with project `runtime.airflow_version: "3.3.0"`, a valid pinned custom image (`"ghcr.io/example/conformdag@sha256:" + "a" * 64`), a fake runtime result, and a core-call spy. Assert the effective profile is explicitly `None` at the core call. Document in the test that this is the intentional C07 precedence correction, not an exact C06 parity case.

- [ ] **Step 2: Add CLI resolver-call and adapter-source tests.**

Spy on `resolve_effective_configuration()` to assert `cli.scan` makes one call with named `invocation_overrides` and the current working directory for invocation-relative packs. Verify an explicit `--runtime` maps to `airflow_profile`, `--runtime-image` maps to `runtime_image`, empty semantic URL/model options remain omitted, and explicit `--semantic/--no-semantic` values preserve tri-state behavior. With semantic enabled, assert provider setup uses effective URL/model/structured-output and reads the API key only through the adapter boundary. With disabled semantic/runtime phases, assert provider/runtime adapters are not constructed.

- [ ] **Step 3: Run CLI tests before migrating the command.**

Run: `mise exec -- uv run pytest tests/test_cli.py -x --tb=short`

Expected: this is the red test run. The C06 CLI path fails at the new required-configuration boundary, and the resolver spy records no call. Existing checks that do not invoke the changed scan path continue to pass. Keep these failures as evidence that the migration tests reach the intended boundary.

- [ ] **Step 4: Replace the CLI merge with one resolution and adapter construction.**

For a normal scan, build `ScanOverrides` from invocation options and call `resolve_effective_configuration(root, invocation_overrides=..., invocation_working_directory=Path.cwd())` once. Use `effective.resolved_policy_pack`, `effective.semantic`, and `effective.runtime`. When semantic execution is enabled, require and validate `effective.semantic.base_url` and `effective.semantic.model`, read the configured API key through `semantic_api_key(effective.project)`, then construct the provider/cache with `effective.semantic.native_structured_output`, temperature, token limits, concurrency, and cache path. Construct `_CliRuntimeExecutor` only when effective runtime is enabled. Parse baseline input before service invocation. Call the application using this shape:

```python
execution = execute_scan(
    ScanOptions(repository_root=root),
    effective,
    semantic_provider=provider,
    semantic_provider_name=provider_name if effective.semantic.enabled else None,
    runtime_executor=runtime_executor,
    baseline=baseline_input,
)
```

Use the same resolved pack for preview mode and retain provider/runtime-free preview behavior. Keep format/destination checks, rendering, `--no-evidence` report-copy behavior, and existing exit precedence in `cli.scan`. Remove imports made unused by the migration.

- [ ] **Step 5: Run CLI, application, runtime, and report compatibility tests.**

Run: `mise exec -- uv run pytest tests/test_cli.py tests/application/test_scan.py tests/test_scan.py tests/test_runtime.py tests/test_gates.py tests/test_reporting.py -x --tb=short`

Expected: CLI delegation, error mapping, renderer output, runtime behavior, baseline/gate behavior, and the explicit profile correction pass.

- [ ] **Step 6: Compare C06 and C07 outputs and exits.**

Replay the same fixed scenarios used in Step 1 after the migration. Compare complete serialized reports and exit codes for deterministic, semantic, runtime-profile, repository-suppression, baseline, and gate cases. All characterized cases must match exactly except the dedicated `--runtime-image` plus project-profile scenario, which must show effective/core profile `None`. Do not weaken report comparisons by dropping findings, fingerprints, suppressions, gate values, or exit codes.

- [ ] **Step 7: Run `mise run check` and commit the CLI/application/core migration.**

Run the full repository gate, then commit only the CLI, application/core files, and their tests with `refactor: resolve scan configuration before execution`. Do not stage `.serena/`.

## Task 4: Route the platform pack seam through the resolver

**Files:**

- Modify: `src/conformdag/platform/runner.py`
- Modify: `tests/test_platform.py`

**Interfaces:**

- Consumes: `resolve_effective_configuration()`, `ScanOverrides`, and the Task 1 absolute `resolved_policy_pack`.
- Produces: the existing subprocess runner using one application-owned policy-pack choice for core scan and gate loading while leaving all other platform orchestration in place.

- [ ] **Step 1: Add a runner regression for pack reuse and platform profile isolation.**

Create a running scan whose repository has a configured `policy_pack` and a non-empty stored `airflow_profile`. Spy on the resolver input, `scan_repository()`, and `select_policy_pack()` used for gate loading. Assert the override carries the repository pack and leaves `airflow_profile=None`; the exact resolver-produced absolute pack reaches both core scan and gate loading; the core call omits `airflow_profile`; and no runtime executor or semantic provider is constructed. Use the existing SQLite `platform_env` fixture and fake complete report to keep the test independent of Docker.

- [ ] **Step 2: Run the platform regression before changing the runner.**

Run: `mise exec -- uv run pytest tests/test_platform.py::test_runner_uses_resolved_pack_without_wiring_stored_profile -x --tb=short`

Expected: the test fails because the current runner performs separate pack resolution for scan and gate.

- [ ] **Step 3: Resolve one platform configuration and reuse its pack path.**

Replace the runner's independent project/repository pack selection with:

```python
effective = resolve_effective_configuration(
    repository_root,
    platform_overrides=ScanOverrides(
        policy_pack=Path(repository.policy_pack) if repository.policy_pack is not None else None,
    ),
)
```

Pass `effective.resolved_policy_pack` to the existing `scan_repository()` call and use it for the later gate pack load. Keep the core `airflow_profile` argument omitted so the legacy direct-call fallback remains. Do not access `repository.airflow_profile`; do not move platform suppressions, normalization, baselines, gates, persistence, cancellation/fencing, DSN, or token behavior into the application.

- [ ] **Step 4: Run platform and workspace path tests.**

Run: `mise exec -- uv run pytest tests/test_platform.py -k 'runner or workspace' -x --tb=short`

Expected: the pack selected from the workspace/repository is used for both scan and gates; persisted profiles remain unused; runner lifecycle behavior remains intact.

- [ ] **Step 5: Run the full repository gate and commit the platform seam.**

Run: `mise run check`

Expected: complete success across every repository gate. Commit only the runner and platform tests with `refactor: resolve platform scan pack once`. Do not stage `.serena/`.

## Task 5: Final implementation evidence and compatibility review

**Files:**

- Verify: all Task 1–4 source and test files.

**Interfaces:**

- Consumes: all completed Task 1–4 behavior and the approved C07 design.
- Produces: complete repository gate output and C06/C07 compatibility evidence for implementation review.

- [ ] **Step 1: Run the complete gate after all implementation commits.**

Run: `mise run check`

Expected: format-check, lint, typecheck, full non-runtime suite, policy-pack validation, and dependency inventory all complete successfully. If any task hangs or fails, investigate and resolve it before recording implementation evidence.

- [ ] **Step 2: Review the final diff against the C07 design.**

Verify every design section maps to code and tests: four-layer precedence; CLI selector mapping; explicit-`False`; path origins; secrets boundary; exact post-C07 `execute_scan()` signature; effective profile regardless of runtime enablement; omitted-versus-explicit core profile semantics; `--runtime-image` precedence correction; no C07 platform profile wiring; platform phase behavior; and C08/C10 boundaries. Verify no schema, fingerprint, output, exit, or unrelated platform orchestration changes entered the diff.

- [ ] **Step 3: Publish only complete implementation evidence after approval of this plan and execution method.**

Record the full `mise run check` result, the compared CLI outputs/exit codes, and the dedicated runtime-image correction case. Do not describe any incomplete or stalled check as passing. Do not start this task until the implementation plan has been approved.

## Plan Self-Review

- **Spec coverage:** Tasks 1–4 cover resolver ownership and precedence, value-object separation, secrets, policy-pack path origins, CLI migration, explicit core profile forwarding, legacy fallback, platform pack reuse, and the C08/C10 boundaries. Task 5 requires a line-by-line final evidence review.
- **Placeholder scan:** No task uses TBD/TODO language or asks an implementer to infer unnamed behavior. Every code touch names its files, contract, focused command, and expected result.
- **Type consistency:** The resolver types are consumed by both CLI and platform. `execute_scan(options, configuration, ...)` consumes `ScanOptions(repository_root)` and no longer receives the removed C06 configuration keywords. The sentinel type remains private to `scan.py`; callers pass only `AirflowProfile | None` explicitly.
- **Review Focus coverage:** Invocation precedence and selector clearing are pinned in Task 1 and Task 3; core omission semantics in Task 2; path origins in Tasks 1 and 4; secrets/adapters in Tasks 1 and 3; platform isolation in Task 4.
- **Intentional non-parity:** Task 3 names the exact project-profile plus `--runtime-image` case, asserts the C07 effective/core value is `None`, and explicitly excludes only that case from exact C06 output/exit parity.
- **Gate status:** The earlier sandboxed pytest run stopped at the loopback-socket permission test and is not counted as passing. A subsequent full `mise run check` with local socket access passed: 607 passed, 2 skipped, 19 deselected; formatting, lint, Pyright, inventory, and both policy packs passed. Task 1 still reruns the complete gate immediately before the first product-code edit; every implementation commit and final implementation evidence requires a complete gate.
