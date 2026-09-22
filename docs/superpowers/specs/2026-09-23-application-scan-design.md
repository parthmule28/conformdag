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
    semantic_enabled: bool | None = None,
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

`application/errors.py` defines only the distinctions needed here:
`ScanInputError(ValueError)` for invalid phase input/preflight and
`RuntimeExecutionError(RuntimeError)` for an injected runtime execution failure.
The CLI adapter translates `RuntimePhaseError` during validation to the former,
and during execution to the latter. Application code turns only the latter
into a structured fatal runtime issue; unrelated exceptions are not swallowed.
Broader cross-adapter error taxonomy belongs to C45.

## Execution order and data semantics

1. Resolve the repository root and load the project config and selected policy
   pack through existing helpers for runtime defaults and gates. An explicitly
   supplied pack keeps its current invoker-working-directory semantics; a
   configured relative pack remains relative to the repository. Validate a
   baseline before scanning: reject an incomplete report or simultaneous
   `report` and `fingerprints`; `None` means no baseline. Missing required
   semantic/runtime adapters and contradictory phase inputs fail preflight.
   The injected runtime adapter validates an enabled runtime before scanning.
2. Call `scan_repository(root, options.policy_pack, ...)` **exactly once** after
   successful preflight, passing the selected Airflow profile, parse cache, and
   any injected semantic provider/metadata. Core still owns its config/pack
   lookup, local suppressions, deterministic checks, and semantic evaluation.
   C06 does not redesign its signature to eliminate the duplicate lookup.
3. If runtime is enabled, call the injected executor with the resolved runtime
   config, scan include/exclude globs, and the sorted union of evaluated and
   skipped policy IDs. Preserve observation order normalization, fatal
   `RUNTIME_OBSERVATION_ERROR` for `ERROR` observations, the image digest,
   runtime profile, and resolved runtime metadata. An execution failure adds
   fatal `RUNTIME_EXECUTION_ERROR` and marks the report incomplete; a `FAIL`
   observation remains a nonfatal outcome. Run this phase even if the core
   report is already incomplete, matching current CLI behavior.
4. Apply only *supplied* operational suppressions after the core scan (and
   runtime), through `reporting.apply_suppressions`. Repository-local
   suppressions remain inside core. Preserve a pre-existing local suppression
   and its provenance when the same finding is also matched operationally;
   append suppression diagnostics for expired, unmatched, or duplicate supplied
   entries. If all remaining unsuppressed `ERROR` findings are waived, remove
   only the fatal `EVALUATION_ERROR` produced for those findings and recompute
   completeness from the other fatal issues. A parse, provider, or runtime
   failure cannot be waived this way. With no operational input, leave core
   suppression state alone.
5. Call `normalize_report()` once on the final findings, observations, issues,
   and metadata, including the no-runtime path. This recalculates the canonical
   result fingerprint after application mutations. No schema or fingerprint
   algorithm change is intended; the gate result is excluded from that hash as
   it is today.
6. **Only if the normalized report is complete**, call
   `evaluate_pack_gates()` with the baseline report when present and a set of
   baseline fingerprints when present; pass `None` for either absent input.
   A pack without gates yields `None`. Embed a non-`None` result in
   `ScanReport.gate_result` and return the same result in
   `ScanExecutionResult.gate_result`. On an incomplete report return `None` in
   both places; never evaluate gates or attach stale gate data to it.

The effective semantic flag follows an explicit `semantic_enabled` override
when provided; otherwise an injected provider opts in, or project config
enables semantic evaluation. An enabled semantic phase without a provider or
model fails preflight; an explicit disable with a provider is contradictory.
The semantic model keyword takes precedence over the project semantic model;
the structured-output keyword takes precedence over its project default.
The CLI continues to construct and configure the provider and resolve secrets
only at its adapter boundary. An enabled runtime uses an explicit
`runtime_config` when supplied or the project default; it requires an injected
executor. `ScanOptions.airflow_profile` overrides the static scan profile;
otherwise an enabled runtime supplies its profile as today's CLI does. A
conflicting explicit scan profile and runtime profile is a preflight error;
the full precedence resolver is deferred to C07.

## CLI and platform boundaries

`cli.scan` parses flags, resolves adapter-only semantic configuration (URL,
model, environment key, cache), maps runtime flags to a typed runtime config,
constructs the runtime adapter, parses baseline JSON into `ScanReport` (the
application validates baseline eligibility), and calls `execute_scan`. Its
CLI-only preview path keeps using `preview_model_context()` without starting a
complete scan. CLI format and
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
  completeness recovery, baseline report/fingerprint paths, conflicting or
  incomplete baseline rejection, complete/incomplete gate behavior, and final
  fingerprint/report parity. Use fake executors; no Docker or provider calls.
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
