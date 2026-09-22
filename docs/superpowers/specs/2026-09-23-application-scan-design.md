# C06 — Complete Application Scan Workflow Design

## Intent

Give the CLI one reusable application workflow for complete scans, with an
interface a later platform or MCP adapter can call. Move runtime composition,
operational suppression, final normalization, and baseline/gate evaluation out
of `cli.scan` without changing the canonical `ScanReport` JSON, CLI rendering,
exit codes, or the offline default. `scan_repository()` remains the only core
evaluation primitive, invoked once per execution that passes preflight.

This is **Approach 1**: small scan options and separate typed phase inputs.
It avoids a transport-shaped invocation object and a second scan or semantic
pipeline. C06 changes the CLI; C10, not C06, migrates the platform runner.
Any temporary CLI composition in C06 exists only to preserve current behavior;
C07 intentionally replaces it with centralized effective configuration.

## Contract and ownership

`src/conformdag/application/scan.py` exposes these dataclasses with exactly the
fields below:

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

`execute_scan()` accepts phase-specific inputs as separate typed keywords:

```python
class RuntimeExecutor(Protocol):
    def validate(
        self, root: Path, config: ProjectRuntimeConfig, include: list[str], exclude: list[str]
    ) -> None: ...

    def execute(
        self, root: Path, config: ProjectRuntimeConfig, policy_ids: list[str],
        include: list[str], exclude: list[str]
    ) -> tuple[list[RuntimeObservation], str]: ...


def execute_scan(
    options: ScanOptions,
    *,
    semantic_provider: SemanticProvider | None = None,
    semantic_provider_name: str | None = None,
    semantic_model: str | None = None,
    semantic_native_structured_output: bool | None = None,
    runtime_config: ProjectRuntimeConfig | None = None,
    runtime_executor: RuntimeExecutor | None = None,
    baseline: BaselineInput | None = None,
    operational_suppressions: Sequence[Suppression] = (),
    parse_cache: ParseCache | None = None,
) -> ScanExecutionResult: ...
```

Keep provider credentials, image choices, output format, filesystem
destinations, and exit codes out of `ScanOptions` and result types.
`RuntimeExecutor` is an application-owned protocol. Its validation takes place
before the core scan, as today's CLI manifest preflight does; execution runs
afterward. `parse_cache` is an optional typed seam for a future runner adapter.
The CLI supplies an adapter that calls the existing `build_runtime_manifest()`
and `execute_runtime()` functions. `application` imports neither Docker/runtime
infrastructure nor CLI/platform/HTTP/persistence types.

An injected semantic provider is the complete semantic execution input: the
application passes it into the one core scan and does not derive an enabled
state or resolve provider/model/structured-output precedence from project
configuration. A supplied `runtime_config` is executed as given; `None` or a
disabled config omits runtime. The CLI composes both phases using its current
behavior until C07 centralizes that work.

`application/errors.py` defines only the distinctions needed here:
`ScanInputError(ValueError)` for invalid phase input/preflight and
`RuntimeExecutionError(RuntimeError)` for an injected runtime execution failure.
The CLI adapter translates `RuntimePhaseError` during validation to the former,
and during execution to the latter. Application code turns only the latter
into a structured fatal runtime issue; unrelated exceptions are not swallowed.
Broader cross-adapter error taxonomy belongs to C45.

## Execution order and data semantics

1. Resolve the repository root and load the project config and selected policy
   pack through existing helpers for scan globs and gates. An explicitly
   supplied pack keeps its current invoker-working-directory semantics; a
   configured relative pack remains relative to the repository. Validate a
   baseline before scanning: reject an incomplete report or simultaneous
   `report` and `fingerprints`; `None` means no baseline. A semantic provider
   requires the model needed by `scan_repository()`. An enabled supplied runtime
   config requires an injected executor, which validates it before scanning.
   The service does not construct or overlay semantic/runtime phase config from
   project settings; temporary CLI composition preserves current behavior until
   C07 replaces it.
2. Call `scan_repository(root, options.policy_pack, ...)` **exactly once** after
   successful preflight, passing `options.airflow_profile` unchanged, the parse
   cache, and any injected semantic provider/metadata. Core still owns its
   config/pack lookup, local suppressions, deterministic checks, and semantic
   evaluation. C06 does not redesign its signature to eliminate the duplicate
   lookup.
3. If a supplied runtime config is enabled, call the injected executor with that
   config, scan include/exclude globs, and the sorted union of evaluated and
   skipped policy IDs. Preserve observation order normalization, fatal
   `RUNTIME_OBSERVATION_ERROR` for `ERROR` observations, the image digest,
   runtime profile, and resolved runtime metadata. An execution failure adds
   fatal `RUNTIME_EXECUTION_ERROR` and marks the report incomplete; a `FAIL`
   observation remains a nonfatal outcome. Run this phase even if the core
   report is already incomplete, matching current CLI behavior.
