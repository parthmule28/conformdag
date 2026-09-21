# Authoritative Check Catalogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize evaluator, configuration, scaffold, legacy-alias, and fixer-vocabulary metadata in one typed `CheckSpec` catalogue while preserving all current scan, policy, finding, fix, report, and CLI behavior.

**Architecture:** Add `conformdag.checks.registry` as the authoritative metadata owner for all 15 known entries. The 12 executable entries reference existing evaluator instances; the three semantic-only entries are explicit `evaluator=None` metadata with no deterministic CLI or policy execution path. Generate evaluator, legacy, and fixability compatibility views from the catalogue, while retaining evaluator implementations and the explicit `FIXERS` function map in their current modules.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, Pyright strict mode, Ruff, Typer, existing `conformdag.evaluator` and `conformdag.fixing.codemods` modules.

**Spec:** `docs/superpowers/specs/2026-09-21-authoritative-check-catalogue-design.md`

## Global Constraints

- Preserve one scan engine: `src/conformdag/scan.py:scan_repository()` remains the canonical core evaluation primitive.
- Do not move evaluator classes or evaluator helpers; C05 owns evaluator modularization.
- Represent all 15 known kinds, but expose only the 12 evaluator-backed kinds through deterministic evaluator and CLI/policy execution views.
- Store every current `RemediationPayload.fix_kind` value explicitly in `CheckSpec.fix_kind`; do not substitute evaluator `kind` when they differ.
- Derive `AUTOFIX_KINDS`, `PROPOSED_ONLY_KINDS`, and `MANUAL_KINDS` from `spec.fix_kind`.
- Keep `FIXERS` as the explicit codemod function map; do not move codemod bodies or make the registry import `FIXERS`.
- Use `evaluator.py.__getattr__` only for external compatibility imports; evaluator internals must use an explicit cycle-safe local registry helper.
- Preserve evaluator ordering, policy IDs, policy scaffolding output, finding semantics, fingerprints, report JSON, fix application, and scan orchestration.
- Do not introduce platform DTO/OpenAPI/service restructuring; those belong to later slices.
- Use targeted `pyright` ignores only where the existing ruamel.yaml convention requires them; do not add broad type ignores.

## Review Focus

- **Fixer vocabulary divergence:** `operator-allow-list` must derive `forbidden-operators`, and `module-scope-io` must derive `top-level-io`; pin the complete 15-entry mapping in `tests/checks/test_registry.py`.
- **Non-executable semantic entries:** `idempotence`, `orchestration-boundary`, and `approved-abstractions` must have `evaluator=None` and remain unavailable to deterministic `policy new` and policy validation; pin executable filtering and CLI rejection in the registry/CLI tests.
- **Import-order cycles:** importing registry first or evaluator first must expose the same derived views and permit a real `effective-owner` lookup/evaluation; pin both subprocess orders in the registry tests.
- **Internal facade misuse:** `policy_configuration_issues()` and evaluator routing must use the local registry helper rather than missing module globals; exercise both paths after each import order.
- **Scaffold drift and mutation:** each executable scaffold must validate through the existing discriminated `PolicyConfiguration` adapter, return a fresh object, and preserve the current CLI YAML; pin fresh-object and CLI parity tests.

---

## File Structure

The implementation changes are intentionally limited to these ownership boundaries:

- **Create:** `src/conformdag/checks/__init__.py` — public facade for the authoritative registry API.
- **Create:** `src/conformdag/checks/registry.py` — `Fixability`, `CheckSpec`, all 15 entries, scaffold factories, and generated compatibility views.
- **Create:** `tests/checks/__init__.py` — test package marker if required by the repository test layout.
- **Create:** `tests/checks/test_registry.py` — catalogue invariants, scaffolds, fixability vocabulary, import-order, and real evaluator parity tests.
- **Modify:** `src/conformdag/evaluator.py` — remove duplicate metadata tables, add the external compatibility facade, and route internal lookups through a local registry helper.
- **Modify:** `src/conformdag/fixing/codemods.py` — retain `FIXERS` and codemod bodies while importing derived fixability views.
- **Modify:** `src/conformdag/cli.py` — replace the scaffold table and executable-kind check with registry lookups.
- **Modify:** `src/conformdag/policy.py` — consume registry-derived executable evaluator/configuration views for validation.
- **Modify:** `docs/architecture.md` and `tests/test_documentation.py` — document and pin the new catalogue owner while retaining compatibility names.
- **Modify:** focused evaluator, fixing, CLI, policy, and round-trip tests only where imports or explicit compatibility assertions need to name the new owner.
- **Modify:** `docs/consolidation/progress.md` — record C03 evidence only after all implementation gates pass.

