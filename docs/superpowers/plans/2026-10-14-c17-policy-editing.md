# C17 Policy Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Follow the user's sequential, no-delegation preference.

**Goal:** Extract the canonical policy and quality-gate mutation workflow into `conformdag.policy.editing` while preserving platform behavior.

**Architecture:** The policy module owns typed edits, provenance/hash refresh, whole-pack validation, and atomic YAML replacement. `PackService` retains pack registration, snapshots, and its `RLock`, delegates mutations, and translates policy errors for unchanged routes.

**Tech Stack:** Python 3.12, Pydantic 2 domain models, ruamel.yaml, pytest, FastAPI platform adapter.

**Spec:** `docs/superpowers/specs/2026-10-14-c17-policy-editing-design.md`

## Global Constraints

- “Do not let FastAPI or SQLAlchemy enter `policy.editing`.”
- “Do not permit partial writes, stale provenance, gate references to missing policies, or raw unvalidated YAML to escape.”
- “Do not duplicate mutation semantics in CLI or future adapters.”
- “Do not add an MCP adapter or change HTTP paths.”
- “PackService remains the registration/snapshot/locking adapter.”
- Keep changes limited to the approved C17 scope; no schema, migration, frontend, evaluator, or auth changes.
- Keep the implementation PR open and unmerged.

## Review Focus

- Source document missing, unreadable, missing the requested section, or newly selected during an upsert: assert rejection or the exact recomputed hash and unchanged bytes on rejection in Task 1.
- Policy update omissions, new-policy completeness, and canonical/legacy vocabulary conflicts: assert preservation/rejection in Task 1.
- Deleting a policy still referenced by a gate or adding a gate with unknown policy IDs: assert whole-pack rejection and unchanged bytes in Task 2.
- Temporary-file write or `os.replace` failure: assert original bytes survive and temp files are removed in Task 4.
- Concurrent edits and reads through one `PackService`: assert serialized snapshots and no lost distinct updates in Task 4.

**Baseline evidence:** On accepted `main@017a6c7d4ef1f51ef085e560005ff3a70cc2687a`, `mise run check` passed: 831 tests passed, 19 deselected, and Pyright reported 0 errors.

---

### Task 1: Extract policy upsert and provenance editing

**Files:**
- Create: `src/conformdag/policy/editing.py`
- Create: `tests/policy/test_editing.py`

**Interfaces:**
- Define `PolicyMutation` as a `TypedDict` with required `title`, `version`, `status`, `severity`, `source_document`, `source_section`, and `invariant` strings. Use `NotRequired` for optional fields: string fields `id`, `source_version`, `safe_path`, and `check_kind`; string lists `airflow_profiles`, `tags`, and `deterministic_checks`; object mappings `ownership`, `scope`, `exceptions`, `enforcement`, `configuration`, and `check_config`. Optional nullable fields accept `None` as omitted. `id` is overridden by the path ID; existing policies retain persisted `airflow_profiles`.
- Define `PolicyEditingError(ValueError)` and `PolicyMemberNotFoundError(PolicyEditingError)`.
- Produce `upsert_policy(pack_path: Path, policy_id: str, mutation: PolicyMutation) -> PolicyPack`.
- Produce `_write_pack(pack: PolicyPack, path: Path) -> None` in `policy.editing`, because policy upsert must write without importing the platform adapter.
- Reuse `load_policy_pack`, `resolve_source_document`, `validate_policy_provenance`, and `validate_policy_pack`; do not import platform or transport contracts.

- [x] **Step 1: Run existing PackService characterization tests before extraction.** Run `mise exec -- uv run pytest tests/test_platform.py::test_pack_service_upsert_and_delete tests/test_platform.py::test_pack_service_delete_rejects_gate_reference_and_preserves_bytes tests/test_platform.py::test_pack_service_gate_crud_preserves_order_and_round_trips tests/test_platform.py::test_gate_mutation_rejects_invalid_reconstructed_pack_and_preserves_bytes -x --tb=short`. Expected: all pass against current behavior.
- [x] **Step 2: Add direct policy-editing tests** named `test_upsert_policy_refreshes_source_hash_and_preserves_omitted_metadata`, `test_upsert_policy_requires_complete_metadata_for_new_policy`, `test_upsert_policy_rejects_missing_source_section_without_write`, `test_upsert_policy_rejects_missing_source_document_without_write`, `test_upsert_policy_rejects_unreadable_source_without_write`, `test_upsert_policy_rejects_conflicting_configuration_vocabulary_without_write`, and `test_upsert_policy_rejects_invalid_whole_pack_without_write`.
- [x] **Step 3: Run the tests to confirm the new API is absent.** Keep imports inside a helper called from each test so pytest reports a failing test (not a collection error). Run: `mise exec -- uv run pytest tests/policy/test_editing.py -x --tb=short`. Expected: the first test fails with the helper's explicit “editing module is not implemented” assertion.
- [x] **Step 4: Implement `PolicyMutation`, the editing errors, `_write_pack`, and `upsert_policy`** in `src/conformdag/policy/editing.py`. Preserve current merge rules, source lookup order, whole-pack validation, hash behavior, and atomic replacement; return the written, validated pack only after all validation succeeds.
- [x] **Step 5: Run `mise exec -- uv run pytest tests/policy/test_editing.py -x --tb=short`.** Expected: all Task 1 policy editing tests pass.

