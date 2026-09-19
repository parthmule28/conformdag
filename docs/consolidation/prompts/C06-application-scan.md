# C06 — Introduce the Complete Application Scan Workflow

## Role and objective

You are the Build agent for C06. Add the reusable application scan workflow that the CLI can call first and platform/MCP can consume later. Keep `scan_repository()` as the canonical core evaluation primitive; do not rewrite it or create a second evaluator.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C03–C05 prompts.
- `src/conformdag/scan.py`, `src/conformdag/cli.py:scan`, `src/conformdag/runtime.py`, `src/conformdag/gates.py`, `src/conformdag/reporting.py`, and `src/conformdag/models.py`.
- `src/conformdag/platform/runner.py` for the current duplicated orchestration.
- `tests/test_scan.py`, `tests/test_cli.py`, `tests/test_runtime.py`, and `tests/test_gates.py`.

## Current ownership and resulting owner

The CLI and platform runner each add runtime, baseline/gate, suppression, normalization, and exit behavior around `scan_repository()`. After this PR, `src/conformdag/application/scan.py` owns complete application orchestration; the CLI becomes a composition/rendering adapter, while platform delegation waits for C10.

## Interfaces

Produce these typed interfaces without putting transport dependencies in them:

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

Use a `RuntimeExecutor` protocol and `execute_scan()` to compose config, core scan, runtime observations, operational suppressions, normalization, and gates without applying gates to incomplete reports.

## Expected files

- Create: `src/conformdag/application/__init__.py`, `application/scan.py`, `application/errors.py`, and `tests/application/test_scan.py`.
- Modify: `src/conformdag/cli.py` to delegate scan orchestration, `src/conformdag/gates.py`/`reporting.py` only where an application-facing seam is required, and focused tests.
- Do not migrate the platform runner in this PR; C10 owns that.

## Test-first sequence

1. Add application tests for deterministic scans, semantic success/failure, runtime success/failure, baseline pass/fail, incomplete-gate suppression, operational suppression, runtime metadata, and report parity.
2. Run `mise exec -- uv run pytest tests/application/test_scan.py -x --tb=short` and confirm the new API is absent.
3. Implement the application service with dependency injection for semantic and runtime adapters; call `scan_repository()` exactly once per execution.
4. Migrate the CLI scan command to map arguments into `ScanOptions`, construct adapters, render the returned report, and preserve exit behavior.
5. Run application, CLI, scan, runtime, gate, fixing, and round-trip tests, then `mise run check` and coverage.

## Allowed changes

- Add application dataclasses/protocols, orchestration, CLI delegation, and parity tests.
- Keep repository-local suppressions inside core initially; supplied operational suppressions are an explicit application input.

## Non-goals and prohibitions

- Do not add FastAPI, Typer, SQLAlchemy, or MCP imports to `application`.
- Do not silently evaluate gates on incomplete reports.
- Do not create `platform_scan()` or `mcp_scan()` equivalents.
- Do not weaken verify-by-rescan fixing or offline defaults.

## Verification matrix

- Application parity and failure-mode tests.
- Existing CLI/scan/runtime/gate suites and round-trip benchmark.
- `mise run check`, coverage, and strict Pyright.
- High-risk independent review must compare old CLI reports with application results while ignoring only intentionally volatile timestamps.

## Completion checklist and handoff

- [ ] `execute_scan()` is the only complete application workflow.
- [ ] `scan_repository()` remains the only core evaluation primitive.
- [ ] CLI no longer owns runtime/gate/suppression business rules.
- [ ] Incomplete reports never receive a gate result.
- [ ] Commit with `feat: add application scan workflow`; open the PR without merging.
