# C07 — Effective Scan Configuration Design

**Status:** Design proposal for external review. No implementation is authorized
until this design and the later implementation plan are approved.

## Intent

Give CLI, platform, and future MCP scan composition one typed owner for
resolving scan configuration. The resolver will apply the same precedence at
every adapter:

```text
explicit invocation → platform repository override → project file → model defaults
```

C07 replaces the temporary CLI merge introduced in C06 and provides a typed
platform seam. It preserves C06 scan behavior and report contracts, keeps
credentials outside effective configuration, and carries the persisted
platform Airflow profile as a typed resolver input without wiring that value
into C07 platform scans. The project profile remains part of effective scan
configuration regardless of runtime execution being enabled. C08 makes the
persisted platform profile effective; C10 moves the platform runner's remaining
scan orchestration into the application workflow.

## Current behavior and ownership

C06 made `application.scan.execute_scan()` the reusable complete scan workflow,
but deliberately left configuration composition in the CLI until C07. Today,
`cli.scan` loads the project config and selected pack, overlays semantic and
runtime CLI values, reads the semantic key from the environment, constructs
providers and a runtime executor, then passes those phase inputs to
`execute_scan()`. The application loads project configuration and the pack
again for scan globs and gates. `scan_repository()` loads the project config
again for scan scope and repository-local suppressions.

The platform runner has a separate path: it passes the repository's optional
policy-pack path directly to `scan_repository()`, then independently chooses
the repository pack or `conformdag.yaml` pack and reloads it for gate
evaluation. The workspace and repository API models also carry
`airflow_profile` as an optional string, but the runner does not use it.
Platform DSN and admin-token values are resolved by `PlatformSettings` and the
worker boundary; they are not scan configuration.

These paths have different responsibilities. Project YAML parsing and model
defaults stay in `conformdag.config` and `conformdag.models`. Selection among
configuration sources belongs to the application. Adapters continue to own
provider, runtime, filesystem, transport, and persistence construction.

## Decision: resolver ownership and inputs

`src/conformdag/application/configuration.py` will own
`resolve_effective_configuration()`, `ScanOverrides`, and
`EffectiveScanConfiguration`. It will read and validate
`<repository_root>/conformdag.yaml` through `load_project_config()` and apply
source precedence. It will not import CLI, platform, HTTP, database, Docker,
or provider adapters; read environment variables; or open network connections.

The resolver accepts two explicitly named override layers so callers cannot
accidentally swap their precedence:

```python
resolve_effective_configuration(
    repository_root: Path,
    *,
    invocation_overrides: ScanOverrides = ScanOverrides(),
    platform_overrides: ScanOverrides = ScanOverrides(),
    invocation_working_directory: Path | None = None,
) -> EffectiveScanConfiguration
```

`invocation_working_directory` exists to preserve the CLI's current resolution
of an explicitly supplied relative policy-pack path against the invoking
directory. Platform workspace loading already resolves repository and pack
paths against the workspace file; the runner will pass that resolved path.
Project-file relative paths continue to resolve from the repository root.
Bundled pack references keep the behavior of the existing policy-pack helper.

`ScanOverrides` is a partial value object used at either adapter boundary:

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
```

`None` means that layer has no value for that field. `False` is a supplied
boolean and overrides `True` below it. The current CLI treats empty semantic
URL and model options as omitted through its existing truthy fallback; the
adapter must preserve that mapping when constructing `ScanOverrides`.
Clearing a configured optional URL, model, profile, or image is not a general
C07 operation. The CLI runtime-selector mapping below is the specific
exception: it clears the sibling runtime target for that invocation.

The complete result is:

```python
@dataclass(frozen=True)
class EffectiveScanConfiguration:
    project: ProjectConfig
    resolved_policy_pack: Path
    runtime: ProjectRuntimeConfig
    semantic: ProjectSemanticConfig
