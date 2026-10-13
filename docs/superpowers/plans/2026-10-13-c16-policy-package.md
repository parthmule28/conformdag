# C16 — Policy Package Decomposition: Implementation Plan

**Status:** Proposed for one docs-PR review
**Planning baseline:** `main@533c5c01616625ce6e04f549d3ff74dc0058f81b`
**Design:** [C16 Policy Package Decomposition](../specs/2026-10-13-c16-policy-package-design.md)
**Predecessor:** C15 — accepted
**Successor:** C17 — Canonical Policy Editing
**Implementation mode:** OpenCode, `superpowers:executing-plans`, native/single-session, sequential execution

## Objective and guardrails

Replace `src/conformdag/policy.py` with the `conformdag.policy` package while preserving observable behavior and public imports. This is a responsibility extraction, not a policy-semantics redesign. The [design specification](../specs/2026-10-13-c16-policy-package-design.md) is authoritative for module ownership, dependency rules, compatibility requirements, and non-goals.

Do not move policy editing out of `platform.packs`; that belongs to C17. Do not change schemas, behavior, API contracts, frontend, persistence, or dependencies. The documentation PR does not authorize beginning implementation.

## Numbered implementation tasks

### Task 1 — Characterize existing behavior

Before editing source, inspect:

- `AGENTS.md`
- `docs/consolidation/architecture-rules.md`
- `docs/consolidation/progress.md`
- `docs/consolidation/prompts/C01-*.md`
- `docs/consolidation/prompts/C16-policy-package.md`
- `docs/consolidation/prompts/C17-policy-editing.md`
- the full `src/conformdag/policy.py`
- every direct and dynamic importer of `conformdag.policy`
- policy, CLI, platform, packpull, distribution, and quality-gate tests
- bundled and organizational pack fixtures

Record the baseline import surface and existing test results.

### Task 2 — Write RED characterization tests

Add tests proving:

1. Public import parity.
2. Public callable signatures.
3. `PolicyValidationError` semantics.
4. YAML errors.
5. Path and bundled alias resolution.
6. Policy pack selection and ambiguity errors.
7. Provenance candidate precedence.
8. Source section and SHA-256 checking.
9. Validation issue contents and order.
10. Active policy filtering.
11. Suppression list/mapping/empty/missing behavior.
12. Golden policy contract/enforcement hashes.
13. Import safety and absence of cycles.

Tests introduced for the target package should fail before extraction where they depend on the new submodule paths. Existing characterization tests must remain green.

### Task 3 — Create the package

Introduce:

```text
policy/__init__.py
policy/loading.py
policy/provenance.py
policy/validation.py
policy/hashes.py
```

Move implementations without reformulating algorithms. Preserve the existing `ruamel.yaml` typing suppression where required. Avoid unnecessary changes to importers.

### Task 4 — Establish the facade

Explicitly re-export old public names through `policy/__init__.py`. Confirm:

- `from conformdag.policy import ...` works;
- CLI imports work;
- platform imports work;
- package distribution imports work;
- no import cycle occurs.

Delete the old `policy.py` only once the package fully replaces it.

### Task 5 — Verify behavioral parity

Use baseline and extracted-package results to compare:

- exception types/messages and `.issues`;
- exact SHA-256 digests;
- validation issue sequences;
- bundled path results;
- suppression deserialization;
- loaded model values.

Do not approve intentional behavior differences as part of C16.

### Task 6 — Test integration boundaries

Run the existing policy, scan, pack, CLI, platform, distribution, semantic, and agent tests affected by policy imports. Ensure packaged wheel and source distribution include the new package. Add a distribution smoke test if existing tests do not already prove the import from an installed artifact.

### Task 7 — Review ownership and scope

Perform an ownership audit:

- no duplicate pack loaders;
- no duplicate hash algorithms;
- no duplicate provenance validators;
- validation retains the authoritative check catalogue;
- no C17 mutation extraction;
- no migration or schema change;
- no unnecessary importer rewrites.

### Task 8 — Full verification

Run:

```text
mise run setup
mise run validate:packs
mise run check
mise run test:coverage
mise run privacy
mise run schema
mise run build
git diff --check
```

`mise run schema` is the repository's checked-in schema verification task. Do not regenerate schemas unless a separately reviewed need is established.

Run focused tests using the actual repository test paths, including `tests/test_policy.py`, `tests/test_cli.py`, `tests/test_platform.py`, `tests/test_distribution.py`, and relevant pack, scan, and semantic tests.

Required coverage is at least the existing 90% gate. Do not accept an unexplained material coverage regression.

### Task 9 — Independent whole-branch review

Review against the pre-C16 baseline. Prioritize:

- import/export parity;
- accidental circular imports;
- loader ordering;
- YAML exception semantics;
- provenance fallback changes;
- hash changes;
- quality-gate validation;
- suppressed/private helper changes;
- packaged-wheel inclusion;
- unintended policy editing movement.

Fix all Critical and Important findings and rerun affected tests.

### Task 10 — Implementation PR

Create `feat/c16-policy-package` and open one implementation PR against accepted `main`. Wait for exact-head CI, including Fast checks, macOS, Airflow runtime, browser journeys, offline benchmark, and Release validation. Opt-in semantic smoke may remain skipped.

Once independently reviewed and green, add one separate C16 review-ledger commit to `docs/consolidation/progress.md`. Verify that the final product-head-to-final-head file delta contains only the ledger update. Stop with the implementation PR unmerged.

## Completion criteria

C16 is ready for merge only when:

- package ownership matches the approved design;
- old imports work;
- no behavior changes are observed;
- golden hashes match;
- policy provenance and validation results match;
- suppression loading matches;
- no duplicate authority exists;
- no C17 scope is included;
- all relevant tests pass;
- schema and package builds pass;
- independent review has no unresolved Critical or Important findings;
- final-head CI is green;
- the review ledger is accurate;
- the implementation PR remains unmerged until explicitly authorized.

## Post-merge acceptance

After an authorized implementation merge:

1. Verify the merge SHA.
2. Verify post-merge `main` CI.
3. Create a docs-only acceptance PR.
4. Change the C16 ledger status `review → accepted`.
5. Record product, review, final, and merge SHAs plus CI evidence.
6. Stop with the acceptance PR unmerged until separately authorized.
7. Once accepted and verified on `main`, begin C17.
