# C54 — Produce the Fresh Threat Model

## Role and objective

You are the Build agent for C54. Reassess threats across malicious repositories, policy packs, providers, MCP callers, filesystem paths, subprocesses, Git, HTTP auth, SQL concurrency, packaging, and release operations, then map each threat to controls and tests.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C15/C24/C27/C43–C46/C52.
- `docs/security.md`, runtime/Docker/Git/semantic/platform code, existing audit remediation evidence, and adversarial tests.

## Current ownership and resulting owner

Security fixes exist across modules but the threat model is distributed. After this PR, `docs/security.md` or `docs/threat-model.md` contains an adversary matrix with asset, capability, control, regression test, residual risk, and owner.

## Interfaces

Threat classes must cover malicious repository text/paths/config, malicious policy/provenance/instructions, malicious provider output/schema/content, future MCP path/mutation parameters, Docker daemon/runtime, Git dirty/target files, platform auth/DB races, logs/cache/artifacts, and package/release supply chain.

## Expected files

- Create/modify: `docs/security.md`, `docs/threat-model.md`, `docs/consolidation/progress.md`, and tests only when a missing control is discovered.
- Do not claim a documentation statement is a control without an implementation/test reference.

## Test-first sequence

1. Build the adversary/control matrix from code and the recorded remediation/audit evidence in the repository.
2. Add regression tests for untested high-risk controls before changing implementation.
3. Correct proven gaps in the owning module, keeping trust boundaries distinct.
4. Run security/privacy, adversarial, platform, runtime, semantic, and default gates.

## Allowed changes

- Threat/security documentation, control links, permanent regressions, and narrowly scoped fixes.

## Non-goals and prohibitions

- Do not implement MCP write capabilities or merge authority.
- Do not collapse Docker, Git, provider, Ruff, and database boundaries into one abstraction.
- Do not treat LLM output as trusted policy/configuration.

## Verification matrix

- Threat matrix review, adversarial/security/privacy tests, package/image checks, default gate, and an explicit count of the recorded historical findings that remain covered.
- Independent security review is required in C58.

## Completion checklist and handoff

- [ ] Every threat has a named control/test or explicit residual risk.
- [ ] Malicious provider/repository/MCP cases are represented.
- [ ] Human merge authority remains explicit.
- [ ] Commit with `docs: add consolidated threat model`; open the PR without merging.
