# C03 Authoritative Check Catalogue Design

**Status:** approved conversational design; written spec awaiting review
**Slice:** C03 — Authoritative Check Catalogue
**Date:** 2026-09-21

## Purpose

C03 establishes one authoritative Python catalogue for check metadata that is
currently split across the evaluator registry, policy configuration mapping,
CLI scaffolding, legacy policy aliases, and fixability sets. The catalogue
must make adding a check a single-source change while preserving the current
scan, finding, policy, fixer, and CLI behavior.

The catalogue is an internal ownership change. It does not introduce a new
scan path, move evaluator implementations, implement semantic checks, or
change any serialized product contract.

## Goals and non-goals

### Goals

- Make `src/conformdag/checks/registry.py` the owner of `Fixability`,
  `CheckSpec`, `CHECK_SPECS`, and derived compatibility views.
- Represent all 15 known check/configuration kinds in the catalogue:
  the 12 current deterministic evaluator kinds plus the three existing
  semantic-only kinds (`idempotence`, `orchestration-boundary`, and
  `approved-abstractions`).
- Mark the three semantic-only entries as non-executable with
  `evaluator=None`; C03 does not implement them and C05 does not receive
  implementation work through this slice.
- Derive evaluator lookup, deterministic configuration lookup, legacy policy
  mappings, and fixability classifications from the catalogue.
- Preserve exact CLI scaffold payloads for the currently executable kinds.
- Preserve old imports such as `conformdag.evaluator.CHECK_EVALUATORS` and
  `conformdag.fixing.codemods.AUTOFIX_KINDS` through compatibility facades or
  derived aliases.
- Prove both import orders work between `checks.registry` and `evaluator`.

### Non-goals

- Moving evaluator classes or evaluator helpers out of `evaluator.py`;
  C05 owns that movement.
- Implementing the three non-executable semantic-only entries.
- Moving codemod function bodies or replacing the explicit `FIXERS` function
  map.
- Changing evaluator logic, finding semantics, policy IDs, policy schemas,
  report JSON, fingerprints, fix application, or scan orchestration.
- Expanding into platform response DTOs, OpenAPI typing, or service
  restructuring owned by later slices.

## Authoritative data model

`checks/registry.py` will define a frozen `CheckSpec` with explicit fields:

- `kind: str` — the deterministic/check vocabulary key.
- `configuration_kind: str` — the typed `PolicyConfiguration.kind` expected
  by the check, including the self-mapping for semantic-only entries.
- `evaluator: DeterministicEvaluator | None` — the existing evaluator
  instance for executable deterministic kinds, or `None` for the three
  non-executable entries.
- `fixability: Fixability` — `AUTOFIX`, `PROPOSED_ONLY`, or `MANUAL`.
- `fix_kind: str | None` — the remediation kind used by the existing fixer
  payloads; populated for autofix/proposed entries and absent for manual
  entries.
- `scaffold_factory: Callable[[], dict[str, object]] | None` — a factory
  returning a fresh, schema-valid configuration payload for executable kinds.
- `legacy_policy_ids: tuple[str, ...]` — policy IDs that historically route
  to this kind.

`CHECK_SPECS` is keyed by `kind` and contains all 15 entries. The insertion
order of the 12 executable entries remains the current `CHECK_EVALUATORS`
order so CLI iteration and generated output remain stable.

The three semantic-only entries are catalogue metadata only. They have no
evaluator and are not exposed as executable deterministic checks by the CLI or
policy validation. Their existing typed model configurations remain unchanged.

## Derived compatibility views

The registry derives these views from `CHECK_SPECS`:

- `CHECK_EVALUATORS`: the 12 entries whose `evaluator` is not `None`.
- `CHECK_CONFIGURATION_KINDS`: configuration mappings for those executable
  entries only. This preserves the current rule that a deterministic policy
  cannot name a semantic-only kind.
- `LEGACY_POLICY_CHECKS`: each legacy policy ID to its catalogue `kind`.
- `LEGACY_POLICY_EVALUATORS`: the legacy evaluator object view derived through
  `LEGACY_POLICY_CHECKS` and `CHECK_EVALUATORS`.
- `LEGACY_POLICY_CONFIGURATION_KINDS`: the legacy configuration-kind view
  derived through `LEGACY_POLICY_CHECKS` and `CheckSpec.configuration_kind`.
- `AUTOFIX_KINDS`, `PROPOSED_ONLY_KINDS`, and `MANUAL_KINDS`: disjoint
  fixability sets derived from every catalogue entry, including the three
  semantic-only manual entries.

