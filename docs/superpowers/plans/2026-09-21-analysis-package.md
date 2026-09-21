# Analysis Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native, single-session implementation of this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic Airflow source-analysis module into explicit models, discovery, cache, and Airflow-analysis modules while preserving the complete `conformdag.analysis` import facade and behavior.

**Architecture:** Move existing code mechanically into four owner modules with one-way dependencies: models at the base, discovery and cache above it, and Airflow AST analysis above both. Keep `analysis/__init__.py` as a pure re-export facade so `scan.py`, `evaluator.py`, fixing, benchmarking, the platform runner, and existing tests need no behavioral import migration.

**Tech Stack:** Python 3.12, `ast`, `pickle`, `pathlib`, pytest, Pyright strict mode, Ruff, and the existing `mise`/`uv` workflow.

**Spec:** `docs/superpowers/specs/2026-09-21-analysis-package-design.md`

## Global Constraints

- Preserve the one scan engine: `src/conformdag/scan.py:scan_repository()` remains the canonical core evaluation primitive.
- Keep `analyze_source()` Airflow-specific with its current signature; do not introduce a generic analysis-family abstraction.
- Do not change discovery symlink policy, recursive glob semantics, content hashing, AST semantics, cache format/behavior, or scan output.
- Keep every existing `from conformdag.analysis import ...` import valid and keep facade exports identical to direct owner exports.
- Keep the existing model shapes and named dataclass default factories; do not redesign source models.
- Keep analysis independent of CLI, platform, evaluator, fixing, semantic, and dbt modules.
- Do not use broad `# type: ignore` comments; satisfy Pyright strict mode with typed imports and targeted narrowing.
- Run the repository setup-aware commands through `mise`; the default gate is `mise run check` and coverage is `mise run test:coverage`.

## Review Focus

- **Facade compatibility:** all 21 public names and all existing consumer imports resolve to the same objects as their direct owner modules; pin this in `tests/analysis/test_models.py`.
- **Package/file transition:** the new package must import cleanly without a stale `analysis.py`, and the facade must not create sibling import cycles; pin package import and owner identity in `test_models.py`.
- **Discovery containment:** nested excludes and internal/external/broken symlinks retain their exact selected-file set and issue codes; pin direct `discovery.py` behavior in `test_discovery.py`.
- **Cache persistence:** empty/corrupt entries remain misses, failed atomic replacement preserves the last good entry, prune tolerates a racing deletion, new writes retain historical `conformdag.analysis.*` globals, and old entries remain loadable; pin each in `test_cache.py`.
- **AST safety and semantics:** no repository code executes, TaskFlow context and unresolved values remain unchanged, and module-scope calls/date extraction retain their existing results; pin direct `airflow.py` behavior in `test_airflow.py`.

---

## File Structure

- **Create:** `src/conformdag/analysis/__init__.py` — facade and `__all__` only.
- **Create:** `src/conformdag/analysis/models.py` — enums, immutable/mutable source records, default factories, and `secret_like()`.
- **Create:** `src/conformdag/analysis/discovery.py` — default excludes, discovery issue set, glob matching, symlink policy, and `discover_python_files()`.
- **Create:** `src/conformdag/analysis/cache.py` — `ParseCache` with its current pickle/atomic-write/prune behavior.
- **Create:** `src/conformdag/analysis/airflow.py` — `_ModelVisitor`, AST/value helpers, `datetime_parts()`, `analyze_source()`, and `iter_module_scope_calls()`.
- **Delete:** `src/conformdag/analysis.py` only after the package imports and the facade tests pass.
- **Create:** `tests/analysis/__init__.py`, `tests/analysis/test_models.py`, `test_discovery.py`, `test_cache.py`, and `test_airflow.py`.
- **Retain unchanged:** existing consumer imports in `src/conformdag/benchmark.py`, `scan.py`, `evaluator.py`, `fixing/engine.py`, `platform/runner.py`, and current test modules; retain `tests/test_analysis.py` as characterization coverage.
- **Modify at completion:** `docs/consolidation/progress.md` for the merged C03 acceptance correction and C04 evidence only; no implementation or generated schema files.

---

### Task 1: Add Direct-Module and Facade Contract Tests

**Files:**
- Create: `tests/analysis/__init__.py`
- Create: `tests/analysis/test_models.py`
- Create: `tests/analysis/test_discovery.py`
- Create: `tests/analysis/test_cache.py`
- Create: `tests/analysis/test_airflow.py`
- Reference without deleting: `tests/test_analysis.py`