```

`project` is the validated project-file value with model defaults applied; it
is retained for project-owned scan controls such as include/exclude globs,
symlink behavior, and local suppression path. `runtime` and `semantic` are the
complete values after all override layers have been applied. Consumers must
use these effective phase fields instead of re-reading corresponding values
from `project.runtime` or `project.semantic`. `resolved_policy_pack` is the
selected absolute pack path, resolved once by the application resolver.

## Decision: precedence and runtime selectors

For policy pack, profile, runtime image, semantic enabled, semantic URL, model,
and structured-output support, the resolver considers values in this order:

1. Explicit invocation override.
2. Platform repository override.
3. Project-file value.
4. The relevant Pydantic model default.

The project file is loaded as a typed `ProjectConfig`; an absent file therefore
uses the existing defaults. The resolver applies field values to typed
`ProjectRuntimeConfig` and `ProjectSemanticConfig` results. It does not let a
lower-precedence value replace a higher-precedence one, and it rejects
conflicting explicit runtime selectors rather than silently choosing one.

The CLI's existing `--runtime` and `--runtime-image` flags are mutually
exclusive selectors, not independent requests to preserve both project
selector fields. When either is explicitly supplied, runtime is enabled and
the selected target is set while the sibling target is cleared for that
invocation. In particular, `--runtime-image` explicitly clears the effective
Airflow profile from lower-precedence layers for that invocation, even if the
project file has one; this is part of the selector mapping, not a general
`None`-means-clear rule for `ScanOverrides`. With neither selector, the
project's `runtime.enabled`, image, and profile values are retained. The
effective profile is used for core static evaluation whether or not runtime
execution is enabled; `runtime.enabled` controls only the optional Docker
runtime phase.
This special invocation rule does not apply to the platform repository's
`airflow_profile`: that field supplies a profile value only; it does not enable
runtime execution or clear a project runtime image.

Semantic enablement is tri-state at the invocation layer. Omission inherits
platform, project, then model default; explicit `False` disables semantic
execution even if a lower layer enabled it. URL, model, and structured-output
values use the same precedence. Missing required URL/model values continue to
produce the current CLI configuration error when semantic execution is
enabled.

## Decision: secrets and adapter construction

Effective configuration contains only policy and execution settings. It never
contains a semantic API key, GitHub token, platform admin token, or database
DSN, and `resolve_effective_configuration()` never reads those secrets from
the environment. `ProjectSemanticConfig.api_key_env` may remain as a name for
the environment variable to consult; the key value is obtained only by the
adapter when semantic evaluation is enabled.

The CLI continues to create `OpenAICompatibleProvider`, its cache, and the
runtime executor after resolution. It reads the API key only at that boundary,
using the configured environment-variable name, and does not store the key in
`ScanOverrides`, `EffectiveScanConfiguration`, `ProjectConfig`, or scan
results. Platform DSN/token handling remains in `PlatformSettings` and worker
composition. No credential or DSN field is added to project scan configuration.

## Decision: replace C06's temporary CLI composition

For a complete CLI scan, `cli.scan` constructs invocation overrides from its
existing options, calls the application resolver once, and uses the result to:

- select the policy pack passed into the existing application scan workflow;
- configure the semantic provider from `effective.semantic`;
- configure runtime execution from `effective.runtime`; and
- pass project scan controls to application execution without repeating a
  source merge.

The post-C07 `application.scan.execute_scan()` contract is:

```python
@dataclass(frozen=True)
class ScanOptions:
    repository_root: Path


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

`configuration` is required and is the only source of resolved scan settings.
`ScanOptions` remains only as repository context: `policy_pack` and
`airflow_profile` are removed from it. `execute_scan()` does not call the
resolver or merge configuration values. It takes the selected pack from
`configuration.resolved_policy_pack`, scan controls and globs from
`configuration.project.scan`, and runtime settings from
`configuration.runtime`.

The semantic model and native structured-output setting come from
`configuration.semantic` when an adapter supplies `semantic_provider`.
`semantic_provider_name` remains an optional adapter metadata value passed
through to report metadata; it is not a configuration override. The
application does not construct provider or runtime adapters. An injected
provider/executor requests that optional phase; without one, that phase is
omitted even if the project file enables it. This preserves the platform's
current behavior when C10 later delegates to the application. The CLI
continues to inject each adapter when its resolved configuration enables that
phase, preserving its C06 behavior. Supplying an adapter for a disabled phase
is an input error. This replaces C06's direct-call error for an enabled
`runtime_config` without a `RuntimeExecutor`: after C07, a caller that does not
inject an executor has not requested runtime execution. The CLI still supplies
one whenever effective runtime is enabled, so its current validation and
execution behavior remain unchanged.

For C07, `execute_scan()` always passes
`configuration.runtime.airflow_version` to core, including an explicit `None`,
without conditioning it on `configuration.runtime.enabled`. A project profile
therefore continues to influence static/core evaluation when Docker runtime
execution is disabled; `runtime.enabled` controls only whether the optional
runtime phase executes. An explicit `--runtime-image` produces an effective
profile of `None`, so a lower-precedence project profile cannot reappear during
core evaluation. C07 does not populate the platform override's profile field,
so no persisted platform profile reaches this projection. C08 owns making its
validated platform profile effective without enabling runtime or changing
runtime-image selection.

`scan_repository()` remains the only core evaluation primitive and continues
to load project scan controls needed for discovery and repository-local
suppressions. Its profile argument must distinguish omission from an explicit
value: legacy/direct callers that omit `airflow_profile` retain the current
project-config fallback, while a C07 application call explicitly supplies the
effective profile, including `None`, and must not fall back to project config.
An internal sentinel/default semantic is one possible implementation; the
precise mechanism is deferred to the implementation plan. The explicit
effective profile prevents core from becoming a second configuration source.
The C07 platform runner remains a legacy direct core caller until C10 and does
not pass the persisted platform profile; its omitted profile argument
therefore retains project-config fallback. The core receives the already
selected absolute pack path, so that read does not make a second precedence
decision. Existing C06 inputs
`semantic_model`, `semantic_native_structured_output`, and `runtime_config`
are removed from `execute_scan()`; their effective values come only from
`configuration`. The C06 `ScanOptions.policy_pack` and
`ScanOptions.airflow_profile` fields are also removed. `semantic_provider`,
`semantic_provider_name`, `runtime_executor`, baseline, operational
suppressions, and parse-cache injection remain phase adapters/metadata rather
than competing configuration sources.

