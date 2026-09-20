# C18 — Decompose Reporting

## Role and objective

You are the Build agent for C18. Split reporting normalization, suppressions, SARIF, and HTML into cohesive modules while keeping `ScanReport` canonical and preserving renderer output.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C06/C16.
- Full `src/conformdag/reporting.py`, `src/conformdag/models.py`, `src/conformdag/scan.py`, `src/conformdag/gates.py`, and platform runner usage.
- `tests/test_reporting.py`, `tests/test_scan.py`, `tests/test_cli.py`, and platform export tests.

## Current ownership and resulting owner

`reporting.py` currently owns suppression application, normalization/fingerprints, blocking classification, SARIF, and HTML. After this PR, `reporting/normalize.py` owns canonical sorting/fingerprints, `reporting/suppressions.py` owns suppression application, and `reporting/sarif.py`/`html.py` own projections. Outcome/blocking decisions move to application/gates only where C11 requires them.

## Interfaces

Preserve `apply_suppressions()`, `normalize_report()`, `render_sarif()`, and `render_html()` through `reporting/__init__.py`. Keep renderer inputs as `ScanReport` and never make a renderer recalculate policy semantics.

## Expected files

- Create: `src/conformdag/reporting/__init__.py`, `normalize.py`, `suppressions.py`, `sarif.py`, `html.py`.
- Remove: `src/conformdag/reporting.py` only after import parity.
- Modify: scan/application/CLI/platform imports and split/add `tests/reporting/` modules.

## Test-first sequence

1. Add import-parity tests and snapshots for normalized report ordering, suppression behavior, SARIF, and HTML.
2. Run current reporting/scan/CLI/platform tests before moving code.
3. Move functions without changing fingerprint or renderer payload inputs.
4. Run focused, full non-runtime, coverage, and package export tests.

## Allowed changes

- Package movement, facade exports, test split, and removal of duplicated renderer imports.

## Non-goals and prohibitions

- Do not change fingerprint inputs; C19 owns the explicit contract.
- Do not make reporting own CLI exit codes, database persistence, or gate policy.
- Do not add transport-specific suppression logic.

## Verification matrix

- Reporting, scan, CLI, platform export, and round-trip tests.
- `mise run check`, coverage, and SARIF/HTML parse checks.

## Completion checklist and handoff

- [ ] Normalization, suppressions, and renderers have separate owners.
- [ ] `ScanReport` remains canonical.
- [ ] Old public imports remain available.
- [ ] Commit with `refactor: split reporting package`; open the PR without merging.