**Interfaces:**
- Consumes the current public names and behavior in `src/conformdag/analysis.py`.
- Produces failing tests that define the direct owner modules, facade identity, and the C04 edge-case contract.

- [ ] **Step 1: Add the facade/owner identity test.**

  In `test_models.py`, define the complete owner map from the approved spec and assert that every facade value is the same object as the direct owner value:

  ```python
  import conformdag.analysis as facade
  from conformdag.analysis import airflow, cache, discovery, models

  OWNERS = {
      "DEFAULT_EXCLUDES": discovery,
      "ParseIssueCode": models,
      "ValueState": models,
      "NON_FATAL_DISCOVERY_ISSUES": discovery,
      "SourceFile": models,
      "ParseIssue": models,
      "StaticValue": models,
      "ImportRecord": models,
      "CallRecord": models,
      "DagRecord": models,
      "TaskRecord": models,
      "ConstantAssignment": models,
      "SecretAssignment": models,
      "secret_like": models,
      "SourceModel": models,
      "matches_exclude": discovery,
      "discover_python_files": discovery,
      "datetime_parts": airflow,
      "analyze_source": airflow,
      "ParseCache": cache,
      "iter_module_scope_calls": airflow,
  }

  def test_facade_exports_direct_owner_objects() -> None:
      assert tuple(facade.__all__) == tuple(OWNERS)
      for name, owner in OWNERS.items():
          assert getattr(facade, name) is getattr(owner, name)
  ```

- [ ] **Step 2: Add direct discovery regressions.**

  In `test_discovery.py`, import `DEFAULT_EXCLUDES`, `discover_python_files`,
  and `matches_exclude` from `conformdag.analysis.discovery`, and import
  `ParseIssueCode` from `conformdag.analysis.models`. Reuse the current temporary-repository
  shapes from `tests/test_analysis.py` and assert that nested paths such as
  `src/a/.venv/x.py` match the default exclude while `src/a/.venv-copy/x.py`
  does not. Add internal, external, directory, chained, and broken symlinks;
  assert the selected files and exact `ParseIssueCode` values remain the same
  as the existing characterization test.

- [ ] **Step 3: Add direct cache regressions.**

  In `test_cache.py`, import `ParseCache` from `conformdag.analysis.cache` and
  `SourceFile`/`analyze_source` from their direct owners. Pin these behaviors:

  ```python
  def test_empty_entry_is_a_miss(tmp_path: Path) -> None:
      cache = ParseCache(tmp_path / "cache")
      cache.directory.mkdir()
      (cache.directory / "abc.pkl").write_bytes(b"")
      assert cache.get("abc") is None
  ```

  Also retain the existing failed-`Path.replace`, racing-prune, and corrupt
  pickle cases. Add a post-C04 serialization assertion: after `cache.put()`,
  decode the pickle opcodes with `pickletools.genops()` and assert that the
  string globals contain `"conformdag.analysis"` but not
  `"conformdag.analysis.models"`. This proves newly written entries retain the
  historical module path rather than merely proving that the facade can read
  old data. For legacy compatibility, temporarily set the
  `__module__` values of `ParseIssueCode`, `ValueState`, `SourceFile`,
  `ParseIssue`, `StaticValue`, `ImportRecord`, `CallRecord`, `DagRecord`,
  `TaskRecord`, `ConstantAssignment`, `SecretAssignment`, and `SourceModel`
  to `"conformdag.analysis"` while serializing a model, restore them in
  `finally`, write that payload to `<hash>.pkl`, and assert `ParseCache.get()`
  returns a `SourceModel` with the original source. This simulates cache
  entries written before the module became a package.

- [ ] **Step 4: Add direct Airflow-analysis regressions.**

  In `test_airflow.py`, import `SourceFile`/`SourceModel` from `models.py` and
  `analyze_source`, `datetime_parts`, and `iter_module_scope_calls` from
  `airflow.py`. Pin a TaskFlow function inside a named `with DAG(...)` block to
  its DAG name, retain unresolved keyword tracking for unknown names, extract
  timezone-aware date calls, and return only module-scope calls. Include a
  top-level call whose function would perform network I/O if executed and
  assert the analysis completes without performing that I/O.

