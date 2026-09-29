# C11 — Centralize scan outcome classification

## Intent and scope

Give CLI, platform, and future adapters one reproducible interpretation of a completed `ScanReport`, including reports loaded from storage. Preserve the existing CLI exit codes, platform lifecycle semantics, report JSON shape, gate rules, and finding-blocking rules. C11 does not add MCP code, modify `ScanExecutionResult`, or change scan orchestration.

## Application contract

`src/conformdag/application/outcomes.py` owns a transport-neutral `ExecutionOutcome(StrEnum)` with `SUCCESS = "success"`, `POLICY_FAILURE = "policy_failure"`, and `INCOMPLETE = "incomplete"`, and the pure function `classify_report(report: ScanReport) -> ExecutionOutcome`. Classification depends only on the supplied canonical report, not exceptions, transport types, persistence, or hidden state. It can therefore be repeated for a stored report. The classifier uses `conformdag.gates.blocking_findings(report)` for the existing unsuppressed blocking semantics; it does not use the exit-code-oriented `reporting.has_blocking_failures()`.

Apply precedence in this order:

1. `not report.complete` **or** any fatal issue → `INCOMPLETE`, regardless of other signals.
2. A present failed gate → `POLICY_FAILURE`.
3. A present passing gate skips the blocking-finding check; with no gate, nonempty `blocking_findings(report)` → `POLICY_FAILURE`.
4. Any runtime observation with status `FAIL` → `POLICY_FAILURE`, even with a passing gate.
5. Otherwise → `SUCCESS`.

No gate means the existing legacy blocking-finding path applies, not an incomplete scan. Suppressed findings do not block through that path. Do not change how gates or finding blocking are computed.

## Adapter mappings and error handling

After rendering the report, CLI maps `SUCCESS` to exit 0, `POLICY_FAILURE` to exit 1, and `INCOMPLETE` to exit 3. Invalid input remains exit 2 through existing exception/preflight handling, outside `classify_report()`. Report serialization and output formatting stay unchanged.

The platform runner maps both `SUCCESS` and `POLICY_FAILURE` to terminal `ScanStatus.SUCCEEDED`; the canonical report carries the policy outcome. Only `INCOMPLETE` maps to `ScanStatus.FAILED` and the existing concise incomplete-error message. Preserve report/finding ingestion, cancellation and claim-attempt fencing, subprocess return behavior, and exception-to-failed handling. A failed gate, blocking finding, or runtime `FAIL` must not become a failed platform execution.

The application workflow keeps returning `ScanExecutionResult(report, gate_result)` unchanged. Adapters classify its final report instead of duplicating success inference. Future adapters may call the same function on deserialized reports.

## Testing and verification

First add a table-driven classifier test covering complete pass, failed gate, passing gate plus blocking finding (success), passing gate plus runtime `FAIL` (policy failure), no-gate blocking finding, suppressed blocking finding, fatal issue, `complete=False` without fatal issue, and no gate with no failures. Confirm the test fails because the classifier is absent before implementing it. Add focused CLI and runner regressions for exit/state mappings, including that policy failure persists as platform success and incomplete persists as failure. Run outcome, CLI, application, runner, gate, and platform tests, then `mise run check`, `mise run test:coverage`, and `mise run schema --check`; report unavailable environment gates rather than claiming they passed.

## Boundaries

Touch `application/outcomes.py`, `cli.py`, `platform/runner.py`, and focused tests; change `application/scan.py` only if an existing seam genuinely requires it. No schema/model changes, SQL migrations, new evaluation pipeline, or transport dependencies in the application layer. Update only the C11 progress ledger row with actual evidence. Open a PR without merging, as required by the C11 slice contract.
