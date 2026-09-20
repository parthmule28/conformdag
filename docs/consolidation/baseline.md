# Consolidation Baseline

This is the authoritative measured starting point for the consolidation
program. Measurements were taken on 2026-09-20 from `origin/main` at commit
`c20b9a19e2d422e0b3743e85548b5fa5cf3df1ad`, before the C01 documentation
commit. The source tree was not changed by the bootstrap backlog commit or by
C01.

## Source and verification baseline

| Measurement | Observed value | Evidence command or source |
| --- | ---: | --- |
| Base ref | `origin/main @ c20b9a19e2d422e0b3743e85548b5fa5cf3df1ad` | `git rev-parse origin/main` |
| Python version | 3.12.14 | `mise run setup` / pytest header |
| Package version | 1.0.0b1 | `pyproject.toml` and smoke test |
| Tests collected | 522 | `mise exec -- uv run pytest --collect-only -q` |
| Default tests | 501 passed, 2 skipped, 19 deselected | `mise run check` |
| Configured coverage | 90.64% | `mise run test:coverage` |
| Deterministic check kinds | 12 | `src/conformdag/evaluator.py:CHECK_EVALUATORS` |
| Legacy policy aliases | 7 | `src/conformdag/evaluator.py:LEGACY_POLICY_EVALUATORS` |
| API route registrations | 27, including `/api` and `/api/{rest:path}` fallbacks | `src/conformdag/platform/app.py:create_app` |
| Dependency inventory | Passed | `mise run check` / `scripts/verify_dependency_inventory.py` |
| Wheel/sdist size | Not measured in this baseline | Run `mise run build` during C38 |
| Platform image size | Not measured in this baseline | Run the container build during C39 |
| Real Postgres concurrency | Not covered by the default suite | Add the dedicated suite in C26 |

The default gate and coverage gate each emitted one existing Starlette/httpx
deprecation warning. Neither warning failed its command.

## Current hotspot sizes

Measured with `wc -l` against the source tree at the base ref:

| File | Lines |
| --- | ---: |
| `src/conformdag/cli.py` | 1,016 |
| `src/conformdag/evaluator.py` | 1,071 |
| `src/conformdag/analysis.py` | 823 |
| `src/conformdag/models.py` | 566 |
| `src/conformdag/scan.py` | 304 |
| `src/conformdag/platform/app.py` | 827 |
| `src/conformdag/platform/db.py` | 387 |
| `src/conformdag/platform/runner.py` | 232 |
| `src/conformdag/platform/worker.py` | 262 |
| `src/conformdag/platform/packs.py` | 272 |
| `src/conformdag/platform/demo.py` | 453 |
| `src/conformdag/semantic.py` | 439 |
| `src/conformdag/fixing/engine.py` | 515 |
| `frontend/src/api.ts` | 558 |
| `tests/test_platform.py` | 4,799 |

## Dependency surfaces

Runtime dependencies in `pyproject.toml`: `httpx>=0.28,<1`, `jinja2>=3.1,<4`,
`pydantic>=2.11,<3`, `rich>=14,<15`, `ruamel.yaml>=0.18,<1`, and
`typer>=0.16,<1`.

Platform extra: `alembic>=1.16,<2`, `fastapi>=0.128,<1`,
`psycopg[binary]>=3.2,<4`, `sqlalchemy>=2.0,<3`, and `uvicorn>=0.40,<1`.

Development group: `coverage[toml]>=7.9,<8`, `pip>=26.2,<27`,
`pip-audit>=2.9,<3`, `pytest>=9.0.3,<10`, `pytest-cov>=6,<7`,
`pytest-mock>=3.14,<4`, and `ruff>=0.12,<1`.

## Known coverage exclusions

The configured coverage report omits `benchmark.py`, `benchmark_semantic.py`,
`cli.py`, `runtime.py`, `semantic.py`, and `semantic_evaluator.py`. C35 is
responsible for removing exclusions based on meaningful tests rather than
replacing them with a lower gate.

## Baseline interpretation

The current tree has stronger verification breadth than the earlier backlog
snapshot, but coverage is lower because the source and test surfaces have
expanded. The consolidation is an ownership and duplication program, not a
rewrite. Every structural prompt must begin with characterization and preserve
the observed current-tree gate before attempting to improve the architecture.