- [ ] **Step 5: Run the contract tests in the expected red state.**

  Run:

  ```bash
  mise exec -- uv run pytest tests/analysis -x --tb=short
  ```

  Expected: collection fails because `conformdag.analysis` is currently a
  single module and has no `models`, `discovery`, `cache`, or `airflow`
  submodule. Do not weaken the tests to make the monolith pass.

- [ ] **Step 6: Commit the failing contract tests.**

  ```bash
  git add tests/analysis
  git commit -m "test: define analysis package contract"
  ```

### Task 2: Extract Models, Discovery, Cache, and Airflow Modules

**Files:**
- Create: `src/conformdag/analysis/__init__.py`
- Create: `src/conformdag/analysis/models.py`
- Create: `src/conformdag/analysis/discovery.py`
- Create: `src/conformdag/analysis/cache.py`
- Create: `src/conformdag/analysis/airflow.py`
- Delete: `src/conformdag/analysis.py`
- Test: `tests/analysis/` and existing `tests/test_analysis.py`

**Interfaces:**
- Consumes the exact monolith bodies and the direct-module tests from Task 1.
- Produces the four owner modules and a facade that exports the 21-name public contract with unchanged signatures.

- [ ] **Step 1: Move the model definitions without changing their bodies.**

  Create `models.py` with the existing future-annotations/import header and
  move `ParseIssueCode`, `ValueState`, `SourceFile`, `ParseIssue`,
  `StaticValue`, `ImportRecord`, `CallRecord`, `DagRecord`, `TaskRecord`,
  `ConstantAssignment`, `SecretAssignment`, `SourceModel`, `secret_like`, and
  all named default factories. Keep dataclass mutability/frozenness, field
  order, defaults, enum values, and type annotations exactly as they are.
  Do not move `DEFAULT_EXCLUDES` or discovery issue sets into this module.
  After those definitions, retain the historical pickle globals for every
  class in the cached `SourceModel` graph while keeping the physical owner in
  `models.py`:

  ```python
  for _cache_model in (
      ParseIssueCode, ValueState, SourceFile, ParseIssue, StaticValue,
      ImportRecord, CallRecord, DagRecord, TaskRecord, ConstantAssignment,
      SecretAssignment, SourceModel,
  ):
      _cache_model.__module__ = "conformdag.analysis"
  del _cache_model
  ```

  The facade must expose each class before cache operations serialize it. This
  metadata is a compatibility mechanism, not a second model implementation.

- [ ] **Step 2: Move discovery ownership and imports.**

  Create `discovery.py` with `DEFAULT_EXCLUDES`,
  `NON_FATAL_DISCOVERY_ISSUES`, `_normalize_relative_path`, `_exclude_regex`,
  `matches_exclude`, `_contains_symlink`, `_append_discovery_issue`, and
  `discover_python_files`. Import `ParseIssue`, `ParseIssueCode`, and
  `SourceFile` from `.models`; preserve all existing `Path.resolve`, glob,
  containment, issue de-duplication, file ordering, UTF-8 read, and SHA-256
  logic.

- [ ] **Step 3: Move cache ownership and imports.**

  Create `cache.py` with the existing `ParseCache` class and its `os`,
  `pickle`, `tempfile`, `suppress`, and `Path` imports. Import `SourceModel`
  from `.models`. Keep pickle validation, `NamedTemporaryFile`/`fsync`, atomic
  `Path.replace`, cleanup, 500-write prune cadence, and specific `OSError`
  handling unchanged.

- [ ] **Step 4: Move Airflow AST ownership and add sibling imports.**

  Create `airflow.py` with `_qualified_name`, `_ModelVisitor`,
  `_literal_value`, `_UNRESOLVED_VALUE`, `datetime_parts`, `analyze_source`,
  and `iter_module_scope_calls`. Import `ParseCache` from `.cache` and the
  required records/helpers from `.models`. Preserve visitor ordering,
  `_function_depth`, `_with_dag_stack`, dynamic-value sentinel identity,
  `ast.parse` error construction, cache hit source replacement, and all AST
  result fields exactly.

- [ ] **Step 5: Add the pure re-export facade.**

  `analysis/__init__.py` must contain no analysis logic. Import the public
  names from the four siblings and declare the exact ordered export list:

  ```python
  __all__ = [
      "DEFAULT_EXCLUDES", "ParseIssueCode", "ValueState", "NON_FATAL_DISCOVERY_ISSUES",
      "SourceFile", "ParseIssue", "StaticValue", "ImportRecord", "CallRecord",
      "DagRecord", "TaskRecord", "ConstantAssignment", "SecretAssignment", "secret_like",
      "SourceModel", "matches_exclude", "discover_python_files", "datetime_parts",
      "analyze_source", "ParseCache", "iter_module_scope_calls",
  ]
  ```

  Ensure each name is imported from its owner rather than redefined in the
  facade. This makes old imports and legacy pickle globals resolve to the
  current class objects.

