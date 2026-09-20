# C62 — Rehearse Packaging and Release Without Publishing

## Role and objective

You are the Build agent for C62. Perform a complete release rehearsal from the consolidated tree without publishing, including wheel/sdist install, platform/SPA boot, runtime smoke image, security gates, SBOM, and immutable runtime identity checks.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C38–C40/C61.
- `docs/release.md`, build/release workflows, Dockerfiles/Compose, runtime identity tooling, packaging scripts, security/privacy tasks, and browser smoke.

## Current ownership and resulting owner

Release correctness is distributed between local tasks and CI. After this PR, a documented rehearsal produces artifacts/logs for package build, isolated install, CLI/community scan, platform boot/SPA/API/404, runtime smoke, dependency/secret/privacy/security scans, SBOM, and tag/image identity.

## Interfaces

No publishing or tag push. Use the exact supported build commands and record image tags with the full ref name rules. Verify the wheel includes `src/conformdag/platform/static/**`.

## Expected files

- Create/modify: `docs/consolidation/release-rehearsal.md`, release scripts/docs, CI checks, and proven packaging/container fixes.
- Do not publish packages/images or change production credentials.

## Test-first sequence

1. Run clean build/package/image/security commands and save logs/artifact inventory.
2. Add failing checks for any missing release invariant.
3. Correct the owning build/release boundary and repeat from a clean output directory.
4. Run installed wheel, packaged server/browser, runtime smoke, SBOM, privacy, dependency, secret, and image checks.

## Allowed changes

- Rehearsal evidence, build/release automation, and proven release fixes.

## Non-goals and prohibitions

- Do not publish, push tags, force-push, or change deployment credentials.
- Do not accept mutable runtime identity or missing static assets.

## Verification matrix

- `mise run build`, isolated install, platform/SPA/browser, runtime, security/privacy, SBOM, image identity and scan.

## Completion checklist and handoff

- [ ] Rehearsal starts from clean outputs and is reproducible.
- [ ] Wheel/sdist/image/SPA/runtime identities are verified.
- [ ] No publish side effect occurred.
- [ ] Commit with `test: rehearse consolidated release`; open the PR without merging.
