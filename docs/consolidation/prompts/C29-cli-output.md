# C29 — Consolidate CLI Errors, Formats, and Exit Mapping

## Role and objective

You are the Build agent for C29. Make CLI presentation a thin, typed adapter over application results and domain errors, without catching intentional exits or changing established output/exit behavior.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C11/C18/C28.
- CLI modules after C28, `application/outcomes.py`, reporting renderers, policy/application errors, and all CLI tests.

## Current ownership and resulting owner

CLI command functions mix exception handling, format selection, rendering, and orchestration. After this PR, `cli/common.py` or the command adapters own `ReportFormat`, explicit domain-error translation, and render selection; application/reporting remain responsible for data and outcomes.

## Interfaces

```python
class ReportFormat(StrEnum):
    JSON = "json"
    SARIF = "sarif"
    HTML = "html"
    TERMINAL = "terminal"
```

Preserve exit mapping: success `0`, policy failure `1`, invalid input/configuration `2`, incomplete/operational `3`. Preserve explicit HTML destination requirements and diagnostics-off-stdout behavior.

## Expected files

- Modify: `src/conformdag/cli/common.py`, command modules, reporting imports, and CLI tests.
- Create/split: `tests/cli/test_output.py` if C33 has landed; otherwise add focused cases to current `tests/test_cli.py`.
- Do not change report renderers or application outcome semantics.

## Test-first sequence

1. Add table-driven tests for format parsing, terminal/JSON/SARIF/HTML rendering, domain errors, intentional `typer.Exit`, stdout/stderr, and exit codes.
2. Run current CLI output tests.
3. Implement typed format selection and narrow exception translation.
4. Run command-specific and package smoke tests.
5. Run `mise run check`, coverage, and render parse checks.

## Allowed changes

- Typed format enum, presentation helpers, explicit error mapping, and tests.

## Non-goals and prohibitions

- Do not catch `typer.Exit` as an error.
- Do not parse exception messages to infer domain outcomes.
- Do not move evaluation/business rules into output handling.

## Verification matrix

- CLI output/exit test matrix.
- Default gate, coverage, SARIF/HTML parsing, and installed-wheel CLI smoke.

## Completion checklist and handoff

- [ ] Exit mapping is centralized and preserved.
- [ ] Formats are typed and renderer selection is presentation-only.
- [ ] Diagnostics do not corrupt machine-readable stdout.
- [ ] Commit with `refactor: consolidate CLI output handling`; open the PR without merging.
