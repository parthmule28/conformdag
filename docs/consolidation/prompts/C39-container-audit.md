# C39 — Audit Runtime and Platform Containers

## Role and objective

You are the Build agent for C39. Review runtime and platform image boundaries separately for security, reproducibility, size, users, writable paths, health checks, and unnecessary dependencies.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C23/C38.
- Dockerfiles, Compose files, runtime profile/image identity files, package build tasks, health checks, and release/security docs.
- Runtime tests, platform boot scripts, and CI image jobs.

## Current ownership and resulting owner

Runtime images host isolated Airflow execution; platform images host FastAPI/worker/SPA. After this PR, an evidence-backed container audit records each image's base, user, capabilities, mounts, network, writable directories, caches, package contents, health check, and size.

## Interfaces

Preserve runtime image digest policy, non-root/read-only/no-network assumptions, exact Airflow compatibility, and platform server/worker boot contract.

## Expected files

- Modify: Dockerfiles, Compose/release docs, image test scripts, and CI only when a measured security/reliability issue is found.
- Create: container audit task/report if no repeatable check exists.
- Do not change image identities or security flags without corresponding tests/docs.

## Test-first sequence

1. Build current runtime/platform images and record size, users, package caches, health, and security scan results.
2. Add checks for non-root, read-only assumptions, capabilities, network, writable paths, static assets, health, and immutable runtime identity.
3. Apply only measured corrections and rebuild.
4. Run runtime smoke, platform boot/browser smoke, `pip-audit`/image scanner, and package checks.

## Allowed changes

- Container audit tooling, Docker/Compose corrections tied to evidence, and documentation.

## Non-goals and prohibitions

- Do not trade security or runtime compatibility for image size.
- Do not use mutable image tags for supported runtime profiles.
- Do not copy dev dependencies into production layers.

## Verification matrix

- Runtime Docker tests, platform boot/Playwright, image scan, package/privacy gates.

## Completion checklist and handoff

- [ ] Runtime and platform container reports are separate.
- [ ] Security flags/users/writable paths are verified.
- [ ] Image size changes are measured.
- [ ] Commit with `chore: audit container boundaries`; open the PR without merging.