4. Apply only *supplied* operational suppressions after the core scan (and
   runtime), through `reporting.apply_suppressions`. Repository-local
   suppression behavior remains unchanged inside core. Extend the helper so an
   already-suppressed finding retains its existing `suppression` object when a
   matching operational suppression is processed; the local suppression
   remains the provenance source, and a cross-layer match is not diagnosed as a
   duplicate. Continue duplicate, unmatched, and expired diagnostics for the
   supplied operational list itself. If an expired operational suppression
   matches a finding that remains suppressed locally, its diagnostic must not
   claim that the finding was reopened. If all remaining unsuppressed `ERROR`
   findings are waived, remove only the fatal `EVALUATION_ERROR` produced for
   those findings and recompute completeness from the other fatal issues. A
   parse, provider, or runtime failure cannot be waived this way. With no
   operational input, leave core suppression state alone.
5. After all post-core runtime and suppression mutations, `execute_scan()` calls
   `normalize_report()` exactly once as its final application-level
   normalization, including the no-runtime path. `scan_repository()` already
   performs its own core normalization; do not remove or redesign it in C06.
   The application normalization recalculates the canonical result fingerprint
   after its mutations. No schema or fingerprint algorithm change is intended;
   the gate result is excluded from that hash as it is today.
6. **Only if the normalized report is complete**, call
   `evaluate_pack_gates()` with the baseline report when present and a set of
   baseline fingerprints when present; pass `None` for either absent input.
   A pack without gates yields `None`. Embed a non-`None` result in
   `ScanReport.gate_result` and return the same result in
   `ScanExecutionResult.gate_result`. On an incomplete report return `None` in
   both places; never evaluate gates or attach stale gate data to it.

The CLI continues to construct and configure the semantic provider and resolve
secrets at its adapter boundary. It constructs the runtime config using its
existing CLI/project behavior and supplies that config plus a runtime adapter
when enabled. For CLI parity, it sets `ScanOptions.airflow_profile` to the
runtime config's profile when runtime is enabled, as the current CLI passes
that profile to the core scan; otherwise it passes `None`. The application
passes this value through unchanged and defines no runtime/profile conflict
rule. This is temporary adapter composition, not an application-level
precedence contract. C07 owns and intentionally replaces this composition with
`ScanOverrides`, `EffectiveScanConfiguration`, and the explicit invocation →
platform override → project config → defaults resolver.

## CLI and platform boundaries

`cli.scan` parses flags and temporarily composes semantic and runtime settings
with project config using its current behavior solely to preserve parity: it
constructs the semantic provider (resolving URL, model, structured output,
environment key, and cache), maps runtime flags to a typed runtime config,
constructs the runtime adapter, and sets `ScanOptions.airflow_profile` to the
runtime profile only when runtime is enabled, matching the current scan call.
It parses baseline JSON into `ScanReport` (the application validates baseline
eligibility) and calls `execute_scan`. C07 intentionally replaces this temporary
composition with centralized effective configuration; C06 defines no reusable
precedence/conflict matrix. Its CLI-only preview path keeps using
`preview_model_context()` without starting a complete scan. CLI format and
destination validation, evidence-stripping for presentation, JSON/SARIF/HTML/
terminal rendering, progress text, and exit mapping stay in the CLI. The exit
precedence remains fatal issue → 3; failed gate → 1; absent gate with blocking
findings → 1; any failing runtime observation → 1; otherwise 0. A passing gate
still overrides legacy blocking findings. `--no-evidence` must not mutate the
canonical result or its fingerprint. Invalid CLI/preflight/baseline input
remains exit 2; runtime execution failures remain structured exit 3.

No `platform/runner.py` edits or new runner-specific entry point are in C06.
Its current orchestration and fenced persistence remain until C10. The
application accepts canonical `Suppression` and `BaselineInput` values so C10
can adapt platform rows and retained fingerprints without importing SQLAlchemy
into `application`.

## Verification and review

- Add `tests/application/test_scan.py` first: deterministic/default-offline
  result, exactly one core invocation, injected semantic success/failure inside
  that invocation, runtime preflight before scanning, runtime success/error/
  failed observation and metadata, operational suppression and targeted
  completeness recovery, baseline report/fingerprint paths, incomplete baseline
  rejection, complete/incomplete gate behavior, and final fingerprint/report
  parity. Include a focused regression where a core report already contains a
  repository-local suppression and a matching operational suppression: the
  finding stays suppressed, retains the original suppression provenance, and
  the cross-layer match does not create duplicate suppression semantics. Test
  the reporting helper's provenance rule directly as well. Use fake executors;
  no Docker or provider calls.
- Characterize CLI output and exits across JSON/SARIF/HTML/terminal, evidence
  stripping, preview mode, semantic config errors, runtime validation/failure,
  configured/explicit pack, baseline, and gated versus legacy outcomes. Update
  mocking seams only where the runtime adapter now owns the call.
- Compare before/after CLI reports for representative deterministic, semantic,
  runtime, suppressed, and gated cases, ignoring only timestamps or other
  intentionally volatile invocation metadata. Preserve source/finding identity,
  result fingerprints, canonical JSON fields, and existing error messages where
  practical. Run focused application/CLI/scan/runtime/gates/reporting/fixing and
  round-trip tests, then `mise run check`, `mise run test:coverage`, schema check,
  and independent high-risk review before an implementation PR.
