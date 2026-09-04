## Purpose

Specifies ConformDAG's distribution and CI surfaces per ADR 0003: a composite GitHub Action
living in this repository (scan via a pinned CLI, SARIF upload, fail on blocking findings,
zero-credential try-now) and git-native policy pack distribution via `conformdag pack pull`
(ambient git credentials, existing provenance validation, recorded resolved refs, explicit
re-pull, and a forward-compatible source grammar). The scan engine, canonical report JSON
contract, and policy pack schema are unchanged; CI scans run the same single engine as local
scans.

## ADDED Requirements

### Requirement: Composite action in this repository

The shipped GitHub Action SHALL live at this repository's root as a composite action
(`action.yml`), versioned by git release tags aligned with CLI releases. The action SHALL run
a scan, support SARIF upload, and fail the job on blocking findings. The action SHALL NOT be
packaged as a Docker action or maintained in a separate repository.

#### Scenario: Pinned-tag workflow scans and uploads SARIF

- **WHEN** a workflow uses the action at a pinned release tag with default inputs on a
  repository containing DAGs
- **THEN** the action scans the repository using the CLI version aligned with that tag
- **AND** the scan's SARIF is uploaded to the repository's code scanning results

### Requirement: Zero-credential try-now

On a public repository using the bundled `community` pack with default inputs, the action
SHALL complete a scan and SARIF upload without any ConformDAG or provider credentials. The
action SHALL NOT require a ConformDAG account, a ConformDAG-operated service, or a model API
key for its default deterministic path.

#### Scenario: Public repo community scan with no credentials

- **WHEN** a public repository adds the action with `policy-pack: community` and default
  inputs, and no credentials or API keys are configured
- **THEN** the scan completes and SARIF is uploaded
- **AND** no ConformDAG account or non-git network service is contacted

### Requirement: Blocking findings fail CI

When `fail-on-blocking` is true (the default) and a scan completes with blocking findings,
the action SHALL cause the workflow to conclude unsuccessfully using the CLI's exit code 1
semantics (a complete run with blocking failures). When `fail-on-blocking` is false, the
workflow SHALL NOT fail due to blocking findings, and those findings SHALL remain in the
report and SARIF artifacts.

#### Scenario: Blocking finding fails CI

- **WHEN** a pull request is scanned with the documented action and a blocking finding is
  present
- **THEN** the workflow concludes unsuccessfully

#### Scenario: fail-on-blocking disabled still reports findings

- **WHEN** the action runs with `fail-on-blocking: false` on a repository with blocking
  findings
- **THEN** the workflow does not fail due to those findings
- **AND** the SARIF and report artifacts contain them

### Requirement: Git-native pack pull

`conformdag pack pull <source>` SHALL fetch the pack from a git URL using ambient git
credentials (SSH keys, credential helpers) into a local cache directory (default
`.conformdag/packs/<name>`), SHALL validate the pack with the existing provenance/schema
validation, and SHALL record the resolved commit ref alongside the pack. Updating a cached
pack SHALL require an explicit re-pull; there SHALL be no automatic sync. Pack pull SHALL NOT
require a ConformDAG account, any network service beyond git, or an API key.

#### Scenario: Private pack repo via deploy key

- **WHEN** an operator with a configured deploy key runs `conformdag pack pull` against a
  private policy repository git URL
- **THEN** the pack is fetched into the cache, validated, and its resolved commit ref is
  recorded
- **AND** no ConformDAG account or non-git service is contacted

#### Scenario: Re-pull is explicit

- **WHEN** a pack is cached at a recorded ref and a later scan or action run happens without
  an explicit re-pull
- **THEN** the cached pack and its recorded ref are used unchanged
- **AND** the recorded ref remains inspectable alongside the cached pack

### Requirement: Forward-compatible source grammar

The `pack pull` source argument grammar SHALL accept filesystem paths and git URLs, and SHALL
reserve a scheme prefix (e.g. `platform://`) for a future platform-backed source. Reserved
schemes SHALL be rejected as unimplemented with a clear message. Implementing a reserved
scheme later SHALL NOT change the behavior of git URL or filesystem sources.

#### Scenario: platform:// source rejected clearly today

- **WHEN** an operator runs `conformdag pack pull platform://org/policy`
- **THEN** the command fails with a message stating the source scheme is not implemented
- **AND** git URL and filesystem sources continue to work unchanged

### Requirement: Deterministic CI parity

A scan run by the action SHALL produce the same canonical report JSON contract as a local CLI
scan for the same repository root, policy pack, and configuration. The action SHALL NOT
implement a second policy evaluation pipeline.

#### Scenario: CI scan matches local scan

- **WHEN** the same repository root, pack, and configuration are scanned locally with
  `conformdag scan` and in CI with the action
- **THEN** the canonical JSON report contract is the same (report version, findings, policy
  pack identity)