---

### Task 1: Write the Registry Contract Tests First

**Files:**
- Create: `tests/checks/__init__.py`
- Create: `tests/checks/test_registry.py`
- Reference: `src/conformdag/models.py`, `src/conformdag/evaluator.py`, `src/conformdag/fixing/codemods.py`

**Interfaces:**
- Consumes the existing evaluator protocol, `Policy` model, `PolicyConfiguration` discriminated union, and `FIXERS` map.
- Produces the behavioral contract for `Fixability`, `CheckSpec`, `CHECK_SPECS`, `check_spec()`, generated views, and compatibility import order.

- [ ] **Step 1: Add the expected catalogue constants and mapping assertions.**

  Pin the 15 catalogue kinds in current evaluator order followed by the three semantic-only entries. Pin the full fixer vocabulary, including the two divergent mappings:

  ```python
  EXPECTED_FIX_KINDS = {
      "effective-owner": "required-owner",
      "tags": "required-tags",
      "effective-timeout": "execution-timeout",
      "retry-bounds": "retry-bounds",
      "module-scope-io": "top-level-io",
      "operator-allow-list": "forbidden-operators",
      "start-date-freshness": "start-date-freshness",
      "catchup-policy": "catchup-policy",
      "module-scope-variables": "module-scope-variables",
      "sensitive-logging": "sensitive-logging",
      "dynamic-dag-factory": "dynamic-dag-factory",
      "ruff-air": "ruff-air",
      "idempotence": "idempotence",
      "orchestration-boundary": "orchestration-boundary",
      "approved-abstractions": "approved-abstractions",
  }
  EXECUTABLE_KINDS = tuple(EXPECTED_FIX_KINDS)[:12]
  NON_EXECUTABLE_KINDS = frozenset(EXPECTED_FIX_KINDS) - set(EXECUTABLE_KINDS)
  ```

  Assert that `CHECK_SPECS.keys()` preserves `EXECUTABLE_KINDS` order followed by the three non-executable kinds, every `spec.fix_kind` matches `EXPECTED_FIX_KINDS`, and every fixability set is derived from expected fix-kind values rather than evaluator-kind values.

- [ ] **Step 2: Add executable/semantic and legacy mapping tests.**

  Assert each executable spec has a non-`None` evaluator and scaffold factory, each semantic-only spec has `evaluator is None` and no executable classification, all legacy IDs are unique, and `LEGACY_POLICY_CHECKS`, `LEGACY_POLICY_EVALUATORS`, and `LEGACY_POLICY_CONFIGURATION_KINDS` agree with the corresponding `CheckSpec`.

- [ ] **Step 3: Add scaffold and codemod consistency tests.**

  For every executable spec, call its factory twice, assert distinct objects, validate both with `TypeAdapter(PolicyConfiguration)`, and assert the returned `kind` equals `spec.configuration_kind`. For every autofix/proposed spec, assert `spec.fix_kind in FIXERS`; assert manual fix kinds have no fixer entry.

