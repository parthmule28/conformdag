## Context

See `proposal.md` for why. `.gitignore` currently lists `openspec/` next to `.cursor/`. The CLI already created a repo-local `openspec/` tree (`config.yaml`, empty `specs/`, `changes/`).

## Goals / Non-Goals

**Goals:**

- Make `openspec/` a first-class, reviewable part of the repository.
- Leave local Cursor skills and IDE metadata untracked.

**Non-Goals:**

- Changing ConformDAG runtime, schemas, or CI quality gates.
- Publishing OpenSpec to PyPI or embedding it in the wheel.

## Decisions

1. **Track the entire `openspec/` directory** rather than a subset. Alternatives: ignore `changes/` and only commit `specs/`. Rejected: active changes need PR review the same as specs.

2. **Keep `.cursor/` gitignored.** Alternatives: commit project skills. Rejected for this change; skills stay local unless a later change publishes them.

3. **`skip_specs: true` on this change.** No product capability delta.

4. **Contributor docs flip from "keep OpenSpec out of product commits" to "commit OpenSpec artifacts with the change they describe."**

## Risks / Trade-offs

- [Large planning diffs] → Keep changes focused; archive completed changes with `openspec archive`.
- [Accidental secrets in specs] → Same rule as other docs: no credentials in `openspec/`.

## Migration Plan

Remove `openspec/` from `.gitignore`, add `openspec/` files, update docs. Rollback: restore the ignore line (not expected after merge).

## Open Questions

None.
