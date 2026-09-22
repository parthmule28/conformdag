# C05 — Deterministic Checks Module Design

## Intent

C05 is a mechanical ownership extraction of the deterministic evaluator. The
goal is to make the check families independently navigable without changing
the scan engine, the C03 catalogue, policy applicability, findings,
fingerprints, evaluator ordering, or Ruff behavior.

The existing `conformdag.evaluator` module remains the consumer-facing import
facade. Existing imports continue to resolve to the same evaluator instances
and compatible helper contracts; new direct module paths expose the ownership
boundaries for later slices.

## Scope and invariants

- Move, do not redesign, the twelve executable evaluator classes and their
  helper functions.
- Keep `conformdag.checks.registry` as the only check catalogue and the only
  source of `CHECK_EVALUATORS`, configuration-kind maps, and legacy aliases.
- Preserve `EvaluationContext` field order and `DeterministicEvaluator`'s
  protocol signature.
- Preserve the current sorted policy evaluation order, skip/evaluated lists,
  configuration errors, finding order, remediation payloads, and fingerprints.
- Preserve Ruff's one-union invocation in orchestration, fallback invocation
  in the Ruff evaluator, source-path identity handling, selector filtering,
  and disabled source fixes.
- Keep checks independent of CLI, FastAPI, platform, and semantic-provider
  code.
- Do not change policy model fields, schemas, fix-engine flow, or scan
  orchestration.
- Keep complete application orchestration, runtime/baseline/gate composition,
  CLI delegation, and platform workflow ownership out of C05; C06 owns those
  concerns while `scan_repository()` remains the core primitive.

## Ownership map

| Module | Owns |
| --- | --- |
| `checks/common.py` | `EvaluationPhaseError`, `EvaluationContext`, `DeterministicEvaluator`, `fix_target`, `policy_applies`, `redact_evidence`, `structural_fingerprint`, and the shared `_finding` builder |
| `checks/airflow/metadata.py` | `OwnerEvaluator`, `TagEvaluator` |
| `checks/airflow/scheduling.py` | `_dag_for_task`, `_effective_value`, `TimeoutEvaluator`, `RetryEvaluator`, `StartDateFreshnessEvaluator`, `CatchupPolicyEvaluator` |
| `checks/airflow/safety.py` | `_version_tuple`, `TopLevelIOEvaluator`, `ForbiddenOperatorEvaluator`, `ModuleScopeVariablesEvaluator`, `SensitiveLoggingEvaluator`, `DynamicDagFactoryEvaluator`, `RuffAirEvaluator`, imported-call/path helpers, and Ruff policy/rule helpers |
| `checks/evaluate.py` | registry lookup, policy configuration validation, deterministic routing, shared Ruff orchestration, and `evaluate_deterministic()`; it does not own complete application scans, runtime, baselines, gates, or CLI composition |
| `evaluator.py` | compatibility imports and the existing lazy registry compatibility views; no evaluator instances or second registry |

The `checks.airflow` package initializer starts as a minimal module while the
family files are created, then re-exports all twelve family classes only after
metadata, scheduling, and safety exist. It contains no evaluation logic.
Family modules depend on `checks.common`; they do not depend on the facade or
the registry.

## Import direction

```text
checks.common
    ↑
checks.airflow.metadata / scheduling / safety
    ↑                         ↑
checks.registry         checks.evaluate
    ↑                         ↑
        conformdag.evaluator (compatibility facade)
```

`checks.evaluate` uses the safety module as a module object for Ruff calls so
tests and explicit callers can patch the single Ruff ownership seam without
duplicating the adapter. The facade re-exports the adapter names for import
compatibility. The old test patch path is an implementation seam rather than
a public contract; moved Ruff tests patch `checks.airflow.safety.run_ruff`.

The registry keeps its runtime class imports local while building
`CHECK_SPECS`, as in C03. This preserves both registry-first and
facade-first import order and prevents a circular dependency between the
catalogue and the compatibility facade.

## Compatibility surface

The facade will re-export the common contracts/helpers, all twelve evaluator
classes, `evaluate_deterministic()`, `policy_configuration_issues()`, Ruff
policy helpers, and the adapter names currently reachable from
`conformdag.evaluator`. Its `__getattr__` continues to resolve the four
registry compatibility views from `conformdag.checks.registry`.

The facade docstring records why this surface exists, its introduction in
`1.0.0b1 / C05`, and that removal requires intentionally dropping legacy
consumer imports after an explicit compatibility/deprecation decision.

## Verification design

Focused tests will establish:

1. Every evaluator class has exactly one family-module owner and the facade
   points at that same class.
2. Both registry-first and facade-first imports expose the same catalogue
   dictionaries and evaluator instances.
3. The existing evaluator characterization suite still covers the findings,
   and direct family tests cover the moved ownership and Ruff patch seam.
4. Airflow operator min/max version bounds, Ruff fallback, precomputed
   violations, symlink scan identity, and selector filtering remain unchanged.
5. Full non-runtime tests, coverage, schema synchronization, Ruff, Pyright,
   policy-pack validation, and the round-trip fixing population remain green.
