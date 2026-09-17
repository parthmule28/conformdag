# Task 17 Report: Span-Application Hardening in the Fix Engine

## Scope

- Added exact `EditSpan` deduplication before patch application, including the
  optional timedelta import span.
- Converted `apply_spans` `ValueError` failures into per-file residuals with
  the affected policy IDs, fix kinds, iteration, and reason.
- Preserved the existing verify-by-rescan loop: only generated candidates are
  rescanned, and unresolved findings remain residuals.
- Added regressions for overlapping spans and duplicate spans.

## Base and Commits

- Base before Task 17: `0232286` (`docs: record Task 16 round 1 validation evidence`)
- Implementation commit: `6015791` (`fix: fix engine treats overlapping spans as residuals instead of crashing (B12)`)
- Evidence report commit: follows this report.

## TDD Evidence

### Red

Added `test_patch_candidates_converts_overlapping_spans_into_residuals` and
`test_patch_candidates_deduplicates_identical_spans` before changing the fix
engine.

Command:

```text
mise exec -- uv run pytest tests/test_fixing.py -k "patch_candidates" -x --tb=short
```

Observed failure before production changes:

```text
ValueError: overlapping edit spans
```

The failure demonstrated that `_patch_candidates` allowed the `ValueError`
from `apply_spans` to escape instead of returning a residual.

### Green

The minimal implementation added `ResidualFailure.reason`, removed duplicate
spans before application, and caught the application `ValueError` as a
residual.

Focused result:

```text
2 passed, 32 deselected in 0.40s
```

The complete fixing and roundtrip modules then passed:

```text
tests/test_fixing.py: 34 passed in 1.79s
tests/test_roundtrip.py: 1 passed in 11.81s
```

## Final Validation

`mise run check` completed successfully:

```text
format-check: 118 files already formatted
lint: All checks passed!
typecheck: 0 errors, 0 warnings, 0 informations
test: 256 passed, 13 deselected, 1 warning
validate:packs: both policy packs valid
```

`mise run test:coverage` completed successfully:

```text
256 passed, 13 deselected, 1 warning in 73.61s
Required test coverage of 90% reached. Total coverage: 90.97%
```

The only warning is the pre-existing Starlette deprecation warning about its
`httpx` TestClient compatibility layer.

## Changed Files

- `src/conformdag/fixing/engine.py`
- `tests/test_fixing.py`
- `.superpowers/sdd/2026-09-05-p1-foundation/task-17-report.md`

The pre-existing untracked `opencode.json` was not modified or staged.
