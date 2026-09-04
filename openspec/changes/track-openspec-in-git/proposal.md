## Why

OpenSpec planning lived in a gitignored `openspec/` directory, so proposals, delta specs, designs, and tasks could not be reviewed on GitHub or shared across machines. ConformDAG 1.0.0 planning needs those artifacts as the in-repo source of truth.

## What Changes

- Track the `openspec/` tree in git (config, `specs/`, `changes/`).
- Keep `.cursor/` gitignored (local agent skills and IDE state).
- Update contributor docs so OpenSpec artifacts are expected in product PRs when a change uses them.
- This change sets `skip_specs: true`: it does not change ConformDAG runtime behavior.

## Capabilities

### New Capabilities

None. Tooling and documentation only (`skip_specs: true`).

### Modified Capabilities

None.

## Impact

- `.gitignore`, `CONTRIBUTING.md`, pull request template.
- First commit of `openspec/config.yaml` and this change directory.
- No CLI, policy, or report contract changes.
