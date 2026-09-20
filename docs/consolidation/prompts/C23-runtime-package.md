# C23 — Review and Decompose the Runtime Package

## Role and objective

You are the Build agent for C23. Measure whether `runtime.py` has distinct profile, manifest, and Docker responsibilities; if the cohesion boundary is real, split it without weakening immutable image identity or sandbox controls. If it is already cohesive, record the decision and make only the smallest safe extraction.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C06/C21.
- Full `src/conformdag/runtime.py`, `src/conformdag/application/scan.py`, runtime smoke scripts, Docker/Compose files, and `tests/test_runtime.py`.
- Release/runtime documentation and immutable digest checks.

## Current ownership and resulting owner

`runtime.py` currently contains profile definitions, manifest validation, Docker command construction, image resolution, execution, and result parsing. The target is `runtime/profiles.py`, `manifest.py`, and `docker.py` only if metrics show separate cohesive responsibilities; otherwise retain a documented cohesive module.

## Interfaces

Preserve `RUNTIME_PROFILES`, `RuntimeProfile`, `RuntimePhaseError`, `DockerRunner`, `build_runtime_manifest()`, and runtime result semantics through `runtime/__init__.py` if split.

## Expected files

- Possible create: `src/conformdag/runtime/__init__.py`, `profiles.py`, `manifest.py`, `docker.py`.
- Possible remove: `src/conformdag/runtime.py` only after import parity; a no-op package move is not required when cohesion is already strong.
- Modify: runtime tests, application/CLI imports, and smoke scripts only for moved symbols.

## Test-first sequence

1. Measure function/module cohesion and add import-parity tests.
2. Run all runtime tests before movement.
3. If split is justified, move profile/manifest/Docker groups and preserve exact command arrays, digest checks, resource limits, no-network/read-only/non-root behavior, and output protocol.
4. Run unit runtime tests and real runtime smoke where Docker is available.
5. Run `mise run check`, coverage impact review, and package/image smoke.

## Allowed changes

- Cohesion-driven file movement, facade exports, and tests.

## Non-goals and prohibitions

- Do not replace Docker isolation with a generic subprocess abstraction.
- Do not accept tag-only custom images, enable network, add capabilities, or change immutable profile identities.
- Do not split solely to meet a line-count target.

## Verification matrix

- Runtime unit suite and `mise run test:runtime`/smoke when Docker is available.
- Default gate, coverage, package, and image security checks.

## Completion checklist and handoff

- [ ] Split/no-split decision is evidence-backed.
- [ ] Runtime security and release identity are unchanged.
- [ ] Public runtime imports remain compatible.
- [ ] Commit with `refactor: organize runtime boundary` or `docs: record runtime cohesion decision`; open the PR without merging.
