# Task 19 Report: DX Commands

## Scope

- Added `conformdag policy hash <document>` with UTF-8 SHA-256 output.
- Added `conformdag policy new <id> --kind <kind> [--document PATH]` with explicit valid configuration templates for every registered check kind.
- Added document-derived provenance sections and content hashes; no fixed section name is assumed.
- Added the required Ruff AIR scaffold rules: `AIR001`, `AIR002`, `AIR301`, `AIR302`, `AIR311`, and `AIR312`.
- Extended `init` with a commented `conformdag-workspace.yaml` scaffold.
- Added `doctor` checks for config, pack, registry, provenance, quality gates, Docker, and platform DSN reachability.
- Added `baseline set <scan-id>` using the existing DSN-backed platform session and admin-token mutation guard.

## Base and Commit

- Base before Task 19: `b214907` (`docs: record Task 17 validation evidence`)
- Implementation commit: the Task 19 conventional commit containing the implementation, tests, and this report.
- The pre-existing untracked `opencode.json` was not modified or staged.

## TDD Evidence

### Red

Added focused tests for policy hashing, unknown kinds, every registered policy kind,
provenance validation, Ruff rules, workspace scaffolding, doctor diagnostics, DSN
reachability, and baseline persistence before the implementation.

Command:

```text
mise exec -- uv run pytest tests/test_cli.py -k "policy_hash or policy_new or workspace_scaffold or doctor_reports" -x --tb=short
```

Observed failure:

```text
test_policy_hash_prints_sha256_of_document: assert 2 == 0
```

The failure was the expected missing-command failure for `policy hash`.

### Green

Focused command:

```text
6 passed, 25 deselected
```

Baseline and configured-DSN doctor tests:

```text
2 passed, 29 deselected
```

Full CLI suite:

```text
31 passed
```

## Final Validation

`mise run check` passed:

```text
format-check: 118 files already formatted
lint: All checks passed!
typecheck: 0 errors, 0 warnings, 0 informations
test: 264 passed, 13 deselected, 1 warning
validate:packs: both policy packs valid
```

`mise run test:coverage` passed:

```text
264 passed, 13 deselected
Required test coverage of 90% reached. Total coverage: 90.97%
```

The only warning is the pre-existing Starlette/httpx TestClient deprecation warning.

The real repository pack also passed `conformdag doctor`: config, pack, registry,
provenance, gates, and Docker were healthy; an unset platform DSN was reported as a
warning without changing the exit code.

## Deviations and Notes

- Policy errors use the existing `_fail` diagnostic path and therefore go to stderr,
  matching the CLI's established error-routing convention.
- An absent project config is a doctor failure because the doctor contract checks config
  presence; an absent optional platform DSN is only a warning.
- The baseline CLI uses the existing local platform DSN/session configuration because
  the repository has no platform URL configuration; it still requires the same admin
  token presence used to enable platform mutations.

## Changed Files

- `src/conformdag/cli.py`
- `tests/test_cli.py`
- `.superpowers/sdd/2026-09-05-p1-foundation/task-19-report.md`