- [ ] **Step 6: Remove the monolith only after package imports are clean.**

  First run the facade import probe and focused tests. Once they import the
  package and pass, delete `src/conformdag/analysis.py`; do not leave a second
  implementation or compatibility copy in the final tree. Verify that the
  importers found in the C04 inventory still use the facade and that no source
  file imports a private module accidentally.

- [ ] **Step 7: Run focused green verification.**

  Run:

  ```bash
  mise exec -- uv run pytest tests/analysis tests/test_analysis.py tests/test_evaluator.py tests/test_scan.py -x --tb=short
  mise exec -- uv run python - <<'PY'
  import conformdag.analysis as facade
  from conformdag.analysis.airflow import analyze_source
  from conformdag.analysis.cache import ParseCache
  from conformdag.analysis.discovery import discover_python_files
  from conformdag.analysis.models import SourceModel

  assert facade.analyze_source is analyze_source
  assert facade.ParseCache is ParseCache
  assert facade.discover_python_files is discover_python_files
  assert facade.SourceModel is SourceModel
  print("analysis package imports and facade identities are valid")
  PY
  ```

  Expected: all selected tests pass, including the untouched characterization
  suite and evaluator/scan callers that still import the facade.

- [ ] **Step 8: Commit the mechanical extraction.**

  ```bash
  git add -A src/conformdag/analysis.py src/conformdag/analysis tests/analysis
  git commit -m "refactor: split analysis package"
  ```

### Task 3: Run Full Verification and Record C04 Evidence

**Files:**
- Modify: `docs/consolidation/progress.md` — C03 post-merge acceptance and the assigned C04 row only.
- Reference: `docs/superpowers/specs/2026-09-21-analysis-package-design.md`, `tests/test_analysis.py`, and all focused analysis tests.

**Interfaces:**
- Consumes the green package implementation and focused evidence from Task 2.
- Produces reproducible full-gate evidence and a review-ready C04 ledger row; it does not alter product behavior.

- [ ] **Step 1: Run the complete required verification matrix.**

  Run each command from the repository root and retain its counts/results:

  ```bash
  mise run check
  mise run test:coverage
  mise run schema --check
  git diff --check
  ```

  `mise run check` must pass format, Ruff, Pyright, the non-runtime suite,
  policy-pack validation, and dependency inventory. Coverage must remain at or
  above the repository's 90% gate. No schema update is expected because no
  Pydantic model changed.

- [ ] **Step 2: Inspect package and dependency boundaries.**

  Confirm all 21 facade names resolve to their direct owners, `analysis.py` is
  absent, `analysis` imports no platform/CLI/evaluator/fixing modules, and
  `tests/test_analysis.py` remains present. Re-run the local consolidation link
  check if the progress or spec documents contain new relative links.

- [ ] **Step 3: Update only the ledger state/evidence.**

  Change the merged C03 row from `review` to `accepted` and retain its PR #27
  link, adding merge commit `2b8f0d8d95fc6159885db5052ad709846b5ccad8` to its
  evidence. Change the C04 row from `planned` to `review`, replace its dashes
  with the actual C04 branch/commit/PR reference and the focused/full command
  results from Steps 1–2, and state that the package split preserved facade,
  discovery, cache, AST, scan, and schema behavior. Do not edit other slice
  rows.

- [ ] **Step 4: Commit the evidence update and inspect the final diff.**

  ```bash
  git add docs/consolidation/progress.md
  git commit -m "docs: record C04 analysis package evidence"
  git diff HEAD~1 --check
  git status --short --branch
  ```

  The final working tree must contain no tracked implementation or generated
  files beyond the intended C04 commits; existing untracked tooling artifacts
  must not be staged.

## Handoff

Open the C04 PR without merging it. The PR description must identify the
mechanical package ownership move, the preserved `conformdag.analysis` facade,
the cache legacy-path compatibility test, and the full verification results.
Human review should specifically inspect the owner map, import identities,
legacy pickle loading, symlink issue parity, and the absence of unrelated
platform/evaluator/CLI changes.
