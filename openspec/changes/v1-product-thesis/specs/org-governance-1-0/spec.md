## Purpose

Defines ConformDAG 1.0.0 as org-scale Airflow policy governance: git-versioned
org packs, a required self-hosted dashboard, and agent-assisted authoring and
fix — with the existing deterministic scan as the verifier.

## ADDED Requirements

### Requirement: Org-first product, not generic community standards

ConformDAG 1.0.0 SHALL present org-specific policy packs as the product. The
bundled `community` pack SHALL remain a try-now / demo path only. Product
documentation SHALL NOT claim a single generic standards document is sufficient
for organizational governance.

#### Scenario: Stranger try-now versus org product

- **WHEN** a user follows the public quickstart without an org pack
- **THEN** they can scan with `--policy-pack community`
- **AND** documentation states that production use requires an org pack in git

#### Scenario: Org messaging

- **WHEN** a platform lead reads 1.0.0 positioning
- **THEN** the product is described as enforcing that organization's versioned
  rules, not a universal Airflow style guide

### Requirement: Golden journeys for 1.0.0

ConformDAG 1.0.0 SHALL support journey B (platform bootstrap: org standards to
validated pack to registered DAG repos to baseline scan) and journey D
(dashboard review of findings, history, suppressions, export). Journey A
(DAG author CLI scan/fix against the org pack) SHALL work as a byproduct of
B and D. Journey D SHALL be completable using the dashboard without requiring
the operator to use the CLI for review.

#### Scenario: Journey D requires dashboard

- **WHEN** a reviewer has a workspace with at least one completed scan
- **THEN** they can inspect repo status, findings with file/line, policy
  contract, scan history, suppressions, and export SARIF or HTML from the
  dashboard

#### Scenario: Journey B ends in a dashboard baseline scan

- **WHEN** a platform lead has written a validated org pack to a policy repo
  working tree and registered one or more local DAG repo paths
- **THEN** they can trigger a baseline scan from the dashboard using the same
  scan engine as the CLI

### Requirement: Dashboard shows agent findings and explanations

The 1.0.0 dashboard SHALL display the full scan the reviewer needs to act:
deterministic findings and, when the operator enables BYOK agent/semantic
evaluation, those findings plus explanations and remediations in the same
review UI. 1.0.0 SHALL NOT ship a dashboard that is deterministic-only while
agent evaluation exists only on the CLI. Offline deterministic scan without
credentials SHALL still work from the dashboard.

#### Scenario: Reviewer sees explanations in the UI

- **WHEN** a scan was run with agent or semantic evaluation enabled and produced
  explanations
- **THEN** the dashboard shows those explanations next to the finding (not only
  in CLI JSON)

#### Scenario: Dashboard scan without credentials

- **WHEN** the operator has not configured a model API key
- **THEN** the dashboard can still run and display a deterministic scan

### Requirement: Documented deploy is Docker Compose

1.0.0 SHALL document Docker Compose as the path to run the dashboard (and
related services) as a whole product. The workspace file path remains an
explicit operator-supplied path (default `./conformdag-workspace.yaml`).

ConformDAG 1.0.0 SHALL ship `conformdag serve` (or an equivalent documented
command) that hosts a local web dashboard. 1.0.0 SHALL NOT be considered
complete if the only review surfaces are CLI, SARIF files, or static HTML
without an interactive dashboard. The dashboard SHALL be self-hosted and
open source. ConformDAG 1.0.0 SHALL NOT require a ConformDAG-operated cloud
service to review scans.

#### Scenario: Serve starts a local dashboard

- **WHEN** an operator runs the documented serve command on a machine with
  workspace configuration
- **THEN** they can open a local HTTP UI and perform journey D

#### Scenario: No hosted SaaS for 1.0.0

- **WHEN** 1.0.0 is published
- **THEN** documentation states there is no hosted ConformDAG control plane
- **AND** all dashboard data stays on the operator's machine or their
  self-hosted process

### Requirement: Git-native org policy distribution

