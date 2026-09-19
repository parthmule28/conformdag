# C51 — Audit Backlog Markers and Legacy Notes

## Role and objective

You are the Build agent for C51. Search all TODO/FIXME/HACK/XXX/legacy/temporary/deprecated markers and resolve, document, track, or remove every occurrence so no silent backlog remains.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C49/C52.
- Repository-wide source/docs/scripts/workflows and compatibility documentation.

## Current ownership and resulting owner

Markers are currently an untracked mixture of real backlog, historical notes, compatibility promises, and stale comments. After this PR, each occurrence has one of four outcomes: resolved, documented with owner/evidence, tracked in a named future slice, or removed.

## Interfaces

For retained `deprecated`/`legacy` paths, documentation must state current support, introduced version, and removal condition. For future work, link a concrete issue or backlog slice rather than leaving an anonymous marker.

## Expected files

- Modify all files containing reviewed markers and `docs/compatibility.md`, `docs/consolidation/progress.md`, or issue references.
- Do not edit generated artifacts solely to hide a marker.

## Test-first sequence

1. Run repository searches for all marker classes and classify every occurrence in a scratch table.
2. Add/adjust tests for markers that describe behavior or compatibility.
3. Resolve/document/remove each marker and run focused tests.
4. Run a final search and `mise run check`.

## Allowed changes

- Marker resolution, explicit tracking documentation, compatibility notes, and tests.

## Non-goals and prohibitions

- Do not remove a marker without understanding its referenced invariant.
- Do not turn unresolved product work into vague prose.
- Do not create a new anonymous backlog marker while cleaning old ones.

## Verification matrix

- Zero unaccounted markers, default gate, docs/link checks, and compatibility review.

## Completion checklist and handoff

- [ ] Search results are classified and evidenced.
- [ ] Retained temporary paths have owners/removal conditions.
- [ ] No silent backlog markers remain.
- [ ] Commit with `docs: resolve backlog markers`; open the PR without merging.
