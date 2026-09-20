# C61 — Verify Clean-Machine Onboarding

## Role and objective

You are the Build agent for C61. Use only repository documentation to execute the clean-machine onboarding flow and fix missing instructions or tooling without changing the product scope.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C52/C53/C60.
- README, development/release/security/configuration docs, `mise.toml`, package/frontend/runtime/platform tasks, and clean-environment setup instructions.

## Current ownership and resulting owner

Onboarding knowledge is distributed among docs and agent instructions. After this PR, a fresh environment can clone, install, run checks, demo, scan, fix dry-run, build frontend, and boot platform using docs only.

## Interfaces

Required flow: clone → `mise install` → `mise run setup` → `mise run check` → demo → community scan → fix dry-run → frontend build → platform boot. Capture environment/tool versions and exact command outcomes.

## Expected files

- Modify: onboarding/development/release docs, `mise.toml`, scripts, and task prerequisites only when the clean run proves a gap.
- Create: `docs/consolidation/onboarding-evidence.md` with date, environment, commands, and results.
- Do not add hidden manual setup steps.

## Test-first sequence

1. Start in a clean container or disposable directory with docs as the only guide.
2. Run each command and record the first failure without patching around it.
3. Add the smallest doc/tooling correction, then restart from the documented step.
4. Run full package/frontend/platform/browser/security checks.

## Allowed changes

- Documentation, setup tasks/scripts, and proven onboarding fixes.

## Non-goals and prohibitions

- Do not rely on local caches, undeclared credentials, or uncommitted files.
- Do not weaken default checks for onboarding convenience.

## Verification matrix

- Clean-machine command transcript, default gate, frontend build, demo, community scan/fix dry-run, platform boot, packaged/browser smoke.

## Completion checklist and handoff

- [ ] Docs-only clean onboarding succeeds.
- [ ] Every required tool/credential/service is named.
- [ ] Evidence records environment and failures.
- [ ] Commit with `docs: verify clean-machine onboarding`; open the PR without merging.
