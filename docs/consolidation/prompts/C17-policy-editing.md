# C17 — Extract Canonical Policy Editing

## Role and objective

You are the Build agent for C17. Move policy and quality-gate mutation semantics out of the platform pack adapter into a reusable policy editing service that CLI, platform, and future MCP can share.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C03/C12/C16.
- `src/conformdag/platform/packs.py`, `src/conformdag/platform/app.py` pack routes, `src/conformdag/policy.py` or `policy/` after C16, and `src/conformdag/models.py`.
- `tests/test_platform.py` pack CRUD/mutation/atomicity tests and `tests/test_policy.py`.

## Current ownership and resulting owner

`PackService` currently owns registration/locking and mutation semantics. After this PR, `policy/editing.py` owns canonical `upsert_policy()`, `delete_policy()`, `upsert_gate()`, and `delete_gate()` operations; `PackService` remains the registration/snapshot/locking adapter.

## Interfaces

Define typed `PolicyMutation`/gate mutation inputs and functions such as:

```python
def upsert_policy(pack_path: Path, policy_id: str, mutation: PolicyMutation) -> PolicyPack: ...
def delete_policy(pack_path: Path, policy_id: str) -> PolicyPack: ...
def upsert_gate(pack_path: Path, gate_id: str, mutation: GateMutation) -> PolicyPack: ...
def delete_gate(pack_path: Path, gate_id: str) -> PolicyPack: ...
```

The functions load YAML, resolve provenance, calculate hashes, preserve immutable metadata, validate the resulting whole pack, atomically write, and return the validated pack.

## Expected files

- Create: `src/conformdag/policy/editing.py`, focused `tests/policy/test_editing.py`.
- Modify: `src/conformdag/platform/packs.py`, platform routes/services, and existing mutation tests.
- Do not add an MCP adapter or change HTTP paths.

## Test-first sequence

1. Move/add tests for policy/gate add/update/delete, provenance, source section/hash, invalid whole-pack rejection, metadata preservation, and atomic temp/replace cleanup.
2. Run focused tests against the current `PackService` behavior.
3. Implement canonical editing functions and make `PackService` delegate while retaining its lock/snapshot responsibility.
4. Run policy editing, platform pack, concurrent update, and validation tests.
5. Run `mise run check`, coverage, pack validation, and privacy checks.

## Allowed changes

- Canonical policy/gate mutation functions, typed mutation inputs, PackService delegation, and tests.

## Non-goals and prohibitions

- Do not let FastAPI or SQLAlchemy enter `policy.editing`.
- Do not permit partial writes, stale provenance, gate references to missing policies, or raw unvalidated YAML to escape.
- Do not duplicate mutation semantics in CLI or future adapters.

## Verification matrix

- `tests/policy/test_editing.py` and existing platform pack tests.
- Atomic-write failure injection and concurrent update tests.
- `mise run check`, coverage, and pack validation.
- Independent review of immutable metadata and unchanged-on-rejection bytes.

## Completion checklist and handoff

- [ ] Policy and gate edits have one reusable owner.
- [ ] Writes are atomic and whole-pack validation is mandatory.
- [ ] PackService is an adapter, not a second editor.
- [ ] Commit with `refactor: extract policy editing service`; open the PR without merging.
