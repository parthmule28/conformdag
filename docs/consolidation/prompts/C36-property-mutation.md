# C36 — Property and Mutation Testing Review

## Role and objective

You are the Build agent for C36. Evaluate whether property-based and mutation testing add signal for high-value invariants, then add only focused tooling and tests whose maintenance cost is justified.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C19/C20/C35.
- Discovery normalization, fingerprint, gate, suppression, state-transition, and configuration-precedence code/tests.
- Current dev dependency and CI policies.

## Current ownership and resulting owner

Example/property tests cover many cases but do not systematically challenge path normalization, fingerprint determinism, gate invariants, state transitions, or precedence. After this PR, selected high-value properties and a documented mutation-testing task assess test strength without slowing every default PR unnecessarily.

## Interfaces

Candidate properties: normalized paths stay contained; repeated fingerprint computation is stable; suppressed findings never block; valid state transitions preserve invariants; explicit config overrides dominate project defaults. Mutation targets are gates, fingerprints, outcomes, suppression matching, and policy compatibility.

## Expected files

- Modify: `pyproject.toml`/dev tooling only if a dependency is justified, `tests/property/` or subsystem tests, `mise.toml`, and development docs.
- Create: a dedicated mutation task/configuration only if a repeatable local command and CI policy are defined.
- Do not alter production code for artificial mutation survivors without a real defect.

## Test-first sequence

1. Run existing tests and identify a concrete invariant with weak case diversity.
2. Add property cases using bounded generated inputs and deterministic seeds where useful.
3. Run focused property tests and inspect counterexamples.
4. Run mutation analysis on the five high-value areas; record survivors and either strengthen tests or document intentional survivors.
5. Run default gate and the dedicated slower task.

## Allowed changes

- Focused property tests, optional dev-only tool/task, and evidence documentation.

## Non-goals and prohibitions

- Do not add a heavyweight always-on CI dependency without a runtime/cost reason.
- Do not generate unbounded filesystem/process/provider inputs.
- Do not treat a mutation score as a production correctness proof.

## Verification matrix

- Focused property tests and reproducible mutation command.
- Default gate, coverage, and evidence review.
- Independent review must inspect the selected invariants, generated counterexamples, mutation survivors, and the decision to keep slow checks outside the default gate.

## Completion checklist and handoff

- [ ] Added properties target named invariants.
- [ ] Mutation findings are recorded with decisions.
- [ ] Slow verification remains separate from ordinary local checks.
- [ ] Commit with `test: assess property and mutation coverage`; open the PR without merging.
