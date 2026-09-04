## Purpose

Defines the agentic enforcement harness: an agent that operates the existing scan/fix
engine as a tool user, generates patches only via deterministic codemods, gates pull
requests on a deterministic re-scan and an LLM-verifier verdict, opens evidence-rich PRs
under a GitHub App, and never merges — humans merge.

## ADDED Requirements

### Requirement: Agent operates the existing engine

The agent SHALL produce scans and fixes only by invoking the same scan engine and codemod
registry used by the CLI. The agent SHALL NOT implement a second policy evaluation or fix
pipeline.

#### Scenario: Agent scan matches CLI scan

- **WHEN** the agent pipeline scans the same repository root, pack, and configuration as
  `conformdag scan`
- **THEN** the canonical JSON report is the same as the CLI's

### Requirement: Deterministic generation, verified application

Patches for mechanical check kinds SHALL come from the deterministic codemod registry. The
agent SHALL run the verify-by-rescan loop before proposing anything, and SHALL NOT propose
a pull request whose re-scan is not clean.

#### Scenario: Clean re-scan becomes a PR candidate

- **WHEN** a codemod patch is applied to an isolated copy and the re-scan reports no
  findings for the targeted checks
- **THEN** the patch proceeds to semantic verification

#### Scenario: Unclean re-scan stops the loop

- **WHEN** the bounded fix loop ends with findings still present
- **THEN** no pull request is proposed for those findings

### Requirement: LLM semantic verification gates pull requests

Before a pull request is opened, an LLM verifier SHALL review the diff and before/after
re-scan evidence against a strict verdict schema (approve or reject with reasons). A
reject verdict SHALL block pull request creation.

#### Scenario: Semantically nonsensical change is rejected

- **WHEN** a codemod patch re-scans clean but produces a semantically nonsensical change
- **THEN** the verifier returns a reject verdict with reasons
- **AND** no pull request is opened

### Requirement: Model-agnostic providers

All LLM calls in the agent and verifier SHALL go through OpenAI-compatible endpoints
configured by the operator. The codebase SHALL NOT contain provider-specific code paths.

#### Scenario: Operator swaps endpoints

- **WHEN** the operator points the configuration at a different OpenAI-compatible base
  URL and model
- **THEN** agent and verifier calls work without code changes

### Requirement: Pull request lifecycle safety

The agent SHALL open pull requests under a GitHub App identity with short-lived tokens.
Every agent-opened pull request SHALL include the evidence body: findings fixed with
file/line, policy contracts, report fingerprints before/after, deterministic verification
result, and LLM-verifier verdict. The agent SHALL NEVER merge, approve, or force-push.

#### Scenario: Happy path PR opened with evidence

- **WHEN** the agent completes a fix loop with a clean re-scan and an approve verdict
- **THEN** it pushes a branch and opens a pull request under the GitHub App identity
- **AND** the pull request body contains the full evidence set

#### Scenario: Merging is not an agent capability

- **WHEN** an agent session is asked to merge, approve, or force-push a pull request
- **THEN** the operation is not available in the agent client and is denied by the
  GitHub App's least-privilege permissions

### Requirement: Policy-review mode

The agent SHALL be able to draft policy-pack pull requests from governance aggregates
(fail rates by policy, suppression rates, stale suppressions, never-firing policies) for
human review. When the platform is absent, the agent MAY compute a local summary from
workspace scans.

#### Scenario: Heavily-suppressed policy yields a scope-adjustment PR

- **WHEN** the aggregates show a policy with a high suppression rate that fails mostly
  outside its intended scope
- **THEN** the agent drafts a policy-pack PR proposing a scope adjustment with the
  aggregate evidence in the PR body
- **AND** a human reviews and merges the PR

### Requirement: Agent never overrides the verifier

Deterministic FAIL findings SHALL remain blocking regardless of agent or LLM output
(single-verifier principle inherited from `org-governance-1-0`, restated for the agent).

#### Scenario: Agent output cannot clear a deterministic FAIL

- **WHEN** deterministic evaluation reports FAIL and the agent or LLM-verifier asserts
  the finding is resolved without a clean re-scan
- **THEN** the finding remains blocking

### Requirement: Optional extra

Agent capabilities SHALL install via an optional extra and SHALL NOT be required for
offline scan or fix.

#### Scenario: Scan and fix without the agent extra

- **WHEN** the operator has not installed the agent extra
- **THEN** `conformdag scan` and `conformdag fix` still work fully offline