### Task 2: Add policy deletion and quality-gate edits

**Files:**
- Modify: `src/conformdag/policy/editing.py`
- Modify: `tests/policy/test_editing.py`

**Interfaces:**
- Define `GateMutation` as a `TypedDict` requiring `rules: list[GateRule | dict[str, object]]` and allowing optional `id: str | None`.
- Produce `delete_policy(pack_path: Path, policy_id: str) -> PolicyPack`, `upsert_gate(pack_path: Path, gate_id: str, mutation: GateMutation) -> PolicyPack`, and `delete_gate(pack_path: Path, gate_id: str) -> PolicyPack`.
- Missing member deletion raises `PolicyMemberNotFoundError`; invalid resulting packs raise `PolicyEditingError`.

- [x] **Step 1: Add tests** named `test_delete_policy_rejects_gate_reference_without_write`, `test_gate_upsert_replaces_or_appends_without_reordering_other_gates`, `test_gate_upsert_rejects_mismatched_id_and_unknown_policy`, and `test_delete_missing_policy_or_gate_raises_typed_error`.
- [x] **Step 2: Run the focused tests and confirm they fail** because the three operations are not implemented.
- [x] **Step 3: Implement the three operations** in `editing.py`, validating the entire pack before any write and returning the validated result.
- [x] **Step 4: Run the policy editing tests.** Expected: all four operations and rejection cases pass; pack bytes remain unchanged on rejected edits.

### Task 3: Delegate from PackService and remove adapter-owned editing

**Files:**
- Modify: `src/conformdag/policy/editing.py`
- Modify: `src/conformdag/platform/packs.py`
- Modify: `src/conformdag/platform/routes/packs.py`
- Modify: focused tests in `tests/test_platform.py` and `tests/policy/test_editing.py`.

**Interfaces:**
- Keep `_write_pack(pack: PolicyPack, path: Path) -> None` as the sole atomic YAML writer in `policy.editing`; remove the duplicate platform writer and mutation helpers.
- `PackService` keeps existing public method names and the `RLock`; its mutation methods take the typed mutation inputs, call the editor under the lock, and map `PolicyMemberNotFoundError` to `PackNotFoundError` and `PolicyEditingError` to `PackError`.
- Route payloads are converted to those typed inputs without changing `PolicyUpsertRequest`, `GateUpsertRequest`, OpenAPI schema, routes, auth, or response models.

- [x] **Step 1: Add an adapter delegation/error-mapping test** named `test_pack_service_delegates_mutations_and_maps_editing_errors`, using monkeypatched editor operations to verify delegation and legacy `PackError`/`PackNotFoundError` translation. Retain existing route tests for HTTP success, 404/422 mappings, auth, canonical persisted vocabulary, and OpenAPI parity.
- [x] **Step 2: Run the focused policy/platform tests** and confirm the new delegation expectations fail before implementation.
- [x] **Step 3: Delegate all four `PackService` mutation methods** to `policy.editing`, remove duplicated merge/validation/write semantics from `platform.packs`, add route-side typed payload conversion, and retarget existing writer imports/monkeypatches to `policy.editing` before removing the platform writer.
- [x] **Step 4: Run `mise exec -- uv run pytest tests/policy/test_editing.py tests/test_platform.py -x --tb=short`.** Expected: all direct editor and adapter regressions pass with unchanged HTTP behavior.

### Task 4: Prove atomic writes, lock semantics, and full gates

**Files:**
- Modify: `tests/policy/test_editing.py`
- Modify: `tests/test_platform.py` to target atomic-write tests at the policy-owned writer and retain `PackService` concurrency tests.

**Interfaces:**
- The editor itself performs atomic replacement but no locking; concurrent registered-pack operations remain serialized by `PackService._lock`.
- The policy-owned writer is `_write_pack(pack: PolicyPack, path: Path) -> None`.

- [x] **Step 1: Run the existing failure-injection tests** for temporary write and replace failures against the policy-owned writer. Run the five `test_write_pack_*` cases in `tests/test_platform.py`; expected: all pass and assert unchanged source bytes plus temporary-file cleanup on failures.
- [x] **Step 2: Inspect the failure-injection assertions** in those tests. Expected: replace, model-dump, and temp-write failures each assert the original bytes survive and no unique temp file remains; successful writes assert replacement and cleanup.
- [x] **Step 3: Run the snapshot and concurrency tests** `test_pack_service_serializes_snapshot_reads_with_writes` and `test_concurrent_policy_updates_do_not_lose_changes`. Expected: both pass against delegated editor operations.
- [x] **Step 4: Run focused verification:** `mise exec -- uv run pytest tests/policy/test_editing.py tests/test_platform.py -x --tb=short`, then `mise run test:coverage`, `mise run validate:packs`, `mise run privacy`, and `mise run check`. Expected: focused tests and each full gate exit zero; coverage is at least 90%.
- [x] **Step 5: Run `git diff --check` and inspect the dependency boundary.** Confirm the only changed product area is policy editing plus its platform adapter/tests, no route/schema/migration changes were introduced, and no untracked `.serena/` data is staged.
