# Deterministic Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the deterministic evaluator into common, Airflow family, and orchestration modules while preserving the C03 catalogue and the `conformdag.evaluator` import facade.

**Architecture:** Shared contracts and finding helpers move to `checks/common.py`; Airflow evaluators move to metadata, scheduling, and safety modules; routing moves to `checks/evaluate.py`. The registry imports evaluator classes from those family modules, while `evaluator.py` only re-exports compatibility names and lazily resolves registry views.

**Tech Stack:** Python 3.12, dataclasses, typing protocols, Pydantic domain models, pytest, Ruff, Pyright, and the existing `mise`/`uv` workflow.

**Spec:** `docs/superpowers/specs/2026-09-22-deterministic-checks-design.md`

## Global Constraints

- This is a mechanical module movement; do not change findings, fingerprints, evaluator ordering, Ruff invocation semantics, or policy applicability.
- `conformdag.checks.registry` remains the one authoritative catalogue; do not create a second registry in the facade.
- Checks must not import CLI, FastAPI, platform, or semantic-provider code.
- Do not alter policy model fields or fix-engine flow.
- Preserve `EvaluationContext`, `DeterministicEvaluator`, `policy_applies`, `structural_fingerprint`, `fix_target`, and `evaluate_deterministic()` compatibility.
- Preserve the C03 catalogue's 15 entries and 12 executable evaluator-backed entries.
- Commit with `refactor: split deterministic checks`; open the PR without merging.

## Review Focus

- **Import cycles and initialization order:** registry-first and facade-first imports must expose identical catalogue dictionaries and evaluator instances. Test in `tests/checks/test_imports.py`.
- **Ruff ownership and path identity:** precomputed violations, fallback execution, symlink scan paths, malformed locations, and selector filtering must remain unchanged. Test in `tests/checks/test_safety.py` and retain the existing adapter characterization tests.
- **Routing semantics:** inactive, non-deterministic, profile-inapplicable, unsupported, legacy, and configuration-invalid policies must retain their existing evaluated/skipped/error behavior. Test in `tests/checks/test_evaluate.py` and retain `tests/test_evaluator.py`.
- **Facade identity:** every moved evaluator class and shared public helper must be the same object reachable through `conformdag.evaluator`, not a wrapper or duplicate. Test in `tests/checks/test_imports.py`.
- **Compatibility documentation:** the facade must state its rationale, introduction version, and removal condition, and architecture documentation must describe the post-C05 ownership. Test with the existing documentation suite and `git diff --check`.

---

### Task 1: Add import-parity and ownership characterization tests

**Files:**
- Create: `tests/checks/test_imports.py`
- Create: `tests/checks/test_common.py`
- Create: `tests/checks/test_metadata.py`
- Create: `tests/checks/test_scheduling.py`
- Create: `tests/checks/test_safety.py`
- Create: `tests/checks/test_evaluate.py`
- Retain: `tests/test_evaluator.py`, `tests/test_check_pack.py`, `tests/test_scan.py`, `tests/test_fixing.py`

**Interfaces:**
- Consumes: the current `conformdag.evaluator` names and the planned direct module paths.
- Produces: failing tests that pin family ownership, facade identity, common contracts, and routing/Ruff seams before moving implementation bodies.

- [ ] **Step 1: Write the failing direct-import and identity tests.**

Use this exact evaluator ownership map:

```python
EVALUATOR_OWNERS = {
    "OwnerEvaluator": "conformdag.checks.airflow.metadata",
    "TagEvaluator": "conformdag.checks.airflow.metadata",
    "TimeoutEvaluator": "conformdag.checks.airflow.scheduling",
    "RetryEvaluator": "conformdag.checks.airflow.scheduling",
    "StartDateFreshnessEvaluator": "conformdag.checks.airflow.scheduling",
    "CatchupPolicyEvaluator": "conformdag.checks.airflow.scheduling",
    "TopLevelIOEvaluator": "conformdag.checks.airflow.safety",
    "ForbiddenOperatorEvaluator": "conformdag.checks.airflow.safety",
    "ModuleScopeVariablesEvaluator": "conformdag.checks.airflow.safety",
    "SensitiveLoggingEvaluator": "conformdag.checks.airflow.safety",
    "DynamicDagFactoryEvaluator": "conformdag.checks.airflow.safety",
    "RuffAirEvaluator": "conformdag.checks.airflow.safety",
}


@pytest.mark.parametrize(("name", "module_name"), EVALUATOR_OWNERS.items())
def test_facade_reexports_the_single_family_class(name: str, module_name: str) -> None:
    facade_class = getattr(importlib.import_module("conformdag.evaluator"), name)
    family_class = getattr(importlib.import_module(module_name), name)
    assert facade_class is family_class
    assert facade_class().policy_id.startswith("AIR-DET-")
```

