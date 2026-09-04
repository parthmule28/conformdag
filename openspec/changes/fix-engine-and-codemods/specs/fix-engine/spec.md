## Purpose

Defines ConformDAG's deterministic fix engine and the agent-readable output contract it depends
on: dry-run-by-default patching, per-check-kind codemods with an explicit fixability matrix,
verify-by-rescan before any write, self-contained findings, a round-trip benchmark release
gate, and fully offline operation. The agentic harness that raises PRs is a separate later
change; this capability is its Phase 1 foundation.

## ADDED Requirements

### Requirement: Dry-run by default

`conformdag fix` SHALL NOT modify DAG source files unless `--apply` is passed. Without
`--apply` it SHALL print the proposed unified diff and write nothing to the repository. The
dry-run output SHALL be identical to the diff that `--apply` would write for the same inputs.

#### Scenario: Fix without apply writes nothing

- **WHEN** an operator runs `conformdag fix` without `--apply` on a repository with findings
- **THEN** a unified diff of the proposed changes is printed
- **AND** no DAG source file in the repository is modified

### Requirement: Deterministic codemods per check kind

Fix generation SHALL be deterministic for mechanical check kinds: identical inputs SHALL
produce byte-identical edit specs and diffs. The engine SHALL declare non-fixable check kinds
explicitly via a fixability matrix rather than guessing a fix. `required-owner`,
`required-tags`, `execution-timeout`, and `retry-bounds` SHALL be mechanical autofix;
`top-level-io` SHALL be proposed-diff-only (structural move, never auto-applied);
`forbidden-operators` and `idempotence` SHALL NOT be autofixed and SHALL be reported as
not-fixable for human or agent action. Patches SHALL be structured edit specs (file, AST
anchor, replacement) rendered to unified diffs; the engine SHALL NOT perform raw string
surgery on sources.

#### Scenario: Execution-timeout finding produces a kwarg addition

- **WHEN** fix runs on an `execution-timeout` finding whose pack config sets a timeout bound
- **THEN** the proposed patch adds (or raises) the `execution_timeout` kwarg with the
  configured value on the anchored task
- **AND** re-running fix on the same inputs yields a byte-identical diff

#### Scenario: Forbidden-operator finding is reported not-fixable

- **WHEN** fix runs on a `forbidden-operators` finding
- **THEN** the finding is reported as not-fixable with its remediation payload
- **AND** no edit spec is generated for it

### Requirement: Verify-by-rescan

The fix engine SHALL apply edit specs to an isolated patched copy (git worktree or temp copy)
of the repository BEFORE any write to sources, and SHALL re-scan that copy with the same scan
engine used to produce the findings. The engine SHALL iterate patch-and-rescan up to a bounded
iteration count and SHALL report residual failures when the loop exits with findings remaining.
Only a verified patch SHALL be presented or applied.

#### Scenario: Patch that does not clear the check is surfaced

- **WHEN** a generated patch fails to clear its originating check on the patched copy's
  re-scan after the bounded iteration count is reached
- **THEN** the engine reports the residual failure with the finding and iteration count
- **AND** the unverified change is not written by `--apply`

### Requirement: Agent-readable findings

Every finding SHALL carry enough context to act without re-reading the repository: location,
evidence, a policy contract reference, and a remediation payload containing the concrete
values configured in the policy pack (not references back to pack files), a code anchor, and a
codemod fix hint. These fields SHALL be optional in the canonical report JSON with a minor
schema version bump, and the report SHALL remain parseable by consumers of the prior schema
version.

#### Scenario: Model consumer can act from the report alone

- **WHEN** a model consumer receives only the report JSON for an `execution-timeout` finding
- **THEN** the finding's remediation payload contains the configured timeout value, the code
  anchor for the target task, and the fix hint
- **AND** the correct `execution_timeout` kwarg fix can be produced without opening the
  repository or the policy pack

### Requirement: Round-trip benchmark gate

The round-trip benchmark SHALL inject known violations into a clean DAG corpus, run the fix
engine over it, and assert that a re-scan of the fixed corpus is clean for the injected
findings. It SHALL extend the existing 240-case deterministic gate, and the release SHALL fail
if the round-trip result regresses.

#### Scenario: Release blocked on round-trip regression

- **WHEN** the round-trip benchmark reports findings remaining after fix on the injected
  corpus, or the case count drops below the gate's floor
- **THEN** the release gate fails and the regression is recorded in release evidence

### Requirement: Offline operation

The entire fix engine SHALL operate with no network access, no credentials, and no model
provider. Fix SHALL NOT require any agent extra, API key, or telemetry to run to completion.

#### Scenario: Fix runs air-gapped

- **WHEN** an operator runs `conformdag fix --apply` on a machine with no network and no
  configured credentials
- **THEN** the command completes verification and writes the verified patch
- **AND** no outbound connection is attempted