- [ ] **Step 4: Add real import-order subprocess tests.**

  Run a fresh Python subprocess for each order so cached modules cannot hide cycles. Each script must perform the catalogue lookup and a real evaluator call, not only imports:

  ```python
  spec = registry.check_spec("effective-owner")
  assert spec.evaluator is registry.CHECK_EVALUATORS["effective-owner"]
  policy = Policy.model_construct(
      id="AIR-TST-001",
      title="Owner",
      version="1.0.0",
      status=LifecycleStatus.ACTIVE,
      severity=Severity.MEDIUM,
      airflow_profiles=[],
      ownership=Ownership(owner="platform"),
      source=PolicySource(document=Path("standards.md"), section="Owners", content_hash="hash"),
      invariant="An owner is present.",
      safe_path="Add an owner.",
      enforcement=EnforcementConfig(
          type=EnforcementType.DETERMINISTIC,
          deterministic_checks=["effective-owner"],
          blocking=True,
      ),
      configuration=RequiredOwnerConfig(allowed_values=["platform"]),
  )
  findings, evaluated, skipped = evaluate_deterministic([policy], [])
  assert findings == []
  assert evaluated == ["AIR-TST-001"]
  assert skipped == []
  ```

  Execute this once after `import conformdag.checks.registry` followed by evaluator compatibility imports, and once after `import conformdag.evaluator` followed by registry imports. Also assert both orders expose identical derived view objects.

- [ ] **Step 5: Run the new tests to confirm the intended red state.**

  Run: `mise exec -- uv run pytest tests/checks/test_registry.py -x --tb=short`

  Expected: collection fails because `conformdag.checks.registry` does not exist yet. Do not implement production code until this failure is observed.

- [ ] **Step 6: Commit the failing contract tests.**

  ```bash
  git add tests/checks/__init__.py tests/checks/test_registry.py
  git commit -m "test: define authoritative check catalogue contract"
  ```

### Task 2: Implement the Authoritative Registry and Scaffolds

**Files:**
- Create: `src/conformdag/checks/__init__.py`
- Create: `src/conformdag/checks/registry.py`
- Test: `tests/checks/test_registry.py`

**Interfaces:**
- Consumes existing evaluator classes by lazy import, existing `RUFF_AIR_RULES`, and typed model configuration kinds.
- Produces `Fixability`, frozen `CheckSpec`, `CHECK_SPECS`, `check_spec(kind)`, generated view constants, and executable scaffold factories.

- [ ] **Step 1: Define the typed catalogue structures.**

  Add a string-valued `Fixability` enum with `AUTOFIX`, `PROPOSED_ONLY`, and `MANUAL`. Add a frozen `CheckSpec` dataclass with the exact fields from the approved spec; `fix_kind` is required and `evaluator`/`scaffold_factory` are optional only for non-executable entries.

- [ ] **Step 2: Implement named fresh scaffold factories.**

  Move the current `cli._policy_configuration()` values without changing them:

  ```text
  effective-owner       -> required-owner       {allowed_values: [platform]}
  tags                  -> required-tags        {required_keys: [domain, owner], allowed_values: {domain: [data, analytics, platform]}}
  effective-timeout     -> execution-timeout    {min_seconds: 1, max_seconds: 86400, approved_default_seconds: 3600}
  retry-bounds          -> retry-bounds         {min_retries: 0, max_retries: 5, min_delay_seconds: 0, max_delay_seconds: 3600, allow_zero_retries: true}
  module-scope-io       -> top-level-io         {forbidden_calls: [requests.get, boto3.client, subprocess.run], uncertain_as_review: true}
  operator-allow-list   -> forbidden-operators  {operators: {airflow.operators.python.PythonOperator: use-taskflow}}
  start-date-freshness  -> start-date-freshness {max_age_years: 2, require_timezone: true}
  catchup-policy        -> catchup-policy       {allow_catchup: false}
  module-scope-variables -> module-scope-variables {patterns: [Variable.get]}
  sensitive-logging     -> sensitive-logging   {secret_patterns: [password, token, secret], logging_calls: [logging.info, logging.warning, logging.error]}
  dynamic-dag-factory   -> dynamic-dag-factory   {allow: false}
  ruff-air              -> ruff-air             {rules: a fresh copy of RUFF_AIR_RULES}
  ```

  Each factory must allocate fresh mutable lists/dicts. The three semantic-only entries have no scaffold factory because current deterministic CLI support does not expose them.

- [ ] **Step 3: Build the 15 `CheckSpec` entries.**

  Use the exact `kind`, `configuration_kind`, `fix_kind`, fixability, and execution status from the approved spec table. Instantiate existing evaluator classes lazily inside a private builder; do not copy evaluator logic or create a second evaluator metadata table.

