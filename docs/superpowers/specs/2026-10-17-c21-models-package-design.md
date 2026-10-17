# C21 — Domain Models Package: Design

**Date:** 2026-10-17
**Stage:** A — design only
**Status:** C21 remains `planned`; this document does not authorize Stage B.
**Baseline:** `main@02f6d3b539bd7b1c6f8060b447ae800228e4ff50`
**Source:** GitHub issue [#76](https://github.com/parthmule28/conformdag/issues/76)

## Objective and scope

Replace the monolithic `src/conformdag/models.py` with a cohesive `src/conformdag/models/` package while preserving the existing public model API and every current data, validation, serialization, and schema contract. The package split is an ownership change only: it must not change model behavior or downstream policy, gate, report, CLI, application, platform, or adapter behavior.

Stage A consists of this design and its sequential TDD plan. No source, tests, schemas, scripts, packaging files, or progress-ledger entries are changed by Stage A. Stage B requires the independent review and merge conditions in issue #76; this document alone is not implementation authorization.

## Frozen contracts

- Preserve every model class, field name and declaration order, annotation, default, default factory, validator, `model_config`, discriminator, literal tag, and validation diagnostic.
- Preserve `model_validate`, `model_dump`, JSON-mode output, `model_json_schema`, and legacy versioned payload behavior.
- Preserve both model import forms: `from conformdag.models import Name` and `conformdag.models.Name`. Re-export the original class objects; do not define shadow classes in the facade.
- Preserve the current `from conformdag.models import *` symbol set. The baseline module exposes 74 non-underscore names, including historical helper imports (`annotations`, `re`, `datetime`, `StrEnum`, `Path`, `Annotated`, `Any`, `Literal`, `BaseModel`, `ConfigDict`, `Field`, `NonNegativeInt`, `PositiveInt`, and `field_validator`) as well as the 58 classes and two type aliases. The package facade will make this surface explicit with an ordered `__all__`; tests will pin its names and bindings. These incidental names remain only for import compatibility, not as recommended APIs.
- Preserve the C18 report fingerprint `8050ab09ad677b729bc5287e99347713afc10bf0d87957066b1494442f034e26`, C19 finding identities, and C20 baseline/gate compatibility.
- Preserve the exact UTF-8 bytes and trailing newline of all seven checked-in JSON schemas. No schema regeneration or schema change is part of C21.
- Do not change production behavior, APIs, policies, fingerprint algorithms, report content, migrations, generated frontend types, or the schema exporter.

## Current-to-target ownership map

The inventory below accounts for all 58 classes in the baseline module, both public type aliases, and the module-level helpers used by their declarations. Class definitions and their behavior move verbatim to one owner module; `models/__init__.py` only re-exports them.

The current wildcard manifest, in the exact insertion order observed at the baseline, is:

```text
annotations, re, datetime, StrEnum, Path, Annotated, Any, Literal,
BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, field_validator,
ConformModel, LifecycleStatus, Severity, EnforcementType, FindingStatus,
AirflowProfile, Confidence, PolicySource, Ownership, PolicyScope,
ExceptionPolicy, EnforcementConfig, RequiredOwnerConfig, RequiredTagsConfig,
ExecutionTimeoutConfig, RetryBoundsConfig, TopLevelIOConfig, OperatorRule,
ForbiddenOperatorsConfig, IdempotenceConfig, OrchestrationBoundaryConfig,
SensitiveLoggingConfig, StartDateFreshnessConfig, CatchupPolicyConfig,
ModuleScopeVariablesConfig, DynamicDagFactoryConfig, RuffAirConfig,
ApprovedAbstractionsConfig, PolicyConfiguration, NoNewFindingsRule,
MaxSeverityRule, MaxFindingsRule, AlwaysBlockRule, FailureRateRule, GateRule,
QualityGate, GateRuleResult, GateResult, Policy, PolicyPack, FindingEvidence,
FindingLocation, RemediationAction, RemediationTarget, RemediationPayload,
Suppression, SemanticAuditEvidence, Finding, RunIssue, RuntimeObservation,
SemanticRunMetadata, RunMetadata, ScanReport, RuntimeManifest,
SemanticRequest, SemanticResponse, ProjectScanConfig, ProjectSemanticConfig,
ProjectRuntimeConfig, ProjectConfig
```

| Target module | Owned public definitions |
| --- | --- |
| `models/common.py` | `ConformModel`; `LifecycleStatus`, `Severity`, `EnforcementType`, `FindingStatus`, `AirflowProfile`, and `Confidence` |
| `models/gates.py` | `NoNewFindingsRule`, `MaxSeverityRule`, `MaxFindingsRule`, `AlwaysBlockRule`, `FailureRateRule`, `QualityGate`, `GateRuleResult`, `GateResult`; type alias `GateRule` |
| `models/policy.py` | `PolicySource`, `Ownership`, `PolicyScope`, `ExceptionPolicy`, `EnforcementConfig`, `RequiredOwnerConfig`, `RequiredTagsConfig`, `ExecutionTimeoutConfig`, `RetryBoundsConfig`, `TopLevelIOConfig`, `OperatorRule`, `ForbiddenOperatorsConfig`, `IdempotenceConfig`, `OrchestrationBoundaryConfig`, `SensitiveLoggingConfig`, `StartDateFreshnessConfig`, `CatchupPolicyConfig`, `ModuleScopeVariablesConfig`, `DynamicDagFactoryConfig`, `RuffAirConfig`, `ApprovedAbstractionsConfig`, `Policy`, `PolicyPack`; type alias `PolicyConfiguration` |
| `models/semantic.py` | `SemanticAuditEvidence`, `SemanticRunMetadata`, `SemanticRequest`, `SemanticResponse` |
| `models/findings.py` | `FindingEvidence`, `FindingLocation`, `RemediationAction`, `RemediationTarget`, `RemediationPayload`, `Suppression`, `Finding` |
| `models/runtime.py` | `RuntimeObservation`, `RuntimeManifest` |
| `models/report.py` | `RunIssue`, `RunMetadata`, `ScanReport` |
| `models/config.py` | `ProjectScanConfig`, `ProjectSemanticConfig`, `ProjectRuntimeConfig`, `ProjectConfig` |
| `models/__init__.py` | Compatibility facade only: explicit re-exports and `__all__`; no duplicate model definitions |

Private declaration helpers move with their owning fields: `_POLICY_TAG_PATTERN` and `_empty_airflow_profiles` to `policy.py`; `_empty_quality_gates` to `policy.py`; `_empty_audit_evidence` to `semantic.py` and imported by `findings.py`; and `_empty_paths`, `_empty_findings`, `_empty_issues`, `_empty_runtime_observations`, and `_empty_semantic_runs` to `report.py`. Their names, return types, and fresh-container behavior remain unchanged. No private helper is added to the public facade.

## Acyclic import graph

Arrows mean “imports from”; there are no reverse edges. Standard-library and Pydantic imports are omitted.

```text
models.common
  └── no model-package dependencies

models.gates       → models.common
models.policy      → models.common, models.gates
models.semantic    → models.common
models.findings    → models.common, models.semantic
models.runtime     → models.common
models.report      → models.common, models.gates, models.findings,
                     models.runtime, models.semantic
models.config      → models.common

models (facade)    → each owner module above; no owner imports the facade
```

This reflects the actual annotation relationships: `PolicyPack` contains `QualityGate`; `Finding` and `SemanticResponse` share `SemanticAuditEvidence`; and `ScanReport` composes the gate, finding, runtime, semantic, and report values. `models.gates` contains value types only and is distinct from the existing behavior module `conformdag.gates`.

Owner modules import referenced domain symbols directly from their owner modules. They must never import `conformdag.models`, `conformdag.models.__init__`, or a sibling symbol through the facade. The facade imports owner symbols only after the owner dependency graph is valid. No model module may import application, CLI, platform, FastAPI, Typer, SQLAlchemy, provider, or adapter code. Avoid `TYPE_CHECKING`-only graph camouflage and `model_rebuild()` workarounds; introduce either only if a demonstrated Pydantic limitation requires a reviewed design amendment.

## Safe module-to-package migration

The file and package cannot coexist at the same import path. Stage B must keep that transition reviewable and unambiguous:

1. On the unchanged baseline, add and run characterization tests and record the seven schema hashes below, the complete public import/star surface, representative validation/serialization results, and legacy pickle evidence.
2. Add a structural test that requires `conformdag.models` to resolve to `src/conformdag/models/__init__.py` and rejects a sibling `src/conformdag/models.py`.
3. Create the package directory and perform one Git move of `src/conformdag/models.py` to `src/conformdag/models/__init__.py`, preserving the file content in that commit. Do not commit a state containing both import targets or a placeholder package that shadows the original implementation.
4. In later test-first commits, move one ownership group at a time into its owner module, delete each moved definition from the facade, and re-export the original owner object. Keep tests and imports green after each commit.
5. Leave existing consumers on `conformdag.models` unless a specific internal import must change to enforce the DAG. Do not perform a repository-wide import rewrite for style.

The migration commit sequence and red/green checkpoints are specified in the plan. All work stays on the C21 implementation branch; no ledger edit or unrelated cleanup is allowed.

## Compatibility facade and Python introspection

`conformdag.models` remains the stable import facade. It explicitly re-exports every baseline public class and both aliases, preserving module attribute access, `from conformdag.models import Name`, wildcard-import bindings, and object identity (`conformdag.models.Name is conformdag.models.<owner>.Name`). The explicit `__all__` preserves the observed baseline wildcard name set, including the historical helper imports listed above. It must not include private factories or implementation-only names.

Moving a class definition normally changes its `__module__` from `conformdag.models` to its owner (for example, `conformdag.models.policy`). That is the honest ownership result. Do not rewrite `__module__`, mutate Pydantic internals, or keep compatibility aliases that create second class objects. Characterization must establish the current reflection and pickle behavior. After the move, prove that legacy pickle globals naming `conformdag.models.<Class>` still resolve through the facade and that new owner-path pickle round trips work. New pickle byte paths may reflect the owner module; this is not a JSON or schema change. Record any unsupported reflective assumption rather than silently emulating the old implementation module.

## Pydantic behavior preservation

The split must preserve, verbatim unless a minimal import adaptation is necessary:

- `ConformModel` configuration (`extra="forbid"`, whitespace stripping) and all subclass configuration inheritance.
- Field order, type expressions, required/optional status, default values, factories, constraints, aliases, and serialization behavior.
- `PolicyConfiguration` and `GateRule` union member order, discriminators (`kind` and `type`), literal tags, and invalid-tag diagnostics.
- `Policy.valid_tags` and `PolicyPack.unique_policy_ids` validator names, ordering, messages, and returned values.
- Every list/dict default factory, including its independence across model instances.
- Pydantic's generated `$defs`, `$ref`, titles, discriminator mappings, validation errors, and JSON-mode conversions.

Cross-module annotations must resolve through direct imports in the owning module namespace. Retain `from __future__ import annotations` where present. Do not compensate for missing imports by weakening annotations, changing member order, changing model names, adding aliases to schemas, or changing Pydantic core-schema internals.

## Exact schema-byte baseline

The following SHA-256 values were captured from the seven checked-in files at the specified base. Stage B must preserve both these raw bytes and the exporter’s rendered output.

| Schema | SHA-256 |
| --- | --- |
| `schemas/policy-pack.json` | `dd6d7a46ada43036b37bdac53df158635f76bd64f1d309993c90ba286ccef143` |
| `schemas/project-config.json` | `7915a1880b803447c3d634d3be8d90d813898e6a15663ea338685b4c8ba35f3a` |
| `schemas/runtime-manifest.json` | `471a3e650fb037afd1d6993aae5d93e1552ceab552ff9422810e4ffc149779de` |
| `schemas/scan-report.json` | `ae1a33e78e0ab5a72a13f629cbcd91de6e3f64baf34af99e47142a2616486695` |
| `schemas/semantic-request.json` | `e63906384ae7bf2e450095481b4d7df43276277a64dbafe5e9c52379c8e3d59f` |
| `schemas/semantic-response.json` | `b26267fa206e994ccfd741c903a35ae2d222ff475416d86d195b47e35cefec75` |
| `schemas/suppression.json` | `0ef3eb979cb76d384db1407edca057485069031dc6a8d2086244b17166bdd529` |

`scripts/export_schemas.py` stays unchanged and continues to import the public facade. `mise run schema` is the required read-only parity check. Do not run `mise run schema:update` to normalize or bless a mismatch. Any byte/hash difference is a stop-and-review condition, not authorization to alter a schema.

## Existing verification anchors

The implementation plan reuses existing consumer tests rather than weakening or replacing them:

- `tests/test_models.py`, `tests/test_policy.py`, and `tests/test_gates.py` cover model validation, tag and ID validators, policy configuration and gate discriminators, legacy baseline call forms, and result behavior.
- `tests/test_fixing.py::test_report_schema_stays_backward_compatible` and scan/report round trips cover v1/v2 report payloads.
- `tests/fingerprints/test_deterministic_contract.py`, `test_semantic_contract.py`, `test_report_contract.py`, and `test_consumer_contract.py` pin C19 identities and the frozen C18 report fingerprint.
- `tests/test_baselines.py`, `tests/test_gates.py`, `tests/test_platform.py`, and `tests/application/test_scan.py` cover C20 baseline values, eligibility, gate use, and compatibility.
- `tests/test_distribution.py` is the existing sdist/wheel smoke-test location; extend it to prove the new package and the root facade import from an installed wheel.
- `tests/test_policy.py::test_policy_package_import_has_no_cycles_or_repository_side_effects` is a pattern for a fresh-process import smoke test.

The new package-boundary tests should live under `tests/models/` because they verify the model package’s ownership, facade, module order, and schema-byte contract. Existing suite organization otherwise remains unchanged.

## Completion and stop conditions

Stage B is complete only when all design-plan tasks pass, the seven schemas are byte-identical, C18/C19/C20 contracts remain unchanged, packaging imports succeed, and all required local/hosted checks pass. The implementation PR must set C21 to `review`, not `accepted`; acceptance requires a separate post-implementation documentation PR after merge and successful post-merge CI.

Stop for independent review or a design decision if any of these occur:

- A baseline public symbol, class identity, import path, pickle path, validation result, error, dump, field order/default, fingerprint, or consumer projection changes unexpectedly.
- Any schema hash or `mise run schema` result differs, or regeneration is proposed.
- A cycle, facade back-edge, dependency on an adapter, package shadowing, or missing direct-owner import appears.
- Verification requires production behavior, a schema, a migration, or an API change outside this scope.
- The final diff includes anything beyond the approved model modules, focused tests, and the C21 `review` ledger evidence.
