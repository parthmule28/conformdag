# C04 — Convert Analysis into a Cohesive Package

## Role and objective

You are the Build agent for C04. Convert `src/conformdag/analysis.py` into a package with explicit models, discovery, cache, and Airflow-analysis modules while preserving all current imports and behavior. This is a mechanical ownership move; do not redesign source models.

## Required reads

- `AGENTS.md`, `docs/consolidation/architecture-rules.md`, `docs/consolidation/progress.md`, and C01.
- Full `src/conformdag/analysis.py` before editing; record its public symbols and importers.
- `src/conformdag/scan.py`, `src/conformdag/evaluator.py`, `src/conformdag/platform/runner.py`, and `tests/test_analysis.py`.
- `tests/conftest.py` and every import of `conformdag.analysis`.

## Current ownership and resulting owner

One module currently owns source models, discovery/symlink policy, parse cache, and Airflow AST extraction. After this PR, `analysis/models.py`, `analysis/discovery.py`, `analysis/cache.py`, and `analysis/airflow.py` own those responsibilities, while `analysis/__init__.py` re-exports the old public names.

## Interfaces

- Consumes: `SourceFile`, `SourceModel`, parse issue/value models, `ParseCache`, `discover_python_files()`, and `analyze_source()`.
- Produces: import-compatible `conformdag.analysis` facade plus direct module paths for later C05/dbt-family work. `analyze_source()` remains Airflow-specific and keeps its current signature.

## Expected files

- Create: `src/conformdag/analysis/__init__.py`, `models.py`, `discovery.py`, `cache.py`, and `airflow.py`.
- Remove: `src/conformdag/analysis.py` only after the package imports cleanly and the facade exports every previous public symbol.
- Modify: import sites only when necessary; retain old top-level imports where the facade supports them.
- Test: split/add `tests/analysis/test_models.py`, `test_discovery.py`, `test_cache.py`, and `test_airflow.py` without deleting current characterization coverage until the move is accepted.

## Test-first sequence

1. Inventory public symbols and add import-parity tests that compare old consumer imports with package exports.
2. Run the focused tests before the move and save the passing baseline.
3. Move code by responsibility without changing function bodies; add named default factories where strict typing requires them.
4. Add explicit regressions for recursive excludes, internal/external/broken symlinks, parse issue typing, cache corruption/atomicity, TaskFlow extraction, and dynamic values.
5. Run the new analysis tests, all scanner/evaluator tests, `mise run check`, and `mise run test:coverage`.

## Allowed changes

- File/package movement, import re-exports, test splitting, and narrowly required type annotations.
- Keep Airflow-specific helper names in `analysis/airflow.py`; dbt models are not part of this PR.

## Non-goals and prohibitions

- Do not change discovery symlink policy, AST semantics, cache format, or scan output.
- Do not introduce a generic multi-family abstraction before a second analysis family exists.
- Do not delete the facade or old tests merely because direct imports now work.

## Verification matrix

- Import-parity and focused analysis tests.
- Full non-runtime suite and 90% coverage gate.
- Pyright strict and Ruff.
- Diff review confirms no platform/CLI dependency entered analysis.

## Completion checklist and handoff

- [ ] `from conformdag.analysis import ...` remains compatible.
- [ ] New direct module paths have clear ownership.
- [ ] All symlink/cache/AST regressions remain covered.
- [ ] No dbt-specific abstraction was introduced.
- [ ] Commit with `refactor: split analysis package`; open the PR without merging.
