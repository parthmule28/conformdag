# C05 — Modularize Deterministic Checks

## Role and objective

You are the Build agent for C05. Split the deterministic evaluator monolith into common contracts, Airflow metadata, scheduling, safety, and orchestration modules while preserving the C03 catalogue and the `conformdag.evaluator` import facade.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C03–C04 prompts.
- `src/conformdag/evaluator.py` in full, especially `EvaluationContext`, evaluator protocol, all 12 evaluator classes, Ruff helpers, and registry lookups.
- `src/conformdag/checks/registry.py`, `src/conformdag/scan.py`, `src/conformdag/policy.py`, and `src/conformdag/fixing/engine.py`.
- `tests/test_evaluator.py`, `tests/test_check_pack.py`, `tests/test_scan.py`, and `tests/test_fixing.py`.

## Current ownership and resulting owner

`evaluator.py` currently owns contracts, helpers, all deterministic evaluator classes, Ruff integration, and orchestration. After this PR, `checks/common.py` owns shared contracts/helpers, `checks/airflow/metadata.py` owns owner/tag checks, `checks/airflow/scheduling.py` owns timeout/retry/start-date/catchup checks, `checks/airflow/safety.py` owns IO/operator/module/sensitive/dynamic/Ruff checks, and `checks/evaluate.py` owns routing/orchestration. `evaluator.py` becomes a compatibility facade.

## Interfaces

- Consumes: C03 `CHECK_SPECS` and existing evaluator protocol inputs.
- Produces: `EvaluationContext`, `DeterministicEvaluator`, `policy_applies`, `structural_fingerprint`, `fix_target`, `evaluate_deterministic()`, and compatibility exports with unchanged behavior.

## Expected files

- Create: `src/conformdag/checks/common.py`, `checks/evaluate.py`, `checks/airflow/__init__.py`, `metadata.py`, `scheduling.py`, `safety.py`, and focused `tests/checks/` modules.
- Modify: `src/conformdag/evaluator.py` into a facade, `src/conformdag/checks/registry.py` imports, and only required consumers.
- Do not alter policy model fields or fix engine flow.

## Test-first sequence

1. Add import-parity tests and evaluator-family characterization cases for every current class.
2. Run `tests/test_evaluator.py`, `test_check_pack.py`, `test_scan.py`, and `test_fixing.py` before moving code.
3. Move shared types/helpers first, then metadata, scheduling, safety, and orchestration; update the registry to reference the new classes.
4. Keep `conformdag.evaluator` re-exports until all consumers and tests pass.
5. Run focused checks, the full non-runtime suite, round-trip benchmark, coverage, Pyright, and Ruff.

## Allowed changes

- Mechanical module movement, import changes, focused test splits, and helper visibility changes needed for clean ownership.
- Add a narrow `ruff` adapter helper only where it is currently owned by the evaluator and no trust-boundary logic changes.

## Non-goals and prohibitions

- Do not change findings, fingerprints, evaluator ordering, Ruff invocation semantics, or policy applicability.
- Do not make checks import CLI, FastAPI, platform, or semantic provider code.
- Do not maintain a second registry in the facade.

## Verification matrix

- All evaluator/check-pack/scan/fixing characterization tests.
- 80-case round-trip fixing benchmark.
- `mise run check` and `mise run test:coverage`.
- Independent review of import direction and registry ownership.

## Completion checklist and handoff

- [ ] Every evaluator has one family module owner.
- [ ] `conformdag.evaluator` remains import-compatible.
- [ ] Ruff and structural fingerprint behavior is unchanged.
- [ ] No CLI, FastAPI, platform, or semantic-provider dependency entered checks; the Ruff adapter remains the intentional single ownership seam in `checks.airflow.safety`.
- [ ] Commit with `refactor: split deterministic checks`; open the PR without merging.
