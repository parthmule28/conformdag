# C19 — Fingerprint Contracts: Sequential TDD Plan

**Baseline:** `main@df6d2dde7165366fe24fd66599284aa84a40f3d2`\
**Design:** `docs/superpowers/specs/2026-10-16-c19-fingerprint-contract-design.md`\
**Canonical contract:** `docs/architecture/fingerprints.md`

**Execution:** Sequential Codex implementation. No subagent delegation. ChatGPT owns all design decisions and plan changes.

## Global constraints

- Preserve every existing fingerprint value and hashing algorithm.
- Make no production-code changes unless an unexpected compatibility defect is independently reviewed and explicitly approved.
- Do not add decorative version constants, report schema fields, or new hashing helpers.
- Preserve legacy import paths and existing tests.
- Leave C20 planned and untouched.
- Do not merge without explicit authorization.

## Task 1 — Baseline and characterization

**Files:** No product changes.

1. Verify the approved C19 documentation is merged into `main`.
2. Create a clean isolated implementation worktree.
3. Read the design, canonical contract, `checks/common.py`, `semantic_evaluator.py`, and `reporting/normalize.py`.
4. Run the existing evaluator, semantic, reporting, gates, fixing, and application tests.
5. Record the C18 frozen report fingerprint and current full test baseline.

**Acceptance:** The existing suite passes before C19 test modifications. Record the exact base SHA and any existing warnings.

## Task 2 — Deterministic finding contract tests

**Create:** `tests/fingerprints/test_deterministic_contract.py`

Test the exact existing contract:

1. Use a fixed policy and an explicit policy version, path, anchor, and status.
2. Calculate an independent expected SHA-256 digest from the documented five-field UTF-8 string.
3. Assert `structural_fingerprint()` matches the independent digest.
4. Assert repeated calls produce the same digest.
5. Assert changing each of policy ID, policy version, path, anchor, or status individually changes the digest for the chosen fixture.
6. Verify that changing an external source-line variable without changing the anchor preserves the digest.
7. Verify that changing a line number embedded in an anchor changes the digest.
8. Cover at least one existing Ruff-style line-dependent anchor.
9. Preserve the `conformdag.evaluator.structural_fingerprint` compatibility import.

Tests must characterize current behavior rather than assume universal structural stability.

**Acceptance:** All tests pass without changing production fingerprint functions.

## Task 3 — Semantic finding contract tests

**Create:** `tests/fingerprints/test_semantic_contract.py`

Use existing synthetic policy/context fixtures and deterministic `SemanticResponse` instances.

Verify:

1. Repeatability with identical inputs.
2. Changes to policy ID/version, normalized status, source path, citation location, citation criterion, or unresolved flag can change the digest.
3. Citation input reordering does not change the digest when the normalized citation set is otherwise identical.
4. Provider explanation, confidence, remediation, and citation excerpt changes do not change the semantic finding fingerprint when normalized identity inputs remain fixed.
5. Source context changes unrelated to the included citation identities do not alter semantic finding identity.
6. An `AIR-SEM-001` response whose normalized status changes because of missing evidence produces the expected identity difference.
7. Compare at least one result with an independently constructed canonical JSON/SHA-256 oracle, not merely a second call to the implementation.

Do not call live providers or persist sensitive responses.

**Acceptance:** New tests and existing `tests/test_semantic_evaluator.py` remain green.

## Task 4 — Report fingerprint contract tests

**Create:** `tests/fingerprints/test_report_contract.py`

Reuse the fixed report factory and frozen baseline from `tests/reporting/`.

Verify:

1. The exact C18 fingerprint remains `8050ab09ad677b729bc5287e99347713afc10bf0d87957066b1494442f034e26`.
2. The complete normalized JSON remains equal to the existing frozen baseline.
3. Run timestamp, previous result fingerprint, gate result, and excluded run metadata do not affect the report digest.
4. Order-independent collections and mappings hash identically under their existing sort rules.
5. Finding status, serialized explanation, evidence, suppression provenance, issue message, runtime observation, and input hashes affect the digest when changed independently.
6. A semantic finding may retain its fingerprint across an explanation change while the containing report fingerprint changes.
7. Applying a suppression retains the matched finding fingerprint but changes the normalized report fingerprint when the serialized finding changes.
8. `normalize_report()` does not mutate its input.
9. The existing `report_version` and JSON schema remain unchanged.

Use explicit comparison fixtures. Do not regenerate the golden values to accommodate a failure.

**Acceptance:** Existing and new normalization tests pass with unchanged production logic.

## Task 5 — Consumer compatibility regression

**Create:** `tests/fingerprints/test_consumer_contract.py` if useful.

Exercise the existing public APIs:

1. A suppression matches a finding by its existing `(policy_id, fingerprint)` pair.
2. A no-new-findings gate recognizes existing finding fingerprints in a baseline.
3. A new finding fingerprint is recognized as new.
4. Suppression does not silently redefine finding identity.
5. Gate evaluation behavior and report identity remain separate.
6. Existing report exports still display or serialize the expected identity values.

Reuse `tests/test_gates.py`, `tests/test_reporting.py`, and existing application/platform tests rather than duplicating extensive integration fixtures.

**Acceptance:** No changes to suppression, baseline, gate, or transport implementation.

## Task 6 — Full verification and implementation PR

Run:

```bash
mise run setup
mise exec -- uv run pytest tests/fingerprints tests/reporting tests/test_evaluator.py tests/test_semantic_evaluator.py tests/test_gates.py tests/test_fixing.py -m 'not runtime' -x --tb=short
mise run check
mise run test:coverage
mise run schema
mise run validate:packs
mise run privacy
git diff --check
```

Review the changed-file list and inspect the entire diff.

Expected modifications are limited to focused fingerprint tests and the C19 row in `docs/consolidation/progress.md`. Production implementation changes require a separate explicit design decision.

Update C19 to `review` with test evidence and the current implementation head. Do not mark it `accepted`.

Commit the tests and ledger update on `test/c19-fingerprint-contract`, push the branch, and open an unmerged PR targeting `main`.

The PR must include:

- Baseline and final head SHA.
- Exact frozen digests verified.
- New positive and negative fingerprint properties.
- Full test counts, Pyright result, coverage, and CI.
- Explanation of known line-dependent anchor limitations.
- Explicit confirmation that all production fingerprint algorithms and serialized contracts remain unchanged.

Preserve the implementation worktree for independent review.

## Final acceptance checklist

- [ ] Three identity algorithms documented accurately.
- [ ] Deterministic finding tests pass.
- [ ] Semantic finding tests pass.
- [ ] Report fingerprint tests pass.
- [ ] Existing C18 frozen digest unchanged.
- [ ] Baseline, suppression, and gate behavior unchanged.
- [ ] No schema or migration change.
- [ ] No new version prefix or incompatible representation.
- [ ] Full verification and required CI pass.
- [ ] C19 ledger is `review`, not `accepted`.
- [ ] Implementation PR remains unmerged.

If any requirement conflicts with observed behavior, stop the affected task and report the exact source, test, and expected/actual result to ChatGPT. Do not redesign fingerprint identity independently.