- [ ] **Step 4: Derive all registry views.**

  Derive `CHECK_EVALUATORS` and `CHECK_CONFIGURATION_KINDS` from evaluator-backed specs, legacy maps from `legacy_policy_ids`, and fixability sets from `spec.fix_kind`. Ensure the derived dictionaries preserve executable insertion order and the legacy policy map points to check kinds before resolving evaluator objects.

- [ ] **Step 5: Export the new package facade.**

  Re-export `Fixability`, `CheckSpec`, `CHECK_SPECS`, `check_spec`, executable/legacy views, and fixability sets from `checks/__init__.py` without importing codemods.

- [ ] **Step 6: Run the registry tests.**

  Run: `mise exec -- uv run pytest tests/checks/test_registry.py -x --tb=short`

  Expected: catalogue, scaffold, fix-kind, and generated-view tests pass; import-order tests remain red until the evaluator compatibility facade and internal helper are added in Task 3.

- [ ] **Step 7: Commit the registry implementation.**

  ```bash
  git add src/conformdag/checks tests/checks/test_registry.py
  git commit -m "feat: add authoritative check catalogue"
  ```

### Task 3: Add the Cycle-Safe Evaluator Facade and Internal Helper

**Files:**
- Modify: `src/conformdag/evaluator.py`
- Test: `tests/checks/test_registry.py`
- Test: `tests/test_evaluator.py`

**Interfaces:**
- Consumes registry views from `conformdag.checks.registry` through an explicit local helper.
- Produces legacy evaluator-module imports and internal routing that work after either import order.

- [ ] **Step 1: Add the local registry helper test expectation.**

  Keep the subprocess test from Task 1 asserting `evaluate_deterministic()` returns the expected empty findings/evaluated/skipped tuple. Add a direct evaluator test that a policy with `deterministic_checks=["effective-owner"]` reaches the evaluator through the helper and does not raise a missing-global error.

- [ ] **Step 2: Replace evaluator-owned metadata tables.**

  Remove the literal `CHECK_EVALUATORS`, `CHECK_CONFIGURATION_KINDS`, `LEGACY_POLICY_EVALUATORS`, and `LEGACY_POLICY_CONFIGURATION_KINDS` tables from `evaluator.py`. Add a private helper with a local import:

  ```python
  def _check_registry():
      from conformdag.checks import registry

      return registry
  ```

  Make `policy_configuration_issues()` read executable configuration and legacy configuration views from `_check_registry()`. Make `_evaluator_for_policy()` read evaluator and legacy evaluator views from `_check_registry()`. No evaluator function may rely on a missing global being resolved by module `__getattr__`.

- [ ] **Step 3: Add external compatibility resolution only.**

  Add `TYPE_CHECKING` declarations and a module-level `__getattr__` that lazily returns registry compatibility names for external imports. The facade must reject unknown names with `AttributeError`, and no internal evaluator function may call the facade implicitly.

- [ ] **Step 4: Run import-order and evaluator tests.**

  Run: `mise exec -- uv run pytest tests/checks/test_registry.py tests/test_evaluator.py -x --tb=short`

  Expected: all registry import-order tests and existing evaluator behavior tests pass.

- [ ] **Step 5: Commit the evaluator facade.**

  ```bash
  git add src/conformdag/evaluator.py tests/checks/test_registry.py tests/test_evaluator.py
  git commit -m "refactor: derive evaluator views from catalogue"
  ```

### Task 4: Derive Fixability Classifications While Preserving FIXERS

**Files:**
- Modify: `src/conformdag/fixing/codemods.py`
- Modify: `src/conformdag/fixing/engine.py` only if import typing requires it; preserve behavior
- Test: `tests/test_fixing.py`
- Test: `tests/checks/test_registry.py`

**Interfaces:**
- Consumes `AUTOFIX_KINDS`, `PROPOSED_ONLY_KINDS`, and `MANUAL_KINDS` generated from `CheckSpec.fix_kind`.
- Produces the unchanged explicit `FIXERS: dict[str, Codemod]` map keyed by remediation vocabulary.

