# C19 — Formalize Fingerprint Contracts

## Role and objective

You are the Build agent for C19. Document and, where useful, version the finding and report fingerprint inputs so report diff, baseline, suppression, and future MCP consumers can rely on stable identity.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C18.
- `src/conformdag/reporting/normalize.py` or current `reporting.py`, `src/conformdag/models.py`, `src/conformdag/evaluator.py`, `src/conformdag/semantic.py`, and `src/conformdag/gates.py`.
- `tests/test_evaluator.py`, `tests/test_semantic.py`, `tests/test_reporting.py`, `tests/test_gates.py`, and `tests/test_fixing.py`.

## Current ownership and resulting owner

Fingerprint construction is implemented near reporting/evaluator logic but its stability contract is implicit. After this PR, `docs/architecture/fingerprints.md` documents volatile exclusions and normalized inputs; the implementation exposes `FINDING_FINGERPRINT_VERSION` and `REPORT_FINGERPRINT_VERSION` if that strengthens intentional evolution without changing serialized shapes.

## Interfaces

- Finding identity includes policy ID/version, path/structural anchor, status, and deterministic semantic citation inputs as currently defined.
- Report identity excludes timestamps and volatile provider prose.
- Version constants are explicit strings and changes require compatibility review.

## Expected files

- Create: `docs/architecture/fingerprints.md`.
- Modify: reporting normalization, evaluator/semantic fingerprint helpers, and focused tests only if version constants or missing contract code are needed.
- Do not change report JSON fields without a separate compatibility decision.

## Test-first sequence

1. Add snapshot/property cases for line-shift stability, timestamp exclusion, semantic prose exclusion, policy version changes, suppression/status changes, and deterministic repeatability.
2. Run current fingerprint/gate/suppression tests and record expected values.
3. Add documentation and version constants or narrow implementation corrections.
4. Run all fingerprint consumers, round-trip tests, coverage, and `mise run check`.

## Allowed changes

- Fingerprint documentation, explicit version constants, and tests pinning current behavior.

## Non-goals and prohibitions

- Do not redesign finding identity for report diff yet.
- Do not include raw semantic explanations, timestamps, machine paths, or secrets.
- Do not silently change existing fingerprints.

## Verification matrix

- Fingerprint snapshots/properties and baseline/suppression/gate tests.
- Round-trip benchmark, `mise run check`, and coverage.
- Independent review of compatibility impact.

## Completion checklist and handoff

- [ ] Finding/report identity inputs are documented.
- [ ] Volatile fields and versioning rules are explicit.
- [ ] Existing known fingerprints remain unchanged unless deliberately versioned.
- [ ] Commit with `docs: document report fingerprint contracts`; open the PR without merging.
