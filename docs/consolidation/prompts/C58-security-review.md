# C58 — Fresh Independent Security Review

## Role and objective

You are the independent reviewer for C58. Review the consolidated tree without relying on the previous audit's conclusions, then create and resolve only substantiated security findings across every trust boundary.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C54–C57.
- `docs/security.md`/threat model, source and tests for filesystem, subprocess/Docker, Git, HTTP provider, DB concurrency, auth, redaction, packaging, and release.
- Previous audit evidence only after forming an independent initial assessment.

## Current ownership and resulting owner

The review must challenge ownership and controls rather than perform a routine checklist. Findings become issues assigned to the actual owning module, with regression tests or documented residual risk.

## Interfaces

Review inputs include malicious repository paths/text/config, policy provenance/instructions, provider output, future MCP authorization/path/mutation surfaces, Docker daemon, Git dirty/verified-file behavior, platform auth/SQL races, logs/cache/artifacts, dependencies/images/releases.

## Expected files

- Create/modify: independent review report under `docs/consolidation/security-review.md`, regression tests, and owning implementation files for substantiated findings.
- Do not rewrite the threat model to hide a finding.

## Test-first sequence

1. Perform the fresh review and record finding, impact, affected boundary, evidence, and proposed test.
2. Add failing regression tests for confirmed issues.
3. Fix the owning layer and rerun focused/security/privacy/adversarial/integration gates.
4. Record rejected findings with technical rationale and residual risk.

## Allowed changes

- Security findings, targeted fixes, regressions, and review evidence.

## Non-goals and prohibitions

- Do not add speculative permissions or generic security wrappers.
- Do not expose secrets in review artifacts.
- Do not merge agent authority or enable future MCP writes.

## Verification matrix

- Security/privacy, adversarial, Postgres/runtime/package, default, and fresh reviewer sign-off.

## Completion checklist and handoff

- [ ] Review was independent of prior findings initially.
- [ ] Every confirmed issue has a regression/evidence or accepted residual risk.
- [ ] Trust boundaries remain distinct.
- [ ] Commit with `security: record independent consolidation review`; open the PR without merging.
