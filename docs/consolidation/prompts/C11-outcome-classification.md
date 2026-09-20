# C11 — Centralize Application Outcome Classification

## Role and objective

You are the Build agent for C11. Give adapters one typed interpretation of a completed report so CLI exit codes, platform terminal state, and future MCP results cannot drift.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C06/C10.
- `src/conformdag/models.py:ScanReport`, `src/conformdag/gates.py`, `src/conformdag/cli.py`, `src/conformdag/application/scan.py`, and `src/conformdag/platform/runner.py`.
- `tests/test_cli.py`, `tests/test_gates.py`, and application/platform tests.

## Current ownership and resulting owner

CLI exit mapping and runner completion currently infer success from report details independently. After this PR, `src/conformdag/application/outcomes.py` owns `ExecutionOutcome` and `classify_report(report)`, while transports map outcomes to their own wire/exit representations.

## Interfaces

```python
class ExecutionOutcome(StrEnum):
    SUCCESS = "success"
    POLICY_FAILURE = "policy_failure"
    INCOMPLETE = "incomplete"


def classify_report(report: ScanReport) -> ExecutionOutcome: ...
```

The classifier treats fatal issues as incomplete, failed gates/blocking findings/runtime FAIL observations as policy failure, and all other complete reports as success.

## Expected files

- Create: `src/conformdag/application/outcomes.py` and `tests/application/test_outcomes.py`.
- Modify: `application/scan.py`, `cli.py`, `platform/runner.py`, and focused tests.
- Do not add MCP code or alter `ScanReport` serialization.

## Test-first sequence

1. Add one table-driven classifier test for complete pass, complete policy failure, fatal issue, runtime failure, suppressed findings, and missing gate.
2. Run the focused test and confirm the classifier is absent.
3. Implement the classifier and replace duplicated adapter inference.
4. Preserve CLI mapping `success=0`, `policy_failure=1`, invalid input `2`, incomplete `3`; platform persistence keeps its existing state contract.
5. Run outcome, CLI, application, runner, gate, and platform tests, then `mise run check`.

## Allowed changes

- Outcome enum/classifier, adapter mappings, and table-driven tests.

## Non-goals and prohibitions

- Do not make outcome classification depend on HTTP, Typer, SQLAlchemy, or exception-message parsing.
- Do not change gate rules or finding blocking semantics in this PR.

## Verification matrix

- Classifier table and adapter exit/state tests.
- Default suite, coverage, and report schema compatibility checks.

## Completion checklist and handoff

- [ ] One classifier owns complete-report outcome semantics.
- [ ] CLI and runner no longer infer success independently.
- [ ] Suppressed findings and incomplete diagnostics map correctly.
- [ ] Commit with `feat: centralize scan outcomes`; open the PR without merging.
