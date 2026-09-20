# C38 — Audit Wheel, Source Distribution, and Installed Assets

## Role and objective

You are the Build agent for C38. Verify that clean wheel/sdist builds contain only intended runtime assets, including the production SPA and bundled policy pack, and that an isolated installed wheel can execute the supported smoke flows.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C31/C37.
- `pyproject.toml` Hatch configuration, `.gitignore`, frontend build task, bundled packs, package imports, release docs, and distribution tests.

## Current ownership and resulting owner

Static SPA files are gitignored and explicitly included as Hatch artifacts; packaging correctness is currently verified in distribution tests and release tasks. After this PR, a reproducible packaging audit records wheel/sdist contents, asset counts, dependency surfaces, and installed smoke results.

## Interfaces

Keep `conformdag = "conformdag.cli:app"` unless a deliberate entry-point change has installed-wheel evidence. Preserve explicit `artifacts = ["src/conformdag/platform/static/**"]` configuration.

## Expected files

- Modify: packaging/release scripts, `tests/test_distribution.py`, `docs/release.md`, and `mise.toml` only for missing repeatable checks.
- Do not remove static artifact configuration or bundled pack inclusion.

## Test-first sequence

1. Build wheel/sdist before changes and inspect file lists, sizes, static assets, bundled pack, and entry points.
2. Add failing installed-wheel smoke checks for missing assets/imports if gaps exist.
3. Implement the smallest packaging/task correction.
4. Install the wheel into an isolated environment and run version, community scan, server import/boot, SPA file, API, and unknown-asset checks.
5. Run package, privacy, security, default, and frontend gates.

## Allowed changes

- Packaging checks, release documentation/tasks, and proven Hatch/include corrections.

## Non-goals and prohibitions

- Do not add generated dev dependencies to runtime packages.
- Do not optimize away required SPA or policy assets.
- Do not claim package success from a source-tree import only.

## Verification matrix

- `mise run build`, wheel/sdist content audit, isolated wheel smoke, privacy/security checks.
- Frontend build prerequisite and default gate.

## Completion checklist and handoff

- [ ] Wheel and sdist contain intended source/assets only.
- [ ] Installed wheel supports community scan and platform/SPA smoke.
- [ ] Artifact inclusion remains explicit and documented.
- [ ] Commit with `test: audit distribution artifacts`; open the PR without merging.