- [ ] **Step 1: Add a regression assertion for the divergent fixer keys.**

  Assert `"forbidden-operators" in MANUAL_KINDS`, `"top-level-io" in PROPOSED_ONLY_KINDS`, `"operator-allow-list" not in MANUAL_KINDS`, and `"module-scope-io" not in PROPOSED_ONLY_KINDS`. Keep the existing complete matrix assertions as parity coverage.

- [ ] **Step 2: Remove manual fixability set literals from codemods.**

  Import the three generated sets from `conformdag.checks.registry`. Leave every existing `FIXERS` entry and codemod body unchanged, including the `top-level-io` and `forbidden-operators` vocabulary. Keep `TIMEDELTA_KINDS` as codemod post-processing metadata because it describes import insertion behavior, not catalogue fixability or executable check registration.

- [ ] **Step 3: Run fixing and round-trip tests.**

  Run: `mise exec -- uv run pytest tests/checks/test_registry.py tests/test_fixing.py tests/test_roundtrip.py -x --tb=short`

  Expected: the fixability matrix, all codemods, and the autofix round-trip population pass without changed patches or residual behavior.

- [ ] **Step 4: Commit the fixer compatibility change.**

  ```bash
  git add src/conformdag/fixing/codemods.py tests/checks/test_registry.py tests/test_fixing.py
  git commit -m "refactor: derive fixer classifications from catalogue"
  ```

### Task 5: Migrate CLI Scaffolding and Policy Validation

