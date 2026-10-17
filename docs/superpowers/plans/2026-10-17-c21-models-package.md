# C21 — Domain Models Package: Sequential TDD Plan

**Date:** 2026-10-17
**Design:** [C21 domain models package design](../specs/2026-10-17-c21-models-package-design.md)
**Stage:** A documentation plan; Stage B requires its own authorization after Stage A is reviewed, merged, and post-merge CI passes.
**Implementation base:** `main@02f6d3b539bd7b1c6f8060b447ae800228e4ff50`
**C21 status:** remains `planned` during Stage A; Stage B implementation PR may move it to `review`; a separate acceptance PR moves it to `accepted`.

## Goal and hard scope

Split `src/conformdag/models.py` into the ownership modules in the design, retaining `conformdag.models` as an explicit identity-preserving facade. This is a compatibility-preserving package refactor, not a model redesign.

Do not change field declarations, model semantics, fingerprints, report JSON, any checked-in schema, schema exporter, migrations, APIs, CLI behavior, frontend, or policy/gate behavior. Do not edit this plan’s ownership decisions during implementation; a conflict with the repository or a failed compatibility invariant is a stop-and-review condition. No task authorizes merge.

## Baseline preparation

Run these before the first implementation edit on the clean base worktree and record exact output in the implementation PR:

```bash
mise run setup
mise run check
mise run schema
sha256sum schemas/policy-pack.json schemas/project-config.json \
  schemas/runtime-manifest.json schemas/scan-report.json \
  schemas/semantic-request.json schemas/semantic-response.json \
  schemas/suppression.json
git diff --check
```

Expected: setup succeeds; the full current gate passes; schema verification passes; the seven hashes equal the design table; and the worktree is clean. If baseline `mise run check` or `mise run schema` fails, stop and report it before changing files. Record the C18 fingerprint and current C19/C20 focused-test results as compatibility oracles, not values to recompute or update.

Use one isolated implementation worktree and one branch from the exact approved base. Make the commits below in order. For every test-first task, commit or stage the new assertion, run its focused test and confirm the described RED, implement only that task, rerun to GREEN, then run its stated regressions. Never leave a commit with a broken facade or duplicate module/package path.

## Task 1 — Characterize the existing public model contract

**Reviewable commit:** `test: characterize legacy model package contract`

Add focused tests under `tests/models/` and a trusted legacy pickle fixture generated from the unchanged base. Do not change production files.

Add assertions for:

- The exact ordered non-underscore export-name manifest from `vars(conformdag.models)`, covering all 58 classes, both aliases, and historical names exposed by wildcard import.
- `from conformdag.models import Name`, `conformdag.models.Name`, and `from conformdag.models import *` bindings for representative classes from every owner group; equal bindings must be the same objects.
- Representative `model_fields` order, `model_dump(mode="json")`, defaults/default-factory independence, discriminated unions, invalid tags, validator messages, and report v1/v2 round trips.
- SHA-256 values of all seven raw schema files; preserve baseline schema renders and `model_json_schema()` comparison through the existing exporter.
- Legacy pickle fixture bytes whose globals name `conformdag.models` for a representative model/enum, so the later package facade can prove old references still load.
- Existing frozen C18/C19 fingerprint assertions and C20 baseline behavior as regression anchors; do not add replacement expected values.

**RED/GREEN checkpoint:** characterization tests must pass on the untouched monolithic baseline (GREEN). Any mismatch against the design’s baseline export/schema manifest means stop and amend the design before the move; do not “fix” current behavior in this task.

```bash
mise exec -- uv run pytest tests/models tests/test_models.py -q
mise exec -- uv run pytest tests/fingerprints/test_deterministic_contract.py \
  tests/fingerprints/test_semantic_contract.py \
  tests/fingerprints/test_report_contract.py \
  tests/fingerprints/test_consumer_contract.py -q
mise run schema
```

## Task 2 — Convert the module to a package atomically

**Reviewable commit:** `refactor: package conformdag domain models`

First add a structural assertion that `importlib.util.find_spec("conformdag.models")` resolves to `src/conformdag/models/__init__.py`, has package search locations, and has no sibling `src/conformdag/models.py`.

**Expected RED:** the test fails because the baseline resolves `models.py` as a module. Then create the package directory and perform one Git rename of the unchanged module to `models/__init__.py`. Keep the complete old implementation in the package initializer for this bootstrap commit; do not create a second module or an empty shadow package.

