## Purpose

Amends the 1.0.0 non-goals requirement of `org-governance-1-0` per ADR 0003: automatic
pull request creation moves from non-goal to in-scope via `agent-harness` under the
never-merge constraint, and the authentication non-goal is narrowed. This change solely
owns the non-goals rewrite; `platform-server` amends only the stable-contracts
requirement.

## MODIFIED Requirements

### Requirement: 1.0.0 non-goals

ConformDAG 1.0.0 SHALL NOT include: a ConformDAG-hosted SaaS; dashboard multi-user
authentication or RBAC (single-admin platform authentication is in scope via the
platform-server change); MCP as a release blocker; autonomous DAG creation or Airflow
runtime orchestration; dbt support; a maintained Airflow 2.x runtime image; product
telemetry / phone-home. Automatic pull request creation is no longer a non-goal: it is in
scope via the `agent-harness` capability under the ADR 0003 constraint that agents open
pull requests and NEVER merge — humans merge.

#### Scenario: MCP absence does not block 1.0.0

- **WHEN** 1.0.0 is released without an MCP server
- **THEN** the release still satisfies this capability if dashboard, scan,
  pack authoring, fix, and GitHub Action requirements are met

#### Scenario: Automatic PRs are agent-opened, human-merged

- **WHEN** the agent completes a fix loop with a clean re-scan and an approve verdict
- **THEN** it may open a pull request with evidence
- **AND** merging remains a human action; the agent holds no merge capability
