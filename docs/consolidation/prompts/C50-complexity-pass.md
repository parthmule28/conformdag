# C50 — Refactor Measured Complexity Hotspots

## Role and objective

You are the Build agent for C50. Use temporary complexity and fan-in/fan-out measurements to refactor only functions whose complexity represents mixed responsibility, with behavior pinned by existing tests.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C33/C49.
- Current complexity report for application scan, fix engine, AST visitor, worker subprocess loop, policy editing, and scan execution.
- Focused tests and public interfaces for each selected hotspot.

## Current ownership and resulting owner

Likely hotspots are `fixing/engine.py`, the AST visitor, worker subprocess execution, policy mutation, and application scan. After this PR, mixed responsibilities are split into named cohesive helpers or modules without creating trivial indirection.

## Interfaces

Select targets using measured complexity and caller impact; record before/after values and preserve public signatures. New helpers must have explicit input/output types and one responsibility.

## Expected files

- Modify only selected hotspot modules and their focused tests.
- Add a temporary measurement script or report under docs if needed; do not add a permanent complexity gate without a policy decision.

## Test-first sequence

1. Run complexity/fan-in/fan-out measurements and choose targets with mixed responsibility.
2. Add characterization tests for error, boundary, and security paths not already covered.
3. Extract one responsibility at a time and run focused tests after each extraction.
4. Run affected subsystem, default, coverage, round-trip, runtime, and Postgres gates as applicable.

## Allowed changes

- Cohesion-driven helper/module extraction, type annotations, and regression tests.

## Non-goals and prohibitions

- Do not refactor solely for line count or a metric threshold.
- Do not weaken exception/security paths or introduce broad catch blocks.
- Do not change public report/fix semantics.

## Verification matrix

- Before/after complexity evidence, focused tests, `mise run check`, coverage, and round-trip benchmark.
- Independent review of the highest-risk extraction.

## Completion checklist and handoff

- [ ] Each refactor has a measured cohesion reason.
- [ ] Public behavior and security invariants remain covered.
- [ ] Complexity report is recorded.
- [ ] Commit with `refactor: reduce mixed-responsibility complexity`; open the PR without merging.
