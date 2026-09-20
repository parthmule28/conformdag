# C55 — Add the Permanent Adversarial Regression Suite

## Role and objective

You are the Build agent for C55. Create a clearly named permanent suite for hostile repository, policy, provider, filesystem, Git, worker, and platform inputs identified by C54.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C43/C54.
- Existing adversarial/security tests, discovery/fixing/agent/platform/runtime/semantic code, and threat matrix.

## Current ownership and resulting owner

Adversarial regressions are spread across ordinary tests and hard to discover. After this PR, `tests/adversarial/` owns hostile-input scenarios and links each case to a threat/control.

## Interfaces

Cover hostile Ruff configuration/selectors, recursive excludes, internal/external/broken symlinks, traversal, malformed/conflicting policy, cache corruption, provider prompt injection/invalid schema/secret-like output, dirty Git targets, stale worker ownership, cancellation races, and malformed platform requests.

## Expected files

- Create: `tests/adversarial/` modules, fixtures, and a README/manifest mapping cases to threat IDs.
- Modify: owning production code only when a regression test proves a gap; update `mise.toml` with a dedicated task if suite cost warrants it.

## Test-first sequence

1. Translate each C54 high-risk matrix row into a failing adversarial test.
2. Run focused tests and fix the owning boundary, not the fixture.
3. Run the suite repeatedly and verify deterministic cleanup/temporary paths.
4. Run default, security/privacy, package, runtime, Postgres, and round-trip gates as relevant.

## Allowed changes

- Hostile fixtures, permanent tests, dedicated task, and proven security fixes.

## Non-goals and prohibitions

- Do not execute malicious repository code on the host.
- Do not use network/provider credentials in adversarial tests.
- Do not make timing races the only proof of state correctness; use database conditions/fences.

## Verification matrix

- `pytest tests/adversarial`, default gate, security/privacy, Postgres/runtime/package gates.
- Independent review must sample hostile path, provider, cache, Git, and worker cases and verify each maps to a C54 control.

## Completion checklist and handoff

- [ ] Every high-risk threat has a permanent regression.
- [ ] Fixtures cannot escape temporary roots or access secrets/network.
- [ ] Failures point to an owning layer.
- [ ] Commit with `test: add adversarial regression suite`; open the PR without merging.
