# C01 — Consolidation Baseline and Architectural Contract

## Role and objective

You are the Build agent for C01. Establish the durable measurement baseline and the architecture contract that every later consolidation PR must follow. This PR is documentation-only: it must not change scanner, platform, frontend, packaging, or runtime behavior.

## Required reads

- `AGENTS.md`
- `docs/superpowers/specs/2026-09-20-consolidation-backlog-design.md`
- `docs/consolidation/README.md`
- `docs/consolidation/architecture-rules.md`
- `docs/consolidation/baseline.md`
- `docs/architecture.md`
- `docs/adr/0001-architecture-principles.md`
- `docs/adr/0002-v1-product-thesis.md`
- `docs/adr/0003-v1-agentic-platform-architecture.md`

Inspect `pyproject.toml`, `mise.toml`, `src/conformdag/evaluator.py`, `src/conformdag/scan.py`, `src/conformdag/platform/app.py`, `src/conformdag/platform/db.py`, `tests/`, and the current Git status before editing.

## Current ownership and resulting owner

Architecture guidance is distributed across `docs/architecture.md`, `AGENTS.md`, implementation comments, and prior plans. After this PR, `docs/consolidation/architecture-rules.md` owns consolidation-specific invariants, `baseline.md` owns measured starting evidence, and the new ADR owns the modular-monolith/application-boundary decision. Existing architecture docs remain valid and are not replaced wholesale.

## Interfaces

- Consumes: current repository at the PR base and the supplied C01–C64 blueprint.
- Produces: `docs/adr/0004-modular-monolith-application-boundaries.md`, updated consolidation contract files, and reproducible evidence commands.

## Expected files

- Create: `docs/adr/0004-modular-monolith-application-boundaries.md`.
- Modify: `docs/consolidation/README.md`, `architecture-rules.md`, `baseline.md`, `progress.md`, and `backlog.md` only when current evidence requires correction.
- Test: no product test file; use documentation and command verification.
- Do not rename or delete source files in this PR.

## Test-first sequence

1. Record the current SHA, branch, line counts, collected tests, default gate result, coverage result, dependency surfaces, route count, and check count in a scratch note.
2. Confirm the values with `mise run check`, `mise run test:coverage`, `mise exec -- uv run pytest --collect-only -q`, and `git diff --check`.
3. Write the ADR and update only evidence that can be reproduced from the recorded commands.
4. Re-run `git diff --check` and inspect every changed Markdown section.
5. Run `mise run check` again if any tracked Python or configuration file was touched; documentation-only changes still require the Markdown/link check used by CI.

## Allowed changes

- Add the ADR and consolidation documentation.
- Correct measured values and name commands for measurements not yet run.
- Define status vocabulary, phase gates, review responsibilities, and the ownership rules required by later prompts.

## Non-goals and prohibitions

- Do not refactor product code, add dependencies, change schemas, or alter `AGENTS.md` in this PR.
- Do not present guessed wheel, image, or Postgres values as measurements.
- Do not use destructive Git commands or remove existing docs because they look redundant.

## Verification matrix

- `git diff --check`.
- The repository's existing Markdown/link check when one exists; otherwise run this deterministic local-link check from the repository root and record its output in the progress ledger:

  ```bash
  python - <<'PY'
  from pathlib import Path
  import re

  root = Path("docs/consolidation")
  failures = []
  for path in root.rglob("*.md"):
      for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
          if target.startswith(("http://", "https://", "#", "mailto:")):
              continue
          local = target.split("#", 1)[0]
          if local and not (path.parent / local).resolve().is_file():
              failures.append(f"{path}: {target}")
  if failures:
      raise SystemExit("\n".join(failures))
  print("all local consolidation links resolve")
  PY
  ```
- `mise run check` if non-documentation files changed.
- Manual review that each rule has one owner and that C01–C64 remains represented in the index.

## Completion checklist and handoff

- [ ] ADR number and title do not collide with an existing ADR.
- [ ] Baseline records observed values separately from future measurement commands.
- [ ] Architecture rules preserve one scan engine, verify-by-rescan fixing, offline default, trust boundaries, and human merge authority.
- [ ] Progress ledger starts product slices at `planned`.
- [ ] Commit with `docs: establish consolidation baseline and architecture contract`; open the PR without merging.
