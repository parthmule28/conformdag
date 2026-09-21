# C04 Analysis Package Design

**Status:** approved
**Slice:** C04 — Convert Analysis into a Cohesive Package
**Date:** 2026-09-21

## Purpose

C04 converts the monolithic `src/conformdag/analysis.py` module into a small
`conformdag.analysis` package. The change is an ownership move: source models,
repository discovery, the parse cache, and Airflow-specific AST extraction get
explicit module owners while existing callers continue importing from the
`conformdag.analysis` facade.

The package boundary is intentionally Airflow-specific for this slice. It
creates direct module paths that a later evaluator-family or dbt slice can use,
but it does not introduce a generic multi-family analysis abstraction.

## Goals

- Create `analysis/models.py`, `analysis/discovery.py`, `analysis/cache.py`,
  `analysis/airflow.py`, and a compatibility-preserving `analysis/__init__.py`.
- Keep every existing public `conformdag.analysis` import valid and preserve
  object identity between facade exports and their owning modules.
- Preserve the exact public signatures and result shapes of
  `discover_python_files()`, `analyze_source()`, `datetime_parts()`,
  `iter_module_scope_calls()`, and `ParseCache`.
- Preserve recursive exclude matching, default excludes, symlink containment
  and issue classification, source hashing, AST-only analysis, dynamic-value
  handling, and cache corruption/atomic-write behavior.
- Keep all existing consumer imports on the facade unless a direct import is
  technically required by the package split.
- Add direct-module tests without deleting the existing characterization suite.

## Non-goals

- No redesign of `SourceFile`, `SourceModel`, parse issue, DAG, task, or value
  records.
- No change to discovery symlink policy, include/exclude semantics, source
  hashing, AST visitor semantics, cache key/entry behavior, or scan output.
- No new scan path and no changes to `scan_repository()` orchestration.
- No dbt models, generic analysis-family interface, evaluator modularization,
  platform DTOs, or CLI changes.
- No migration of existing callers away from `conformdag.analysis` merely to
  demonstrate the new package.

## Ownership map

The following are the only implementation owners after the move:

| Owner | Symbols and responsibility |
| --- | --- |
| `analysis/models.py` | `ParseIssueCode`, `ValueState`, `SourceFile`, `ParseIssue`, `StaticValue`, `ImportRecord`, `CallRecord`, `DagRecord`, `TaskRecord`, `ConstantAssignment`, `SecretAssignment`, `SourceModel`, `secret_like`, and their named default factories |
| `analysis/discovery.py` | `DEFAULT_EXCLUDES`, `NON_FATAL_DISCOVERY_ISSUES`, path normalization/glob matching, symlink inspection/issue recording, and `discover_python_files()` |
| `analysis/cache.py` | `ParseCache`, including its pickle validation, atomic replacement, prune cadence, and failure handling |
| `analysis/airflow.py` | Airflow-specific `_ModelVisitor`, AST/value helpers, `_UNRESOLVED_VALUE`, `datetime_parts()`, `analyze_source()`, and `iter_module_scope_calls()` |
| `analysis/__init__.py` | Public facade and `__all__`; it imports and re-exports the public names above but owns no analysis logic |

The dependency direction is one-way:

```text
models   <- discovery
models   <- cache
models + cache <- airflow
models + discovery + cache + airflow <- __init__ facade
```

`models.py` imports no sibling analysis module. `discovery.py` and `cache.py`
may consume model types. `airflow.py` may consume model types and `ParseCache`.
The facade is imported by existing consumers such as `scan.py`, `evaluator.py`,
the fixing engine, the benchmark module, and the platform runner; those
consumers must not become dependencies of the analysis package.

## Public compatibility contract

The facade will expose this complete public symbol set, with each value being
the same object exported by its owner:

```python
PUBLIC_FACADE_NAMES = (
    "DEFAULT_EXCLUDES",
    "ParseIssueCode",
    "ValueState",
    "NON_FATAL_DISCOVERY_ISSUES",
    "SourceFile",
    "ParseIssue",
    "StaticValue",
    "ImportRecord",
    "CallRecord",
    "DagRecord",
    "TaskRecord",
    "ConstantAssignment",
    "SecretAssignment",
    "secret_like",
    "SourceModel",
    "matches_exclude",
    "discover_python_files",
    "datetime_parts",
    "analyze_source",
    "ParseCache",
    "iter_module_scope_calls",
)
```

The direct ownership paths are:

- `conformdag.analysis.models` for the model/enumeration/secret-name entries.
- `conformdag.analysis.discovery` for default excludes, non-fatal discovery
  issues, matching, and file discovery.
- `conformdag.analysis.cache` for `ParseCache`.
- `conformdag.analysis.airflow` for AST analysis and date/module-call helpers.

The existing signatures remain unchanged:

```python
def discover_python_files(
    repository_root: Path,
    include: list[str],
    exclude: list[str] | None = None,
    follow_internal_symlinks: bool = False,
) -> tuple[list[SourceFile], list[ParseIssue]]: ...

def analyze_source(
    source: SourceFile,
    cache: ParseCache | None = None,
) -> tuple[SourceModel | None, ParseIssue | None]: ...

def datetime_parts(node: ast.AST) -> tuple[tuple[int, int, int] | None, bool | None]: ...

def iter_module_scope_calls(model: SourceModel) -> Iterator[CallRecord]: ...
```

Private visitor and helper names remain private to their owning modules. They
are not added to the facade or treated as a new compatibility surface.

## Cache compatibility

The cache remains a trusted local pickle directory keyed by the source content
hash. `ParseCache.get()` and `.put()` retain their current validation,
atomic-write, prune, and error-handling bodies.

The facade re-exports all model classes under their historical
`conformdag.analysis` names. This keeps existing cache entries whose pickle
globals point at the old module importable after `analysis.py` becomes a
package. A regression test will write a legacy-path pickle for a `SourceModel`
and verify that the new `ParseCache` loads it as the current model class.

## Test strategy

The existing `tests/test_analysis.py` remains in place as characterization
coverage. New `tests/analysis/` tests will exercise the ownership paths:

- `test_models.py`: facade-to-owner identity and complete public export parity.
- `test_discovery.py`: direct discovery imports plus recursive excludes and
  internal/external/broken symlink issue behavior.
- `test_cache.py`: direct cache imports plus empty/corrupt entries, legacy
  pickle loading, atomic replacement failure, and racing prune entries.
- `test_airflow.py`: direct AST imports plus non-execution, TaskFlow context,
  unresolved dynamic values, date extraction, and module-scope call filtering.

The tests are added before production extraction so direct-module imports fail
against the current monolith. After extraction, focused analysis tests,
scanner/evaluator tests, the full non-runtime suite, strict type checking,
format/lint checks, and the 90% coverage gate must all pass.

## Acceptance criteria

C04 is complete when:

1. `src/conformdag/analysis.py` is gone and the five expected package files
   exist with the ownership map above.
2. Every current `from conformdag.analysis import ...` consumer import remains
   valid, and facade names are identical to direct owner exports.
3. The direct discovery, cache, and Airflow tests cover the specified edge
   cases while `tests/test_analysis.py` remains present and green.
4. No source, scan, finding, report, cache, policy, or CLI behavior changes in
   the focused and full test suites.
5. `mise run check`, `mise run test:coverage`, `mise run schema --check`, and
   `git diff --check` pass; no platform or CLI dependency enters analysis.
