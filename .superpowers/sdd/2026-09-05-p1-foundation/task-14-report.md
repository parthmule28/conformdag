# Task 14 Report: Findings and History Pagination

## Scope

- Added bounded `limit` and `offset` query parameters to scan findings and
  repository scan history.
- Added the additive `baseline_status` finding field.
- Preserved the existing null-safe `gate_passed` status projection and API
  fallback/static route registration order.

## Base and Commits

- Base before Task 14: `cef3a92` (`fix: preserve framework error propagation for request logging (B7)`)
- Implementation commit: `6af332c` (`feat: pagination on scan findings and history (F5)`)
- Evidence report commit: `713674c` (`docs: record Task 14 validation evidence`)

## API Semantics

Both paginated endpoints accept:

- `limit`: integer from 1 through 500, default 50
- `offset`: integer greater than or equal to 0, default 0

The values are applied to the ordered SQL query before materialization. Findings
retain their existing policy/file ordering; history remains newest first.

Each finding now includes `baseline_status` without removing or changing any
existing field:

- `"existing"`: the finding fingerprint occurs in the repository's configured
  baseline scan.
- `"new"`: a usable baseline exists and the fingerprint does not occur in it.
- `null`: the repository has no usable baseline. This includes an absent,
  missing, cross-repository, or non-successful baseline. `null` is intentionally
  not classified as `"existing"`.

A successful baseline remains usable when its full report artifact has been
  pruned because the platform retains normalized finding rows. The comparison
  is therefore based on same-repository normalized baseline findings.

## TDD Evidence

### Red

Added tests for findings pagination, invalid limits, history pagination,
baseline `existing`/`new` labels, and unavailable-baseline `null` semantics.

Command:

```text
mise exec -- uv run pytest tests/test_platform.py -k "paginates or bad_limit or baseline" -x --tb=short
```

Observed failure before production changes:

```text
test_findings_endpoint_paginates: AssertionError: assert 3 == 2
```

This demonstrated that the existing endpoint ignored `limit`.

### Green

The minimal implementation added FastAPI query validation, SQLAlchemy
`.limit().offset()` calls, baseline fingerprint lookup, and the additive
payload field.

Focused result after implementation and formatting:

```text
8 passed, 57 deselected, 1 warning in 14.28s
```

## Validation

Commands run after implementation:

```text
mise exec -- uv run pytest tests/test_platform.py
65 passed, 1 warning in 26.68s

mise exec -- uv run ruff check src/conformdag/platform/app.py tests/test_platform.py
All checks passed!

mise exec -- uv run ruff format --check src/conformdag/platform/app.py tests/test_platform.py
2 files already formatted

mise exec -- uv run pyright src/conformdag/platform/app.py tests/test_platform.py
0 errors, 0 warnings, 0 informations
```

The only warning is the pre-existing Starlette deprecation warning about its
`httpx` TestClient compatibility layer.

## Changed Files

- `src/conformdag/platform/app.py`
- `tests/test_platform.py`
- `.superpowers/sdd/2026-09-05-p1-foundation/task-14-report.md`
