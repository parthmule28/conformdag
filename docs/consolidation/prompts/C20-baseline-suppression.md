# C20 — Unify Baseline and Suppression Semantics

## Role and objective

You are the Build agent for C20. Give CLI, platform, and future adapters one canonical baseline value and one canonical suppression path without changing the existing report or gate behavior.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C11/C19.
- `src/conformdag/gates.py`, `src/conformdag/reporting/`, `src/conformdag/application/scan.py`, `src/conformdag/platform/runner.py`, `src/conformdag/platform/db.py`, and `src/conformdag/models.py`.
- CLI baseline loading in `src/conformdag/cli.py` and tests for baseline, gates, suppressions, retention, and platform runner.

## Current ownership and resulting owner

Gate evaluation accepts either a baseline report or fingerprint set, and platform retention has its own representation. After this PR, a canonical `Baseline` value object and constructors own that distinction; compatibility wrappers remain while callers migrate.

## Interfaces

```python
@dataclass(frozen=True)
class Baseline:
    fingerprints: frozenset[str]


def baseline_from_report(report: ScanReport) -> Baseline: ...
def baseline_from_fingerprints(fingerprints: Iterable[str]) -> Baseline: ...
```

`evaluate_pack_gates(pack, report, baseline)` becomes the preferred form; the old report/fingerprint parameters remain as a deprecation wrapper until C30.

## Expected files

- Create or place: `src/conformdag/application/baselines.py` or the agreed domain module, plus focused tests.
- Modify: `gates.py`, `application/scan.py`, `cli.py`, `platform/runner.py`, and baseline/reporting tests.
- Do not change database retention schema or finding fingerprint construction.

## Test-first sequence

1. Add tests for report/fingerprint constructors, empty baselines, artifact-pruned reports, no-new findings, suppression timing, and baseline eligibility.
2. Run current gate/platform/CLI tests.
3. Implement the value object and migrate application/runner/CLI callers.
4. Keep the compatibility wrapper and assert equivalent results for both forms.
5. Run gates, reporting, scan, CLI, platform, round-trip, coverage, and `mise run check`.

## Allowed changes

- Baseline value object, constructors, gate signature adapter, and caller migration.

## Non-goals and prohibitions

- Do not redefine fingerprint identity or baseline eligibility.
- Do not apply operational suppressions inside core repository-local suppression loading.
- Do not let frontend code calculate baseline truth.

## Verification matrix

- Application, gate, CLI, runner, retention, and suppression tests.
- `mise run check`, coverage, and round-trip benchmark.
- Review artifact-pruned baseline behavior.
- Independent review must compare report-backed and fingerprint-only baselines, suppression timing, and server-authoritative eligibility.

## Completion checklist and handoff

- [ ] One baseline representation serves report and fingerprint inputs.
- [ ] Suppression timing remains before gate/outcome calculation.
- [ ] Compatibility wrapper is documented for C30.
- [ ] Commit with `refactor: unify baseline semantics`; open the PR without merging.
