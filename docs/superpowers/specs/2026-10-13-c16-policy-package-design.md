# C16 — Policy Package Decomposition

**Status:** Proposed for one docs-PR review
**Planning baseline:** `main@533c5c01616625ce6e04f549d3ff74dc0058f81b`
**Predecessor:** C15 — accepted
**Successor:** C17 — Canonical Policy Editing

## 1. Objective

Replace `src/conformdag/policy.py` with a cohesive `conformdag.policy` package while preserving observable policy behavior and public imports. C16 is a behavior-preserving extraction of responsibilities, not a functional policy change.

The extraction establishes explicit ownership for loading, provenance, validation, and hashing; makes future C17 policy editing safer; and removes unrelated responsibilities from one module. The planning-baseline module is 228 lines, so file size alone is not the justification.

### Success criteria

- One authoritative policy-loading implementation.
- One provenance-validation implementation.
- One policy and quality-gate validation implementation.
- One pair of canonical policy hash functions.
- Every previous public symbol remains available at `conformdag.policy`.
- Existing error types, signatures, messages, ordering, and hashing behavior are retained.
- No policy schema, JSON schema, HTTP contract, or database migration changes.
- Existing policy editing remains in `platform.packs` until C17.

## 2. Baseline inventory

At the planning baseline, `src/conformdag/policy.py` contains:

- `PolicyValidationError`
- `_yaml`
- `_read_yaml`
- `resolve_policy_pack_path`
- `resolve_configured_policy_pack`
- `resolve_source_document`
- `load_policy_pack`
- `validate_policy_pack`
- `select_policy_pack`
- `validate_policy_provenance`
- `active_policies`
- `_policy_hash`
- `policy_contract_hash`
- `policy_enforcement_hash`
- `load_suppressions`

Key consumers include the application scanning workflow, CLI, checks/evaluator integration, pack pulling, platform pack management, semantic evaluation, and policy tests.

## 3. Target package and ownership

```text
src/conformdag/
└── policy/
    ├── __init__.py
    ├── loading.py
    ├── provenance.py
    ├── validation.py
    └── hashes.py
```

Remove `src/conformdag/policy.py` only after import and behavior parity are proven.

### `loading.py`

Own:

- `_yaml`
- `_read_yaml`
- `PolicyValidationError`
- `resolve_policy_pack_path`
- `resolve_configured_policy_pack`
- `load_policy_pack`
- `select_policy_pack`
- `load_suppressions`

Keep the current policy-loading sequence:

1. Read YAML.
2. Require a mapping.
3. Validate the `PolicyPack` model.
4. Resolve the pack/repository roots.
5. Collect provenance issues.
6. Collect policy/quality-gate issues.
7. Raise the same aggregate `PolicyValidationError` if necessary.
8. Otherwise return the validated pack.

Do not change exceptions or issue ordering. Keep suppression loading in `loading.py` for C16. It is an existing YAML input operation; broader suppression ownership changes are deferred to C18/C20.

### `provenance.py`

Own:

- `resolve_source_document`
- `validate_policy_provenance`

Preserve source-document resolution order:

1. Relative to the pack directory.
2. Relative to the pack directory's parent.
3. Relative to the repository root.
4. Existing repository-root fallback.

Preserve the existing checks for missing files, UTF-8 read failures, section presence, and SHA-256 content hashes. Do not normalize or rewrite source documents or their content hashes.

### `validation.py`

Own:

- `validate_policy_pack`
- `active_policies`

Retain quality-gate validation, policy configuration checks, Ruff selector validation, and deterministic-check catalogue validation. Preserve lazy imports needed to avoid import cycles with checks, evaluator, gates, and Ruff.

Do not introduce an independent check catalogue. Do not move Pydantic model validation out of `conformdag.models`.

### `hashes.py`

Own:

- `_policy_hash`
- `policy_contract_hash`
- `policy_enforcement_hash`

Preserve the exact normalization and digest calculation:

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"))
```

Encode as UTF-8 and calculate SHA-256. The policy contract hash must continue to include the same fields:

- `id`
- `title`
- `severity`
- `scope`
- `invariant`
- `safe_path`
- `exceptions`
- `configuration`

The enforcement hash must continue to derive from `policy.enforcement.model_dump(mode="json")`. No additional fields, hash prefix, version, or salt are allowed.

### `__init__.py` compatibility facade

Explicitly re-export every previously public policy symbol with the same callable identity where practical. Avoid duplicating implementations in the facade.

Private helpers remain private; move or re-export them only where required by internal implementation or observed compatibility. Document this import compatibility seam:

- **Why:** support established `conformdag.policy` imports.
- **Introduced:** C16.
- **Removal:** not automatically scheduled; reevaluate only through the C30 compatibility audit.
- **Canonical implementation ownership:** the respective policy submodule.

## 4. Dependency rules

Permitted package dependency relationships:

```text
loading → provenance, validation, models, bundled
provenance → models
validation → models and existing lazily imported validators
hashes → models
__init__ → package re-exports
```

`validation.py` must not import `loading.py` solely to obtain the shared error type. `loading.py` must not import from its public `policy.__init__` facade. Avoid importing all sibling modules at module initialization when a direct submodule import is possible.

There must be no dependency on FastAPI, Typer, SQLAlchemy, platform routes, or persistence.

## 5. Compatibility and behavioral invariants

### Public imports and signatures

Existing imports such as the following must continue to work:

```python
from conformdag.policy import (
    PolicyValidationError,
    load_policy_pack,
    validate_policy_pack,
    validate_policy_provenance,
    policy_contract_hash,
)
```

The following must retain signatures and observable behavior:

- `resolve_policy_pack_path`
- `resolve_configured_policy_pack`
- `resolve_source_document`
- `load_policy_pack`
- `select_policy_pack`
- `validate_policy_provenance`
- `validate_policy_pack`
- `active_policies`
- `load_suppressions`
- `policy_contract_hash`
- `policy_enforcement_hash`

### Errors and validation

Preserve exception type, `PolicyValidationError.issues`, message formatting, issue order, validation order, malformed YAML handling, missing-file handling, duplicate policy ID rejection, invalid deterministic-check rejection, invalid quality-gate reference handling, invalid Ruff selectors, and unsupported configuration handling.

### Bundled packs and aliases

Preserve `community` and any other existing bundled alias resolution. Do not introduce new relative-path resolution rules.

### Suppressions

Preserve missing-file behavior, empty YAML handling, mapping/list formats, and Pydantic validation. Do not move suppression application semantics or alter matching, expiry, or duplicate diagnostics.

### Hashes

Golden hash fixtures must match before and after extraction. Compare exact digest strings, not merely digest length.

### Import-time behavior

Importing `conformdag.policy` must not write files, access the network, execute user repository Python, load arbitrary packs, or introduce a new import cycle.

## 6. Explicit non-goals

C16 excludes:

- C17 policy/gate editing extraction;
- policy schema modifications;
- quality-gate semantics changes;
- check-catalogue restructuring;
- new policy-pack formats;
- policy registry redesign;
- suppression application refactoring;
- pack distribution or Git-pull refactoring;
- platform PackService mutation changes;
- HTTP/API changes;
- frontend changes;
- database migrations;
- model training or semantic-provider changes;
- dependency upgrades;
- C18 reporting extraction;
- C20 baseline/suppression changes;
- C30 compatibility removal.