**Expected GREEN:** the structural test and Task 1 characterization tests pass; old imports and model behavior remain unchanged.

```bash
mise exec -- uv run pytest tests/models -q
mise exec -- uv run pytest tests/test_models.py tests/test_policy.py tests/test_gates.py -q
mise run schema
git diff --check
```

## Task 3 — Extract common and gate value models

**Reviewable commit:** `refactor: extract common and gate models`

Add direct-owner import/identity tests for `conformdag.models.common` and `conformdag.models.gates`, including every common enum/base type, all gate models, and the `GateRule` alias. Cover gate discriminator mappings, serialized tags, validation errors, and model-default behavior. Assert that the facade re-exports each owner object by identity.

**Expected RED:** direct owner-module imports fail before those modules exist. Extract `ConformModel` and the six enums to `common.py`; extract the five gate rule classes, `GateRule`, `QualityGate`, `GateRuleResult`, and `GateResult` to `gates.py`. Update the facade to import/re-export these objects and make `policy`-remaining declarations refer directly to the gate owner where needed. Do not alter `conformdag.gates` (gate evaluation behavior).

**Expected GREEN:** owner imports, facade identity, policy/gate model tests, and exact schema checks pass.

```bash
mise exec -- uv run pytest tests/models tests/test_models.py tests/test_gates.py -q
mise exec -- uv run pytest tests/test_policy.py -q
mise run schema
```

## Task 4 — Extract policy and policy-configuration models

**Reviewable commit:** `refactor: extract policy models`

Add direct-owner tests for all policy and configuration models, `PolicyConfiguration`, validator identity/messages, union tag ordering, and `PolicyPack` composition with `QualityGate`.

**Expected RED:** direct imports from `conformdag.models.policy` fail. Extract the policy-owned declarations and `_POLICY_TAG_PATTERN`, `_empty_airflow_profiles`, and `_empty_quality_gates`; import common and gate symbols from their owner modules. Remove duplicate definitions from the facade and re-export the owner objects.

**Expected GREEN:** policy construction, validation/provenance/hash tests, gate tests, class identity, and all schema hashes pass.

```bash
mise exec -- uv run pytest tests/models tests/test_models.py tests/test_policy.py \
  tests/policy tests/test_gates.py -q
mise run validate:packs
mise run schema
```

## Task 5 — Extract semantic models

**Reviewable commit:** `refactor: extract semantic models`

Add direct-owner tests for `SemanticAuditEvidence`, `SemanticRunMetadata`, `SemanticRequest`, and `SemanticResponse`; check literal status validation, evidence limits, enum defaults, and empty audit-evidence factory independence.

**Expected RED:** direct imports from `conformdag.models.semantic` fail. Move the four definitions and `_empty_audit_evidence` to `semantic.py`, importing shared common types directly. Keep existing facade re-exports and do not change semantic request/response fields or fingerprint logic.

**Expected GREEN:** semantic model, semantic evaluator, C19 semantic fingerprint, and schema tests pass.

```bash
mise exec -- uv run pytest tests/models tests/test_semantic.py \
  tests/fingerprints/test_semantic_contract.py -q
mise run schema
```

## Task 6 — Extract findings and suppression models

**Reviewable commit:** `refactor: extract findings models`

Add direct-owner/identity tests for all seven findings-owned definitions, including `Finding`’s semantic evidence, remediation payloads, and suppression fields. Verify independent default containers and JSON-mode serialization.

**Expected RED:** direct imports from `conformdag.models.findings` fail. Move the definitions; import common enums and semantic evidence/factory from owner modules, never through the facade. Do not change finding identities, report normalization, suppression order, or C20 gate behavior.

**Expected GREEN:** findings/suppression/report round trips, deterministic and semantic finding identity, C18 frozen report fingerprint, and schemas remain unchanged.

```bash
mise exec -- uv run pytest tests/models tests/test_models.py tests/test_reporting.py \
  tests/reporting tests/fingerprints -q
mise exec -- uv run pytest tests/test_baselines.py tests/test_gates.py -q
mise run schema
```

## Task 7 — Extract runtime, report, and project configuration models

**Reviewable commit:** `refactor: extract report runtime and config models`

Add direct-owner tests for `RuntimeObservation`/`RuntimeManifest`, `RunIssue`/`RunMetadata`/`ScanReport`, and all four project configuration models. Verify every report collection factory is fresh and every composed annotation resolves without a cycle.

