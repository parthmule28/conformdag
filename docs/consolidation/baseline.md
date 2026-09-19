# Consolidation Baseline

This is the measured starting point for the backlog work. Measurements were taken in the dedicated `docs/consolidation-backlog` worktree from local `main` at commit `68a837ca12209bbdb7f9308ab741051d70c16d40` on 2026-09-20. The local `main` branch was 17 commits behind `origin/main`; the backlog intentionally uses the local `main` snapshot requested for the worktree and does not fetch or merge remote history.

## Workspace and branch evidence

| Item | Value |
| --- | --- |
| Backlog branch | `docs/consolidation-backlog` |
| Backlog worktree | `/tmp/opencode/conformdag-consolidation-backlog` |
| Base branch | local `main` |
| Base commit | `68a837ca12209bbdb7f9308ab741051d70c16d40` |
| Remote refs | Retained; no remote branch was deleted |
| Pre-existing checkout changes | Preserved in the cleanup stash created before branch removal; inspect with `git stash list` in the original checkout |
| Local branches after cleanup | `main`, `docs/consolidation-backlog` |

## Verification baseline

| Measurement | Observed value | Evidence command |
| --- | ---: | --- |
| Tests collected | 410 | `mise exec -- uv run pytest --collect-only -q` |
| Default tests | 396 passed, 1 skipped, 13 deselected | `mise run check` |
| Configured coverage | 92.22% | `mise run test:coverage` |
| Python version | 3.12.14 | `mise run setup` / pytest header |
| Package version | 1.0.0b1 | `pyproject.toml` and smoke test |
| Deterministic check kinds | 12 | `src/conformdag/evaluator.py:CHECK_EVALUATORS` |
| Legacy policy aliases | 7 | `src/conformdag/evaluator.py:LEGACY_POLICY_EVALUATORS` |
| API routes | 26, including the `/api/{rest:path}` fallback | `src/conformdag/platform/app.py:create_app` |
| Wheel/sdist size | Not measured in this baseline | Run `mise run build` during C01/C38 |
| Platform image size | Not measured in this baseline | Run the container build during C39 |
| Real Postgres concurrency | Not covered by the default suite | Add the dedicated suite in C26 |

The default gate emitted one existing Starlette/httpx deprecation warning. It did not fail the gate.

## Current hotspot sizes

Measured with `wc -l` before backlog artifacts were added:

| File | Lines |
| --- | ---: |
| `src/conformdag/cli.py` | 1,011 |
| `src/conformdag/evaluator.py` | 973 |
| `src/conformdag/analysis.py` | 577 |
| `src/conformdag/models.py` | 566 |
| `src/conformdag/scan.py` | 316 |
| `src/conformdag/platform/app.py` | 770 |
| `src/conformdag/platform/db.py` | 282 |
| `src/conformdag/platform/runner.py` | 216 |
| `src/conformdag/platform/worker.py` | 209 |
| `src/conformdag/platform/packs.py` | 267 |
| `src/conformdag/semantic.py` | 359 |
| `src/conformdag/fixing/engine.py` | 515 |
| `frontend/src/api.ts` | 557 |
| `tests/test_platform.py` | 4,030 |

## Dependency surfaces

Runtime dependencies in `pyproject.toml`: `httpx`, `jinja2`, `pydantic`, `rich`, `ruamel.yaml`, and `typer`.

Platform extra: `alembic`, `fastapi`, `psycopg[binary]`, `sqlalchemy`, and `uvicorn`.

Development group: `coverage[toml]`, `pip`, `pip-audit`, `pytest`, `pytest-cov`, `pytest-mock`, and `ruff`.

## Known coverage exclusions

The configured coverage report omits `benchmark.py`, `benchmark_semantic.py`, `cli.py`, `runtime.py`, `semantic.py`, and `semantic_evaluator.py`. C35 is responsible for removing exclusions based on meaningful tests rather than replacing them with a lower gate.

## Baseline interpretation

The repository already has strong default verification and recent security remediation. The consolidation is therefore an ownership and duplication program, not a rewrite. Every structural prompt must begin with characterization and preserve the observed default gate before attempting to improve the architecture.