Also assert that `EvaluationContext`, `DeterministicEvaluator`, `fix_target`,
`policy_applies`, `redact_evidence`, and `structural_fingerprint` imported
from the facade are the same objects from `checks.common`, and that facade
registry views are the exact dictionaries from `checks.registry`.

- [ ] **Step 2: Add direct family characterization cases.**

Keep the existing end-to-end evaluator tests as the behavior oracle and add
one direct ownership test in each focused module. The tests must instantiate
the family class through its direct module path and evaluate the same minimal
models/policies already used by the characterization suite. The safety test
must patch `conformdag.checks.airflow.safety.run_ruff`, not the old facade
path, for both a mapped violation and the no-binary fallback.

- [ ] **Step 3: Run the new tests and record the expected pre-move failure.**

Run:

```bash
mise exec -- uv run pytest tests/checks/test_imports.py tests/checks/test_common.py tests/checks/test_metadata.py tests/checks/test_scheduling.py tests/checks/test_safety.py tests/checks/test_evaluate.py -x --tb=short
```

Expected: collection fails because the direct `checks.common`,
`checks.airflow.*`, and `checks.evaluate` modules do not yet exist. Do not
weaken the tests to make the pre-move run pass.

### Task 2: Move shared contracts and finding helpers

**Files:**
- Create: `src/conformdag/checks/common.py`
- Modify: `tests/checks/test_common.py`

**Interfaces:**
- Consumes: the current contract/helper definitions in `src/conformdag/evaluator.py`.
- Produces: `EvaluationPhaseError`, `EvaluationContext`, `DeterministicEvaluator`, `fix_target`, `policy_applies`, `redact_evidence`, `structural_fingerprint`, and `_finding` for all family modules.

- [ ] **Step 1: Move the imports and definitions without changing bodies.**

Create `checks/common.py` with the exact current signatures:

```python
def fix_target(
    line: int,
    enclosing: str | None,
    node: Literal["dag-call", "task-call", "statement"],
) -> RemediationTarget: ...


@dataclass(frozen=True)
class EvaluationContext:
    policy: Policy
    models: Sequence[SourceModel]
    airflow_profile: AirflowProfile | None = None
    repository_root: Path | None = None
    ruff_violations: list[dict[str, Any]] | None = None


class DeterministicEvaluator(Protocol):
    policy_id: str

    def evaluate(self, context: EvaluationContext) -> list[Finding]: ...
```

Copy `policy_applies`, `redact_evidence`, `structural_fingerprint`, and
`_finding` verbatim, including imports and type annotations. Do not import the
registry, Ruff adapter, or any application layer.

- [ ] **Step 2: Run common tests.**

Run:

```bash
mise exec -- uv run pytest tests/checks/test_common.py -x --tb=short
```

Expected: the direct common tests pass without importing the evaluator facade.

### Task 3: Move metadata evaluators

**Files:**
- Create: `src/conformdag/checks/airflow/__init__.py`
- Create: `src/conformdag/checks/airflow/metadata.py`
- Modify: `tests/checks/test_metadata.py`

**Interfaces:**
- Consumes: `checks.common` and the existing analysis/model types.
- Produces: `OwnerEvaluator` and `TagEvaluator`, with unchanged `policy_id`, `evaluate()` signatures, finding payloads, sort order, and helper calls.

- [ ] **Step 1: Add the thin Airflow package initializer.**

Re-export exactly the twelve evaluator classes from their family modules. Do
not put evaluation logic in `__init__.py` and do not re-export private
helpers.

- [ ] **Step 2: Move `OwnerEvaluator` and `TagEvaluator` verbatim.**

Update only their imports to `conformdag.checks.common` and leave all finding
construction, casts, sorting, and policy IDs unchanged. Do not leave a second
class definition in `evaluator.py` after the facade is installed.

- [ ] **Step 3: Run direct metadata tests.**

Run:

```bash
mise exec -- uv run pytest tests/checks/test_metadata.py tests/test_reporting.py -x --tb=short
```

Expected: direct classes produce the same owner/tag findings as the existing
facade imports.

### Task 4: Move scheduling evaluators and effective-value helpers

**Files:**
- Create: `src/conformdag/checks/airflow/scheduling.py`
- Modify: `tests/checks/test_scheduling.py`

**Interfaces:**
- Consumes: `checks.common`, `SourceModel`, `DagRecord`, `StaticValue`, `TaskRecord`, `ValueState`, and the five scheduling configuration models.
- Produces: `_dag_for_task`, `_effective_value`, `TimeoutEvaluator`, `RetryEvaluator`, `StartDateFreshnessEvaluator`, and `CatchupPolicyEvaluator`.