`check_spec(kind)` is the single lookup API for callers that need complete
metadata. Unknown kinds retain a clear lookup error; existing CLI and policy
error boundaries continue to render their current user-facing messages.

## Cycle-safe compatibility boundary

The registry must be importable before or after `evaluator.py` without a
circular-import failure.

The design uses this dependency direction:

1. `evaluator.py` defines `EvaluationContext`, the evaluator protocol, and all
   evaluator classes without importing the registry during module execution.
2. `registry.py` builds its catalogue through a private builder that imports
   the already-defined evaluator classes lazily. It never imports evaluator
   compatibility aliases while constructing the catalogue.
3. `evaluator.py` exposes old registry names through a lazy module
   compatibility facade (`__getattr__`) backed by `TYPE_CHECKING` declarations.
   A legacy import therefore resolves to the completed registry only when the
   name is requested.
4. `checks/__init__.py` re-exports the authoritative registry API for new
   callers.

Tests will explicitly exercise both sequences:

- `import conformdag.checks.registry` followed by importing compatibility
  names from `conformdag.evaluator`.
- `import conformdag.evaluator` followed by importing the registry.

Both sequences must expose the same object identities for derived evaluator
and fixability views.

## Scaffolding and executable behavior

The current `_policy_configuration()` literal in `cli.py` moves into named
catalogue scaffold factories. Each factory returns a fresh object and
preserves the exact current values, including the Ruff rule list.

`policy new` resolves `CheckSpec` and accepts only entries with both an
evaluator and a scaffold factory. Consequently the three non-executable
semantic-only entries remain unavailable to the deterministic CLI exactly as
they are today. The generated YAML block, validation path, policy ID, and
error messages remain behaviorally unchanged.

Policy validation uses the derived executable evaluator and configuration views
for unknown-check and configuration-kind checks. The legacy fallback continues
to resolve policy IDs through `LEGACY_POLICY_CHECKS`; it does not become a
second registry.

## Fixability and codemod boundary

`fixing/codemods.py` retains the explicit `FIXERS` mapping and every existing
codemod body. It imports the derived fixability views rather than defining the
classification sets itself. The registry does not import `FIXERS`, avoiding a
cycle and keeping codemod implementation ownership in the fixing package.

Registry tests will prove:

- the three fixability sets are pairwise disjoint and cover all 15 specs;
- every `AUTOFIX` and `PROPOSED_ONLY` spec has the expected `fix_kind`;
- every autofix/proposed kind has an entry in `FIXERS`;
- manual kinds do not acquire a codemod accidentally.

## Verification strategy

### New registry tests

`tests/checks/test_registry.py` will cover:

- all 15 kinds are unique and discoverable;
- executable specs have evaluators and scaffold factories;
- semantic-only specs have `evaluator is None` and are not executable;
- all executable configuration kinds validate through the existing
  discriminated `PolicyConfiguration` machinery;
- legacy policy IDs are unique and map to check kinds, evaluator instances,
  and configuration kinds consistently;
- scaffold factories return fresh, schema-valid payloads;
- derived fixability views and `FIXERS` agree;
- both registry/evaluator import orders succeed and preserve compatibility
  object identity.

### Existing parity suites

The implementation must keep the existing evaluator, policy, CLI, fixing, and
round-trip tests green. The full verification includes:

- focused registry, evaluator, policy, CLI, and fixing tests;
- the 80-case autofix round-trip population;
- `mise run check`;
- `mise run test:coverage`;
- pack validation and schema checks;
- frontend tests/build only if the merged tree or generated package gate
  requires them.

No test may assert merely that a table has a particular private shape when a
behavioral parity assertion is possible. The high-value assertions are
generated views, schema-valid scaffolds, import-order safety, and unchanged
scan/fix results.

## Acceptance criteria

C03 is complete when:

1. `checks/registry.py` is the only catalogue owner.
2. All 15 known entries are represented, with exactly 12 executable evaluator
   entries and three explicit non-executable entries.
3. Evaluator, policy, CLI, and codemod compatibility names are derived from
   the catalogue or explicitly preserved as facades; no duplicate metadata
   table remains.
4. `FIXERS` remains an explicit function map while fixability classification
   comes from `CheckSpec`.
5. Both import orders pass without circular-import errors.
6. Existing evaluator behavior, policy IDs, scaffolds, findings, reports,
   fix behavior, and scan orchestration are unchanged.
7. The required focused and repository verification gates pass.