For CLI parity, the adapter enables a runtime executor only under the same
conditions as C06. `execute_scan()` always passes the effective profile to
core evaluation, including `None`; it creates/runs the runtime adapter only
when runtime is enabled. This preserves profile selection from project config
while disabled and ensures an explicit `--runtime-image` clears that profile
for core evaluation. The current error mapping, offline default, report
fields, fingerprints, renderers, and exit precedence remain unchanged. Preview
mode continues to avoid provider/runtime construction and uses the resolved
pack.
Other CLI commands such as `fix` and `doctor` are outside C07; they are not
complete application scan entry points.

## Decision: platform seam and C08/C10 boundaries

The platform runner passes the repository's policy-pack value through
`platform_overrides` and uses `resolved_policy_pack` both for its current core
scan call and its separate gate-pack load. It does not read, parse, or pass
`RepositoryRow.airflow_profile` in C07. This removes its independent choice
between repository and project policy-pack values without moving scan,
suppression, normalization, baseline, gate, persistence, or fencing logic.
Those remaining runner responsibilities stay in C10.

`ScanOverrides.airflow_profile` is typed as `AirflowProfile | None`, so the
canonical resolver can accept a typed profile from callers such as the CLI.
The existing platform string is deliberately not converted into this type in
C07. C08 owns validating repository/API/workspace values, handling invalid
historical persisted values, populating `platform_overrides.airflow_profile`,
and making that override effective. C07 adds no database migration and does
not change the platform profile's observable scan behavior.

The resolver may return project-level semantic and runtime settings for any
adapter, but C07 does not activate semantic or Docker runtime phases in
platform scans; the current runner has no semantic-provider or
runtime-executor composition. The project Airflow profile may still affect
core static evaluation through the current direct-call fallback; that does not
execute the runtime phase. C10 must preserve platform phase behavior while
delegating orchestration unless a later approved slice explicitly changes
platform opt-in semantics. Sharing a resolved configuration does not itself
imply execution of an optional phase.

## Behavior and error contract

- Project defaults remain unchanged when no overrides are present.
- The resolver's output is the only resolved configuration passed to
  `execute_scan()`; the removed C06 keyword values cannot override or disagree
  with it.
- Invalid project configuration and invalid override combinations fail before
  scanning with a configuration/input error mapped by the calling adapter.
- Invalid semantic URL/model settings fail only when semantic is enabled, as
  today; secret lookup remains lazy and is skipped when disabled.
- A resolved pack path is stable across the scan and gate phases in each
  caller. CLI relative explicit paths remain invocation-directory-relative;
  project-relative paths remain repository-relative; platform workspace paths
  remain workspace-relative at load time and absolute after registration.
- C07 changes no report schema, fingerprint inputs, scan engine, policy schema,
  platform database schema, or CLI output/exit contract.

## Verification required for the later implementation plan

The implementation plan should require a precedence matrix across all four
layers for every override field, including explicit `False`, no-override
defaults, project-file defaults, and invocation-over-platform behavior. It
should cover conflicting runtime selectors, configured runtime state with
explicit CLI selectors, path-origin behavior, semantic enablement and lazy
secret lookup, and the absence of keys/tokens/DSNs from both value objects.
CLI characterization must retain C06 output and exit parity for deterministic,
semantic, runtime, suppression, baseline, and gate cases. Platform checks must
prove repository policy-pack precedence and show that C07 does not make the
stored Airflow profile or project semantic/runtime options execute in the
runner. The later implementation plan must name the repository checks and
compatibility evidence required before implementation is considered complete.

## Self-review

- **Completeness:** The resolver owner, source order, path origins, partial
  override semantics, secrets boundary, exact post-C07 `execute_scan()`
  contract, omitted-versus-explicit core profile semantics, CLI migration, and
  C08/C10 cut lines are specified.
- **Consistency:** The profile override is typed in the resolver contract,
  while the persisted platform string is not wired until C08. Resolver output
  alone does not activate runtime or semantic phases in the platform runner;
  phase adapters are separate from effective configuration values.
- **Scope:** C07 centralizes configuration resolution and composes existing
  adapters; C08 makes the platform profile effective; C10 migrates the
  platform scan workflow. Product code, tests, and implementation planning are
  deferred until the applicable review gates.
- **Ambiguity:** The C06 runtime selector interaction is recorded as an
  explicit CLI-only rule, including the profile clear implied by
  `--runtime-image`. `None` means absence in ordinary override values; the
  selector mapping is the explicit exception. The core scan contract
  distinguishes omitted profile from explicitly supplied `None`. C06's
  direct-call runtime-config/executor validation is explicitly replaced by
  adapter-requested runtime execution while CLI behavior remains the same.