- [ ] **Step 1: Move the effective-value helpers first.**

Copy `_dag_for_task` and `_effective_value` without changing precedence:
task unresolved kwargs, task values, DAG unresolved defaults, DAG defaults,
then absent. Keep the same `ValueState` values and DAG lookup order.

- [ ] **Step 2: Move the four scheduling evaluator classes verbatim.**

Copy `TimeoutEvaluator`, `RetryEvaluator`, `StartDateFreshnessEvaluator`, and
`CatchupPolicyEvaluator`, including `_target_seconds`, `_unresolved_finding`,
and `_payload`. Replace only old helper imports with local module imports and
`checks.common` imports.

- [ ] **Step 3: Run scheduling characterization tests.**

Run:

```bash
mise exec -- uv run pytest tests/checks/test_scheduling.py tests/test_evaluator.py -k 'timeout or retry or start_date or catchup or deterministic_policy_suite' -x --tb=short
```

Expected: identical statuses, explanations, remediation payloads, and
fingerprints.

### Task 5: Move safety and Ruff evaluators

**Files:**
- Create: `src/conformdag/checks/airflow/safety.py`
- Modify: `tests/checks/test_safety.py`
- Modify: `tests/test_evaluator.py`

**Interfaces:**
- Consumes: `checks.common`, analysis call/constant/import records, safety configuration models, and `conformdag.ruff_adapter`.
- Produces: the six safety evaluator classes, `_resolve_imported_call`, `_ruff_path`, `ruff_policies_for_scan`, and `ruff_rules_for_policies`.

- [ ] **Step 1: Move non-Ruff safety evaluators verbatim.**

Move `TopLevelIOEvaluator`, `_resolve_imported_call`,
`ForbiddenOperatorEvaluator`, `ModuleScopeVariablesEvaluator`,
`SensitiveLoggingEvaluator`, and `DynamicDagFactoryEvaluator`. Preserve
module-scope filtering, operator profile/version checks, secret detection, and
all remediation payloads.

- [ ] **Step 2: Move Ruff selection and mapping verbatim.**

Move `_ruff_path`, `ruff_policies_for_scan`, `ruff_rules_for_policies`, and
`RuffAirEvaluator`. Import `run_ruff` and `ruff_rule_matches` in this module.
Keep path normalization, scanned-file filtering, malformed-location guards,
selector matching, and the `source fixes are disabled` remediation unchanged.

- [ ] **Step 3: Move Ruff tests to the owning patch seam.**

Change only evaluator tests that patch the old implementation seam to:

```python
monkeypatch.setattr("conformdag.checks.airflow.safety.run_ruff", fake_run_ruff)
```

Retain adapter-level tests that patch `conformdag.ruff_adapter` directly.

- [ ] **Step 4: Run safety and Ruff tests.**

Run:

```bash
mise exec -- uv run pytest tests/checks/test_safety.py tests/test_evaluator.py -k 'ruff or top_level or forbidden or module_scope or sensitive or dynamic or deterministic_policy_suite' -x --tb=short
```

Expected: PASS, including symlink scan identity and the single Ruff fallback
path.

### Task 6: Move orchestration and update the C03 registry

**Files:**
- Create: `src/conformdag/checks/evaluate.py`
- Modify: `src/conformdag/checks/registry.py`
- Modify: `tests/checks/test_evaluate.py`
- Modify: `tests/checks/test_registry.py` only where direct owner imports are asserted

**Interfaces:**
- Consumes: `checks.common`, `checks.airflow.safety`, and the existing registry views.
- Produces: `_check_registry`, `policy_configuration_issues`, `_evaluator_for_policy`, and `evaluate_deterministic()` with the current signatures and tuple result.

- [ ] **Step 1: Move routing helpers and preserve lazy registry lookup.**

Create `checks/evaluate.py` with the existing bodies of `_check_registry`,
`policy_configuration_issues`, and `_evaluator_for_policy`. Keep registry
access local to the helper so import order remains safe.

- [ ] **Step 2: Move `evaluate_deterministic()` verbatim.**

Retain sorted policy IDs, configuration validation before evaluation, active
deterministic/hybrid filtering, profile applicability, legacy fallback, and
the `(findings, evaluated, skipped)` return contract. Use the `safety` module
object for both `safety.ruff_rules_for_policies(...)` and
`safety.run_ruff(...)`, so the union invocation remains one patchable owner.

- [ ] **Step 3: Point the registry at family modules.**