**Files:**
- Modify: `src/conformdag/cli.py`
- Modify: `src/conformdag/policy.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Consumes `check_spec()`, executable evaluator views, and scaffold factories from `checks.registry`.
- Produces unchanged `policy new` output, unknown-kind errors, pack validation, and legacy policy fallback behavior.

- [ ] **Step 1: Add executable-boundary tests.**

  Extend CLI tests to assert `policy new --kind idempotence`, `--kind orchestration-boundary`, and `--kind approved-abstractions` retain the current non-executable rejection. Keep the existing loop over `CHECK_EVALUATORS` and exact Ruff scaffold assertion.

- [ ] **Step 2: Replace `_policy_configuration()` with registry lookup.**

  Remove the duplicate configuration dictionary. Have the private helper resolve `check_spec(kind)`, reject missing/non-executable specs with the current error, and call the selected factory. Have `policy_new()` use the executable registry view for its known-kind check while preserving the exact YAML block and `Policy.model_validate()` guard.

- [ ] **Step 3: Replace policy validation table imports.**

  Make `validate_policy_pack()` consume registry-derived `CHECK_EVALUATORS` for unknown deterministic checks. Leave quality-gate, Ruff selector, provenance, and policy configuration validation semantics unchanged. The evaluator’s `policy_configuration_issues()` remains the owner of expected configuration/legacy mappings and accesses them through its local helper.

- [ ] **Step 4: Run CLI and policy parity tests.**

  Run: `mise exec -- uv run pytest tests/test_cli.py tests/test_policy.py tests/checks/test_registry.py -x --tb=short`

  Expected: all existing scaffold, unknown-check, legacy-policy, and pack validation assertions pass with byte-equivalent scaffold payloads.

- [ ] **Step 5: Commit the CLI/policy migration.**

  ```bash
  git add src/conformdag/cli.py src/conformdag/policy.py tests/test_cli.py tests/test_policy.py
  git commit -m "refactor: route CLI and policy metadata through catalogue"
  ```

### Task 6: Update Ownership Documentation and Compatibility Assertions

**Files:**
- Modify: `docs/architecture.md`
- Modify: `tests/test_documentation.py`
- Modify: focused existing imports only when needed to state compatibility ownership

**Interfaces:**
- Consumes the final registry ownership and compatibility facade.
- Produces documentation that identifies `checks.registry` as the metadata owner while retaining the public compatibility names.

- [ ] **Step 1: Update the architecture policy-model paragraph.**

  State that `checks.registry` owns the authoritative `CheckSpec` catalogue and derives `CHECK_EVALUATORS`, fixability views, and legacy aliases. State that evaluator implementations remain in `evaluator.py` until C05 and legacy names remain compatibility views.

- [ ] **Step 2: Update documentation assertions.**

  Preserve assertions for the compatibility names and add an assertion for the authoritative catalogue owner. Do not remove compatibility wording that current users or tests rely on.

- [ ] **Step 3: Run documentation and focused compatibility tests.**

  Run: `mise exec -- uv run pytest tests/test_documentation.py tests/checks/test_registry.py tests/test_evaluator.py tests/test_fixing.py tests/test_cli.py tests/test_policy.py -x --tb=short`

  Expected: documentation, registry, evaluator, fixer, CLI, and policy parity tests pass.

- [ ] **Step 4: Commit the ownership documentation.**

  ```bash
  git add docs/architecture.md tests/test_documentation.py
  git commit -m "docs: record authoritative check catalogue ownership"
  ```

### Task 7: Run Full C03 Verification and Record Evidence

**Files:**
- Modify: `docs/consolidation/progress.md`
- Review: all C03 implementation files and commits

**Interfaces:**
- Consumes the completed catalogue, compatibility views, and parity tests.
- Produces a review-ready C03 branch with measured verification evidence and no unrelated changes.

- [ ] **Step 1: Run the complete Python quality gate.**

  Run: `mise run check`

  Expected: Ruff, format, Pyright, pack validation, dependency inventory, and the complete non-runtime suite pass.

- [ ] **Step 2: Run coverage and schema/package gates.**

  Run: `mise run test:coverage`, `mise run schema --check`, and `mise run build`.

  Expected: coverage remains at or above the repository’s 90% gate, checked-in schemas remain synchronized, and the frontend/package build succeeds without C03-generated contract changes.

- [ ] **Step 3: Run the focused 80-case round-trip and registry suites once more.**

  Run: `mise exec -- uv run pytest tests/checks/test_registry.py tests/test_evaluator.py tests/test_fixing.py tests/test_cli.py tests/test_policy.py tests/test_roundtrip.py -x --tb=short`

  Expected: the catalogue invariants, import-order execution checks, evaluator behavior, fixer behavior, CLI scaffolds, policy validation, and round-trip verification all pass.

- [ ] **Step 4: Update the C03 progress row.**

  Record the branch, commit/PR reference, test counts, coverage, schema/pack/build evidence, and the explicit limitation that semantic-only entries remain non-executable until they are separately implemented in a future scoped slice. Keep C02’s accepted evidence unchanged.

- [ ] **Step 5: Inspect and commit the final evidence.**

  Run `git diff --check`, `git diff --stat`, and `git status --short --branch`. Confirm only the planned catalogue, compatibility, test, documentation, and progress files are tracked. Commit the ledger update with:

  ```bash
  git add docs/consolidation/progress.md
  git commit -m "docs: record C03 catalogue verification"
  ```

- [ ] **Step 6: Push the branch and open the C03 PR without merging.**

  Write the reviewed evidence into `/tmp/c03-pr-body.md` before opening the PR:

  ```markdown
  ## Summary

  - Centralize all 15 check metadata entries in `checks.registry`.
  - Preserve the 12-entry executable boundary and existing fixer vocabulary.
  - Keep evaluator compatibility imports cycle-safe and scan behavior unchanged.

  ## Verification

  - `mise run check`: <record result>
  - `mise run test:coverage`: <record result>
  - `mise run schema --check`: <record result>
  - `mise run build`: <record result>
  - Focused registry/evaluator/fixing/CLI/policy/round-trip tests: <record result>

  Semantic-only entries remain non-executable until they are separately
  implemented in a future scoped slice.
  ```

  ```bash
  git push -u origin docs/c03-authoritative-check-catalogue
  gh pr create --base main --head docs/c03-authoritative-check-catalogue \
    --title "refactor: centralize check catalogue" \
    --body-file /tmp/c03-pr-body.md
  ```

  The PR body must list the 15-entry/12-executable boundary, preserved fixer vocabulary, cycle-safe import-order tests, unchanged scan behavior, and full verification evidence. Do not merge the C03 PR in this slice.