Org policy packs SHALL live in git (central policy repo and/or co-located in a
monorepo). 1.0.0 SHALL document a golden path of a central policy repository
consumed by DAG repos (submodule or equivalent path checkout). 1.0.0 SHALL NOT
require signed OCI/HTTP policy bundle pull. The dashboard SHALL register local
filesystem paths to policy and DAG repositories; it SHALL NOT remotely clone
or sync git as a 1.0.0 MUST.

#### Scenario: Publish is git, not upload to ConformDAG

- **WHEN** a platform lead finishes pack authoring in 1.0.0
- **THEN** validated files are written to the policy repo working tree
- **AND** committing and tagging remains a human git operation

### Requirement: Single scan engine

All 1.0.0 scan entry points (CLI, dashboard, GitHub Action) SHALL produce
findings by invoking the same scan orchestration used by `conformdag scan`.
They SHALL NOT implement a second policy evaluation pipeline.

#### Scenario: Dashboard scan matches CLI

- **WHEN** the same repository root, pack, and configuration are scanned from
  the CLI and from the dashboard
- **THEN** the canonical JSON report contract is the same (report version,
  findings, policy pack identity)

### Requirement: Deterministic scan is the verifier

When an agent or semantic evaluator disagrees with a deterministic finding,
the deterministic FAIL SHALL remain a failure for blocking evaluation. Agents
SHALL NOT override or drop deterministic FAILs. Agent-authored policy packs
SHALL only reference check kinds the engine already implements; unknown check
kinds SHALL fail pack validation.

#### Scenario: Agent cannot clear a deterministic FAIL

- **WHEN** deterministic evaluation reports FAIL for a policy
- **THEN** an agent PASS or suggested patch that does not change the source
  enough to satisfy the check SHALL leave the scan FAIL after re-evaluation

#### Scenario: Pack with unknown check kind is invalid

- **WHEN** a pack lists a deterministic check the engine does not implement
- **THEN** validation fails before that pack is used for a scan

### Requirement: Agent pack authoring and fix in 1.0.0

ConformDAG 1.0.0 SHALL provide agent-assisted drafting of an org pack from
org-specific standards documents, and SHALL provide `conformdag fix` (or
equivalent) that proposes source patches, re-scans, and applies only with
explicit operator confirmation. Agent features MAY require an optional install
extra and BYOK credentials. Offline `scan` SHALL remain usable without the
agent extra.

#### Scenario: Scan without agent extra

- **WHEN** the operator has not installed the agent extra and has not enabled
  semantic evaluation
- **THEN** `conformdag scan` still completes an offline deterministic scan

#### Scenario: Fix requires confirmation

- **WHEN** the operator runs fix without an apply confirmation flag
- **THEN** the system shows a proposed patch and does not write DAG sources

### Requirement: GitHub Action in 1.0.0

ConformDAG 1.0.0 SHALL ship a documented GitHub Action (or reusable workflow)
that runs a scan, can upload SARIF, and fails the job on blocking findings.

#### Scenario: Blocking finding fails CI

- **WHEN** a pull request is scanned with the documented action and a blocking
  finding is present
- **THEN** the workflow concludes unsuccessfully

### Requirement: Stable 1.0.0 contracts

The 1.0.0 release SHALL treat policy pack YAML schema, canonical scan report
JSON, and public CLI commands `scan`, `serve`, `fix`, and `validate-policies`
as compatibility surfaces. The dashboard HTTP API MAY be documented as
internal and unstable.

#### Scenario: Report JSON remains canonical

- **WHEN** any 1.0.0 adapter renders findings
- **THEN** it is a projection of the versioned scan report JSON contract

### Requirement: 1.0.0 non-goals

ConformDAG 1.0.0 SHALL NOT include: a ConformDAG-hosted SaaS; dashboard
multi-user authentication or RBAC; MCP as a release blocker; automatic pull
request creation; autonomous DAG creation or Airflow runtime orchestration;
dbt support; a maintained Airflow 2.x runtime image; product telemetry /
phone-home.

#### Scenario: MCP absence does not block 1.0.0

- **WHEN** 1.0.0 is released without an MCP server
- **THEN** the release still satisfies this capability if dashboard, scan,
  pack authoring, fix, and GitHub Action requirements are met