**Expected RED:** direct imports from `runtime.py`, `report.py`, and `config.py` fail. Move definitions and their report factories, importing cross-module fields using the design DAG. Remove their old definitions from the facade; re-export the owner objects. Do not change scan, CLI, application, platform, or persistence code unless a specific import-cycle correction is unavoidable and approved.

**Expected GREEN:** report v1/v2 compatibility, scan/application serialization, platform persistence/export, project configuration, and all seven schemas pass.

```bash
mise exec -- uv run pytest tests/models tests/test_scan.py tests/test_fixing.py \
  tests/application tests/test_platform.py -q
mise exec -- uv run pytest tests/fingerprints -q
mise run schema
```

## Task 8 — Lock the facade, import graph, pickle, and installed-package behavior

**Reviewable commit:** `test: lock models facade and distribution imports`

Add fresh-process tests that import owner modules in multiple orders, import the root facade and all owners, exercise wildcard imports, and assert no module is an accidental back-edge to `conformdag.models`. Check no platform/application modules are loaded as a side effect. Confirm every baseline name resolves to its owner object and `__all__` preserves the baseline wildcard surface.

Load the Task 1 legacy pickle fixture by its `conformdag.models` globals; also round-trip newly pickled objects through owner module paths. Document the expected `__module__` change to owner modules; do not mutate it for compatibility. Extend `tests/test_distribution.py` so both the built wheel and sdist contain the complete models package, then install the wheel into an isolated target and prove legacy facade imports and direct owner imports work without the source checkout.

**Expected RED:** import-order, pickle, or distribution assertions fail if a re-export is missing, a dependency edge is cyclic, or package files are absent. Fix only the owner/facade wiring required by the design.

**Expected GREEN:** all fresh-process permutations, old/new pickle round trips, and installed wheel/sdist checks pass.

```bash
mise exec -- uv run pytest tests/models tests/test_distribution.py \
  tests/test_policy.py::test_policy_package_import_has_no_cycles_or_repository_side_effects -q
mise run build
mise run schema
```

The existing distribution task runs `ui-build` before `uv build`; preserve the package’s frontend artifacts and do not weaken that packaging gate.

## Task 9 — Full parity verification and review handoff

**Reviewable commit:** `test: verify C21 model package parity`

Run all required checks from a clean implementation worktree. Do not regenerate schemas. Inspect the full diff and prove it contains only the approved `src/conformdag/models/` move/split, focused model/distribution tests, and the C21 status/evidence update in `docs/consolidation/progress.md`.

```bash
mise run check
mise run test:coverage
mise run schema
sha256sum schemas/policy-pack.json schemas/project-config.json \
  schemas/runtime-manifest.json schemas/scan-report.json \
  schemas/semantic-request.json schemas/semantic-response.json \
  schemas/suppression.json
mise run validate:packs
mise run privacy
mise run build
git diff --check
```

Expected: all required gates pass; strict Pyright reports zero errors; coverage remains at least 90%; schema output and the seven raw hashes exactly equal baseline; C18 fingerprint and C19/C20 compatibility tests pass; wheel/sdist smoke passes. Capture focused test totals, full-suite totals, coverage, Pyright, packaging, and exact-head CI evidence in the implementation PR. C21 may move from `planned` to `review` only in that implementation PR’s ledger update. Open the PR against `main` and leave it unmerged for independent review.

## Stop conditions

Stop without regenerating, broadening scope, or continuing to later tasks if:

1. Any characterization test fails on the unmodified baseline.
2. A test-first RED reveals a contract other than the expected missing package/module or a clearly isolated assertion for the current task.
3. Any schema bytes/hash, `mise run schema`, fingerprint, model dump, validation result/error, import-star surface, legacy pickle load, gate/baseline behavior, or downstream report projection changes.
4. An acyclic owner import cannot be achieved without a facade back-edge, adapter import, unexplained forward-reference workaround, or Pydantic internal mutation.
5. Packaging or CI fails for a reason not immediately attributable to the task. Diagnose and report; do not suppress or skip the gate.
6. The diff includes excluded files or unapproved behavior. Do not use reset/checkout to discard work; preserve the branch and request review.

After all tasks, open an unmerged implementation PR and stop for independent review. Do not merge it or open the separate C21 acceptance PR without later explicit authorization.
