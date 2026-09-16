# Task 15 Report: Configurable CORS Middleware

## Scope

- Added configurable CORS origins to `PlatformSettings`.
- Added comma-separated environment parsing through
  `CONFORMDAG_PLATFORM_CORS_ORIGINS`.
- Added FastAPI `CORSMiddleware` with credentials, all methods, and all
  headers enabled as specified.
- Preserved the localhost SPA default and existing API fallback/static route
  registration order.

## Base and Commits

- Base before Task 15: `713674c` (`docs: record Task 14 validation evidence`)
- Implementation commit: `e187729` (`feat: configurable CORS origins (B14)`)
- Report commit: follows this report.

## API and Configuration Semantics

`PlatformSettings.cors_origins` defaults to:

```text
["http://localhost:5173"]
```

`CONFORMDAG_PLATFORM_CORS_ORIGINS` is split on commas, whitespace is trimmed,
and empty entries are discarded. The resulting list is passed to
`CORSMiddleware` with:

- `allow_credentials=True`
- `allow_methods=["*"]`
- `allow_headers=["*"]`

Same-origin SPA requests remain the default deployment path; CORS only adds
cross-origin support for explicitly configured origins. Unknown origins do not
receive an `access-control-allow-origin` response header. API fallback and
static dashboard registration remain after all specific API routes.

## TDD Evidence

### Red

Added tests for an allowed localhost preflight, an unknown-origin rejection,
and comma-separated environment parsing.

Command:

```text
mise exec -- uv run pytest tests/test_platform.py -k cors -x --tb=short
```

Observed failure before production changes:

```text
test_cors_preflight_allows_configured_origin: assert 405 == 200
```

The failure demonstrated that the existing app had no preflight middleware.

### Green

The minimal implementation added the settings field/parser and middleware
configuration without changing route registration.

Focused result:

```text
3 passed, 65 deselected, 1 warning in 2.87s
```

The full platform module then passed:

```text
68 passed, 1 warning in 25.30s
```

## Final Validation

`mise run check` completed successfully:

```text
format-check: 118 files already formatted
lint: All checks passed!
typecheck: 0 errors, 0 warnings, 0 informations
test: 251 passed, 13 deselected, 1 warning in 80.29s
validate:packs: both policy packs valid
```

`mise run test:coverage` completed successfully on the retry with an adequate
timeout:

```text
251 passed, 13 deselected, 1 warning in 199.50s
Required test coverage of 90% reached. Total coverage: 90.90%
```

The initial 120-second tool invocation timed out during the roundtrip suite
without a test failure or coverage result. The retry completed in 199.50s. The
generated root `.coverage` artifact was removed only after the coverage run.

The only test warning is the pre-existing Starlette deprecation warning about
its `httpx` TestClient compatibility layer.

## Changed Files

- `src/conformdag/platform/app.py`
- `tests/test_platform.py`
- `.superpowers/sdd/2026-09-05-p1-foundation/task-15-report.md`