Change only `_build_check_specs()` imports from `conformdag.evaluator` to the
metadata, scheduling, and safety modules. Change the `TYPE_CHECKING` protocol
import to `from conformdag.checks.common import DeterministicEvaluator`.
Leave every `CheckSpec` entry and every derived compatibility dictionary
unchanged.

- [ ] **Step 4: Run routing, registry, and import-order tests.**

Run:

```bash
mise exec -- uv run pytest tests/checks tests/test_evaluator.py tests/test_check_pack.py tests/test_scan.py tests/test_fixing.py -x --tb=short
```

Expected: PASS, including registry-first/facade-first subprocess imports and
the existing fixing characterization cases.

### Task 7: Install the compatibility facade and update architecture documentation

**Files:**
- Modify: `src/conformdag/evaluator.py`
- Modify: `docs/architecture.md`
- Modify: `tests/checks/test_imports.py`

**Interfaces:**
- Consumes: all common, family, safety, and evaluate module exports.
- Produces: the unchanged `conformdag.evaluator` import surface with no evaluator implementation or catalogue duplication.

- [ ] **Step 1: Replace the monolith with a documented facade.**

Use this module-docstring contract:

```python
"""Compatibility facade for deterministic evaluation.

Introduced in 1.0.0b1 / C05 because existing consumers import evaluator
contracts, classes, and routing from ``conformdag.evaluator``. Remove only
after those imports have an explicit deprecation and compatibility plan.
"""
```

Explicitly import and re-export the common contracts/helpers, all twelve
family classes, `evaluate_deterministic`, `policy_configuration_issues`,
`ruff_policies_for_scan`, `ruff_rules_for_policies`, `run_ruff`, and
`ruff_rule_matches`. Retain `_REGISTRY_COMPATIBILITY_NAMES` and `__getattr__`
so registry views still resolve from `conformdag.checks.registry`. Do not
define replacement dictionaries or wrapper evaluator classes.

- [ ] **Step 2: Keep existing consumers on the facade.**

Leave `scan.py`, `policy.py`, `semantic_evaluator.py`, benchmark code, and
existing external-facing tests importing from `conformdag.evaluator` unless a
direct import is required to eliminate a cycle.

- [ ] **Step 3: Update architecture text and assert parity.**

Change `docs/architecture.md` to state that `checks.common`,
`checks.airflow.*`, and `checks.evaluate` own deterministic evaluation while
`evaluator.py` is the compatibility facade. Extend import tests to assert
registry views are the exact registry dictionaries and facade class/helper
identities remain stable.

- [ ] **Step 4: Run the complete focused suite.**

Run:

```bash
mise exec -- uv run pytest tests/checks tests/test_evaluator.py tests/test_check_pack.py tests/test_scan.py tests/test_fixing.py tests/test_reporting.py -x --tb=short
```

Expected: all focused tests pass with no finding or report diffs.

### Task 8: Verify, document, commit, and open the PR

**Files:**
- Modify: `docs/consolidation/progress.md`
- Commit: all C05 source/tests/docs changes

**Interfaces:**
- Consumes: the completed modular evaluator and verification matrix.
- Produces: a reviewable C05 branch and PR; no merge.

- [ ] **Step 1: Run the full verification matrix.**

Run each command and retain its exit status/output:

```bash
mise run check
mise run test:coverage
mise run schema --check
git diff --check
```

The default suite must include the 80-case round-trip population. Coverage
must meet the repository's 90% gate; Ruff, Pyright, policy-pack validation,
inventory, and all non-runtime tests must pass.

- [ ] **Step 2: Update the slice ledger with factual evidence.**

Change C04 from `review` to `accepted` and record PR #28's merge commit
`3a651fe8b516b18fb8de2994e76c262635ce7482`. Change C05 from `planned` to
`review`, record the new branch/PR, and summarize focused/full verification
results without claiming human acceptance before merge.

- [ ] **Step 3: Commit the implementation.**

Run:

```bash
git diff --check
git add src/conformdag/checks src/conformdag/evaluator.py tests/checks tests/test_evaluator.py docs/architecture.md docs/consolidation/progress.md docs/superpowers/specs/2026-09-22-deterministic-checks-design.md docs/superpowers/plans/2026-09-22-deterministic-checks.md
git commit -m "refactor: split deterministic checks"
```

Do not stage the pre-existing untracked `.serena/` directory.

- [ ] **Step 4: Request independent review and open the PR.**

Use the repository's independent review workflow to inspect import direction,
registry ownership, finding/fingerprint parity, and Ruff behavior. Address
only verified Critical/Important findings within scope. Push the branch and
open a PR targeting `main` with the title `refactor: split deterministic
checks`; do not merge it.
