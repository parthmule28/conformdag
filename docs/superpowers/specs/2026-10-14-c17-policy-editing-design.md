# C17 — Canonical Policy Editing Design

## Goal

Move policy and quality-gate mutation semantics from `platform.packs.PackService` into a reusable, transport-independent policy editing service. Platform remains an adapter; policy edits have one canonical owner.

## Ownership and dependency boundary

- `src/conformdag/policy/editing.py` owns policy and gate upsert/delete semantics, provenance refresh, whole-pack validation, and atomic YAML replacement.
- `PackService` continues to own registration, pack-name-to-path lookup, snapshots/reads, and its current `RLock`. It delegates edits while holding that lock and maps policy editing errors to the existing platform errors.
- `policy.editing` may depend on policy models and policy loading/provenance/validation helpers. It must not import FastAPI, SQLAlchemy, or platform modules.
- HTTP routes and wire contracts remain unchanged. No CLI or MCP adapter is added in this slice.

## Typed mutation contracts and operations

Define static `TypedDict` inputs in `policy.editing` so adapters pass typed values without making the policy layer depend on transport DTOs:

- `PolicyMutation` requires `title`, `version`, `status`, `severity`, `source_document`, `source_section`, and `invariant`. Optional fields mirror the existing request vocabulary: `source_version`, `ownership`, `scope`, `exceptions`, `enforcement`, `safe_path`, `tags`, `deterministic_checks`, `configuration`, `check_kind`, and `check_config`. To preserve direct `PackService` callers, it also accepts optional `id` and `airflow_profiles`; the path ID remains authoritative, and an existing policy retains its stored profiles. Optional nullable values are treated as omitted, matching the current route's `exclude_none=True` behavior.
- `GateMutation` requires `rules: list[GateRule | dict[str, object]]` and permits an optional `id` solely for the existing mismatch check. The typed mapping option preserves direct callers that supply rule payload dictionaries; `QualityGate.model_validate` validates those values before writing.

The editing API is:

```python
def upsert_policy(pack_path: Path, policy_id: str, mutation: PolicyMutation) -> PolicyPack: ...
def delete_policy(pack_path: Path, policy_id: str) -> PolicyPack: ...
def upsert_gate(pack_path: Path, gate_id: str, mutation: GateMutation) -> PolicyPack: ...
def delete_gate(pack_path: Path, gate_id: str) -> PolicyPack: ...
```

Each function loads the pack through the canonical loader, applies one edit, verifies provenance and validates the complete resulting pack, atomically replaces the YAML file, then returns the validated `PolicyPack`. These functions do not provide locking; callers that coordinate shared pack state must serialize operations. `PackService` keeps the current in-process lock behavior.

## Behavior to preserve

- Policy upsert resolves the source document using existing pack/repository-relative lookup, requires the requested source section, and refreshes the SHA-256 hash from the complete UTF-8 document.
- Policy updates retain omitted contract metadata and tags; new policies require complete `ownership`, `scope`, `exceptions`, and `enforcement` metadata. Canonical and legacy configuration vocabulary stays conflict-checked and only canonical fields are persisted.
- Gate IDs come from the path argument; a supplied mismatching ID is rejected. Upserts replace in place or append, preserving other member order.
- Deleting a missing policy or gate raises a typed editing not-found error. Whole-pack validation rejects deleting a policy still referenced by a gate and rejects invalid gate references.
- Validation and write failures leave the original file bytes unchanged. YAML replacement uses a unique temporary file in the pack directory, `os.replace`, and cleanup on failures.
- Existing route authentication, paths, status codes, payloads, and OpenAPI schemas remain stable.

## Errors and adapter mapping

`policy.editing` defines a `PolicyEditingError` for invalid requested edits and a `PolicyMemberNotFoundError` for deleting a missing policy or gate. Existing `PolicyValidationError` from loading remains a policy-layer error. `PackService` translates the typed editing errors to `PackError` / `PackNotFoundError`; route handlers retain their current HTTP mappings.

## Scope and acceptance

- Add `src/conformdag/policy/editing.py` and focused `tests/policy/test_editing.py` coverage.
- Update `platform.packs` and the narrow route-to-service payload conversion; preserve existing platform behavior and concurrency guarantees.
- Do not change model schemas, database migrations, HTTP paths, auth, evaluator semantics, or frontend/API contracts.
- Confirm atomic failure behavior, provenance/hash refresh, metadata preservation, full-pack validation, and lock-serialized concurrent updates.
- Run focused policy/platform tests, `mise run check`, `mise run test:coverage`, `mise run validate:packs`, and `mise run privacy`.
- Open an implementation PR and leave it open and unmerged.
