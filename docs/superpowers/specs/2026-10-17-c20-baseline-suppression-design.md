# C20 — Baseline and Suppression Semantics: Design

**Date:** 2026-10-17
**Status:** Stage A documentation-only review
**Baseline:** `main@103d606ab96fde091ba6a445152ff3e2bcea64d4`
**Issue:** [#72 — Unify Baseline and Suppression Semantics](https://github.com/parthmule28/conformdag/issues/72)

## 1. Purpose and stage boundary

C20 will give gate evaluation, application workflows, CLI, platform execution,
and future adapters one immutable baseline value and a single suppression-to-
gate flow. It is a compatibility refactor: existing reports, gate outcomes,
finding fingerprints, report fingerprints, and platform eligibility must not
change.

This document is Stage A design material. The current PR contains Markdown
planning documents only. It does not authorize Stage B implementation. Do not
start implementation until Stage A has merged, its post-merge CI has passed,
and the user explicitly authorizes it. Keep the C20 progress-ledger entry at
`planned` throughout Stage A. For Stage B, move it to `review` when the
implementation is complete and submitted for independent review. Record
`accepted` only in a separate post-implementation acceptance PR, after the
implementation PR is merged and its post-merge CI passes.

The design follows the [C20 handoff prompt](../../consolidation/prompts/C20-baseline-suppression.md),
[C19 fingerprint contract](../../architecture/fingerprints.md), and
[consolidation architecture rules](../../consolidation/architecture-rules.md).

## 2. Current behavior at the baseline

- `BaselineInput` is a frozen application adapter with the ordered fields
  `report: ScanReport | None = None` and
  `fingerprints: frozenset[str] | None = None`. It is defined at
  `conformdag.application.scan.BaselineInput` and re-exported as
  `conformdag.application.BaselineInput`. CLI and platform runner import the
  application-level export.
- `execute_scan` rejects a `BaselineInput` containing both forms and rejects
  an incomplete report before invoking the core scan. No `BaselineInput`
  (`None`) means there is no baseline; an input with an empty fingerprint
  frozenset is still an explicitly supplied baseline.
- `evaluate_gate` and `evaluate_pack_gates` currently take the baseline
  report as their third positional argument (or as `baseline_report=`) and
  accept `baseline_fingerprints=` as a keyword. The rule resolver uses the
  report when both legacy sources are present; fingerprints are the fallback
  when no report is supplied.
- For `no-new-findings`, the baseline side contains every fingerprint in the
  baseline report. The current side is the set of unsuppressed blocking
  findings. Suppression identity remains `(policy_id, fingerprint)`.
- The platform accepts only a same-repository scan that is succeeded and has
  `complete is True`. If its report artifact has been pruned, the runner
  rebuilds the baseline input from retained `FindingRow.fingerprint` values.
  An eligible scan with no retained findings produces an empty set, not an
  ineligible or absent baseline.
- Repository-local suppressions are applied by the core scan. The application
  later applies active, exact-match operational suppressions, preserves local
  provenance, normalizes the final report, and evaluates gates. The returned
  report is then used by callers for outcome classification.

## 3. Ownership: one layer-neutral Baseline

Create `src/conformdag/baselines.py` as the owner of the canonical value and
its constructors. This root-level domain module is intentionally independent
of the application package: `conformdag.gates` is core code and must not
import `conformdag.application`. The gate layer and application adapters both
import the same Baseline from `conformdag.baselines`. The module may depend on
core models such as `ScanReport`; it must not depend on adapters, persistence,
or transport layers.

```python
@dataclass(frozen=True)
class Baseline:
    fingerprints: frozenset[str]


def baseline_from_report(report: ScanReport) -> Baseline: ...


def baseline_from_fingerprints(fingerprints: Iterable[str]) -> Baseline: ...
```

The value contains identities only, not a report, eligibility decision,
suppression records, persistence identifiers, or a second copy of scan
behavior.

### Construction rules

- `baseline_from_report` snapshots every finding fingerprint, including
  findings already marked suppressed. This matches the existing baseline
  report rule.
- `baseline_from_fingerprints` consumes an iterable once and snapshots it
  into a `frozenset`; later mutation of the source collection cannot mutate
  the Baseline.
- An empty `frozenset` is a valid Baseline. Absence is represented by
  `None`, not by an empty Baseline.
- Constructors do not redefine baseline eligibility or the existing
  incomplete-report error boundary. Application/CLI validation continues to
  reject incomplete report input, while the platform remains authoritative
  for persisted-scan eligibility.
- Fingerprint strings are neither recomputed, normalized, versioned, nor
  validated under a new format.

## 4. Gate API and legacy compatibility

The preferred form is:

```python
evaluate_pack_gates(pack, report, baseline)
evaluate_gate(gate, report, baseline)
```

The third positional argument accepts the canonical `Baseline` (and
`None`). For compatibility, a `ScanReport` in that position remains a
legacy report baseline. Preserve the existing `baseline_report=` and
`baseline_fingerprints=` keyword forms through C30. The report-wins rule
applies when legacy `baseline_report` and `baseline_fingerprints` are both
provided, whether the report is positional or keyword: use all fingerprints
from the report and ignore the fingerprint argument. Keep this behavior in
both gate helpers.

Do not blend a canonical Baseline argument with legacy source arguments in one
call. Reject that ambiguous mixed form with `ValueError`. The report-wins
precedence is specifically for the established legacy report/fingerprint pair.

This gate-level compatibility does not change application validation:
`execute_scan(baseline=BaselineInput(report=..., fingerprints=...))` continues
to reject both fields being set, before the core scan call. The distinct
behaviors are deliberate and must have separate tests.

The gate continues to compare all fingerprints from the selected baseline
with the final report's unsuppressed blocking findings. Other gate rules,
gate-result selection, and report serialization remain unchanged.

### BaselineInput compatibility facade through C30

Keep the existing frozen `BaselineInput` compatibility type through C30,
including both import paths:

- `from conformdag.application import BaselineInput`
- `from conformdag.application.scan import BaselineInput`

Preserve its constructor fields, order, defaults, and names:
`report` followed by `fingerprints`; both default to `None`. Existing
construction with no arguments, with either keyword, or through existing CLI
and runner imports must continue to work through C30. During migration, the
application converts this boundary adapter to the root-level Baseline. Do not
move ownership of the canonical Baseline into the application package merely
to keep the legacy adapter importable.

## 5. Absence, empty baselines, eligibility, and pruning

Keep these states distinct at the source boundary:

| State | Application representation | Meaning |
| --- | --- | --- |
| No baseline selected, missing, or ineligible | `None` | No usable baseline was supplied |
| Eligible baseline with no findings | `Baseline(fingerprints=frozenset())` | A real baseline exists and has an empty identity set |
| Eligible baseline with findings | Baseline containing their fingerprints | Compare against those existing identities |

For the `no-new-findings` rule, the first two states may result in the same
empty comparison set, as they do today. They must not be collapsed in
application/platform resolution: eligibility, baseline status, and retention
behavior depend on whether a baseline exists.

The platform continues to use `eligible_baseline`: the selected scan must
belong to the same repository, have succeeded, and have `complete is True`.
Missing, cross-repository, queued, running, failed, cancelled, or incomplete
scans remain ineligible. The setter continues rejecting an ineligible scan;
the runner treats a missing or ineligible configured selection as no
baseline. The frontend does not compute this truth.

When the selected scan is eligible:

- If `report_json` is present, build the Baseline from its report.
- If retention has pruned `report_json`, build it from retained
  `FindingRow.fingerprint` values.
- If there are zero retained rows, construct an empty Baseline. Do not return
  `None`, even though the report artifact is unavailable.

This keeps report-backed and artifact-pruned gate behavior equivalent without
reconstructing the report or changing the retention schema.

## 6. Suppression precedence and outcome timing

Retain one orchestration path and the current ownership:

1. The single core `scan_repository` invocation loads and applies
   repository-local suppressions.
2. The application adds runtime observations when configured.
3. The application filters operational suppressions to active entries whose
   exact `(policy_id, fingerprint)` matches a finding in the current report,
   then applies them before normalization and gate evaluation. If a local
   suppression already supplied provenance, preserve it.
4. Normalize the fully suppressed report, then evaluate gates only for a
   complete report. Callers classify the resulting report/outcome afterward.

Operational suppressions do not move into core repository-local loading.
Expired and unmatched operational overlays remain non-applicable under the
current application behavior. Suppressed findings remain excluded from
blocking gate inputs; operational suppressions keep their current error-waiver
and completion behavior. Suppression identity and timing do not change.

## 7. Fingerprint, persistence, and output invariants

- Preserve C19's unversioned finding and report fingerprint algorithms and
  values. Do not hash the Baseline object or report fingerprint into finding
  identity.
- Keep the frozen C18 report fingerprint
  `8050ab09ad677b729bc5287e99347713afc10bf0d87957066b1494442f034e26`
  unchanged.
- Do not change report JSON, schemas, CLI serialization/error mapping,
  persisted finding fingerprints, or migrations.
- Do not change eligibility, add a second scan/gate workflow, or add frontend
  baseline logic.
- Retain the legacy gate arguments and BaselineInput facade until C30. Removal
  after that boundary requires a separate compatibility decision.

Finding identity remains subject to the C19 contract: source changes and
line-dependent anchors may change fingerprints. C20 adds no broader
stability guarantee.

## 8. Stage A completion

Stage A completes only after the documentation-only PR containing this design
and the sequential TDD plan is explicitly authorized for merge, merged, and
its post-merge CI passes. Review approval or passing pre-merge CI alone does
not complete Stage A. The PR must not change Python, tests, schemas,
migrations, frontend, or `docs/consolidation/progress.md`; the C20 ledger
therefore remains `planned` throughout Stage A. Stage B requires a later
explicit user authorization. During Stage B, set C20 to `review` when the
implementation PR is ready for independent review. Set it to `accepted` only
through a separate post-implementation acceptance PR after implementation
merge and successful post-merge CI. No implementation or merge is part of
this design.
