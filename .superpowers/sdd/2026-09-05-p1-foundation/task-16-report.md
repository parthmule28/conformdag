# Task 16 Report: TaskFlow DAG Matching Inside `with DAG(...)`

## Scope

- Added scoped tracking for enclosing `with DAG(...) as <name>:` contexts in
  the source analyzer.
- Assigned the enclosing DAG variable name to TaskFlow-decorated tasks.
- Updated the existing TaskFlow fixture assertion from the obsolete `None`
  expectation to the enclosing `"dag"` name.

## Base and Commits

- Base before Task 16: `6284655` (`docs: identify task report commits`)
- Implementation commit: `62865f8` (`fix: TaskFlow tasks inside with DAG(...) resolve their dag_name (B11)`)
- Evidence report commit: follows this report.

## Analysis Semantics

`_ModelVisitor` maintains `_with_dag_stack` while visiting `with` statements.
`DAG` context expressions are identified with the existing `_qualified_name`
resolution pattern. A named `as <name>` binding is pushed for the context body
and removed afterward, so nested DAG contexts resolve to the innermost name and
TaskFlow functions outside a DAG context continue to receive `dag_name=None`.

## TDD Evidence

### Red

Added `test_taskflow_task_inside_with_dag_gets_dag_name` before changing the
production analyzer.

Command:

```text
mise exec -- uv run pytest tests/test_analysis.py::test_taskflow_task_inside_with_dag_gets_dag_name -x --tb=short
```

Observed failure before production changes:

```text
AssertionError: assert None == 'dag'
```

The failure demonstrated that the existing TaskFlow record did not retain its
enclosing `with DAG(...) as dag:` binding.

### Green

The minimal implementation added the DAG context stack and used its current
entry when constructing TaskFlow `TaskRecord` values.

Focused result:

```text
1 passed in 0.11s
```

The analysis and check-pack test modules then passed together:

```text
15 passed in 1.55s
```

## Final Validation

`mise run check` completed successfully:

```text
format-check: 118 files already formatted
lint: All checks passed!
typecheck: 0 errors, 0 warnings, 0 informations
test: 252 passed, 13 deselected, 1 warning
validate:packs: both policy packs valid
```

`mise run test:coverage` completed successfully:

```text
252 passed, 13 deselected, 1 warning in 284.91s
Required test coverage of 90% reached. Total coverage: 90.98%
```

The only warning is the pre-existing Starlette deprecation warning about its
`httpx` TestClient compatibility layer.

## Changed Files

- `src/conformdag/analysis.py`
- `tests/test_analysis.py`
- `tests/test_check_pack.py`
- `.superpowers/sdd/2026-09-05-p1-foundation/task-16-report.md`

## Round 1 Fix Evidence

### Findings Addressed

- `visit_With` now assigns each visited DAG context's alias to its matching
  `DagRecord.variable_name`, allowing `_dag_defaults` to match TaskFlow
  `dag_name` values and inherit `default_args`.
- The context stack preserves `None` for unnamed `with DAG(...):` statements
  instead of converting it to an empty string.

Round 1 implementation commit: `1f5db38` (`fix: preserve TaskFlow DAG context defaults (B11)`).

### TDD Evidence

#### Red

Added an evaluator-level regression for TaskFlow retry inheritance from
`default_args`, plus a regression for unnamed DAG context names.

Commands:

```text
mise exec -- uv run pytest tests/test_check_pack.py::test_taskflow_tasks_inherit_with_dag_default_args tests/test_analysis.py::test_taskflow_task_inside_unnamed_with_dag_has_no_dag_name -x --tb=short
```

The default-args test failed because the effective retry status was `PASS`
instead of `FAIL`; the unnamed-context test failed because `dag_name` was `""`
instead of `None`.

#### Green

The two regression tests passed after the visitor fix:

```text
2 passed in 0.93s
```

The complete analysis and check-pack modules passed:

```text
17 passed in 1.41s
```

### Round 1 Validation

`mise run check` completed successfully:

```text
format-check: 118 files already formatted
lint: All checks passed!
typecheck: 0 errors, 0 warnings, 0 informations
test: 254 passed, 13 deselected, 1 warning
validate:packs: both policy packs valid
```

`mise run test:coverage` completed successfully:

```text
254 passed, 13 deselected, 1 warning in 242.44s
Required test coverage of 90% reached. Total coverage: 90.96%
```

The only warning remains the pre-existing Starlette deprecation warning about
its `httpx` TestClient compatibility layer.
