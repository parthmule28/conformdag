# ConformDAG Consolidation Execution Backlog Design

## Goal

Turn the supplied C01–C64 consolidation blueprint into a durable OpenCode execution backlog. Each consolidation slice must be independently understandable, reviewable, testable, and ready to paste into a Build-agent session without requiring the agent to reconstruct the architecture from the original blueprint.

## Scope

This deliverable is planning and coordination documentation. It does not implement the consolidation, change runtime behavior, alter public contracts, or add product dependencies.

The backlog treats C01 through C64 as independently reviewable PR-sized slices. The slices retain the blueprint's ordering and dependencies, but each prompt may instruct the implementer to split a slice further if the current code or verification results prove that the proposed boundary is unsafe. Such a split must be recorded in the progress ledger rather than silently expanding a PR.

The backlog is based on the repository state at the start of this worktree. Every Build prompt must still require the agent to inspect the current files and callers before editing; file paths in a prompt are an ownership target, not permission to overwrite unexpected work.

## Artifact structure

```text
docs/consolidation/
├── README.md
├── architecture-rules.md
├── baseline.md
├── backlog.md
├── progress.md
└── prompts/
    ├── C01-*.md
    ├── C02-*.md
    └── C64-*.md
```

### `README.md`

Explains the purpose of the consolidation program, the relationship between the index and prompts, the required Build-agent workflow, status vocabulary, and how to update progress without rewriting history.

### `architecture-rules.md`

Captures the non-negotiable ownership and safety rules from the blueprint: one scan engine, verify-by-rescan fixing, human merge authority, offline default, distinct trust boundaries, canonical `ScanReport`, lower-layer dependency direction, explicit compatibility paths, Alembic-only schema changes, and one authoritative check catalogue.

### `baseline.md`

Records the starting commit and measurements that are available without inventing values. Unknown measurements are named as commands to run in C01, not represented as guessed numbers. The file also records the local-branch/worktree cleanup performed before this backlog work and the preserved pre-existing stash reference.

### `backlog.md`

Provides the program-level view: all 64 slices, phase grouping, dependencies, risk level, expected review focus, status, and exit gates. It links to exactly one prompt file per slice and identifies which slices require Postgres, Docker, frontend, browser, packaging, or independent review verification.

### `prompts/CNN-*.md`

Each prompt is ready to paste into an OpenCode Build session. It is self-contained and uses the same required structure described below.

### `progress.md`

Is the execution ledger. It contains one checkbox and evidence row per slice, plus phase-level gates and a final accounting section. Agents update only the slice they are executing and append evidence; they do not mark unrelated slices complete.

## Build-prompt contract

Every prompt must contain these sections in this order:

1. **Role and objective** — tells the Build agent which C slice it owns and what outcome is required.
2. **Required reads** — names `AGENTS.md`, `docs/consolidation/architecture-rules.md`, `docs/consolidation/progress.md`, the relevant prior prompt or ADR, and exact source/test files to inspect.
3. **Current ownership** — states where the responsibility lives today and what must become the single owner after the slice.
4. **Dependencies and interfaces** — gives exact symbols, data shapes, compatibility facades, and consuming slices. No task may refer to an undefined future symbol.
5. **Expected files** — separates create, modify, rename, delete, and test paths. A prompt must explicitly say when a file move is not allowed.
6. **Test-first sequence** — gives concrete failing-test, focused-run, minimal-implementation, focused-run, subsystem-run, and diff-review steps. Commands must use the repository's `mise`/`uv` conventions.
7. **Allowed changes** — defines the smallest implementation and documentation scope for the PR.
8. **Non-goals and prohibited changes** — explicitly forbids unrelated cleanup, parallel scan paths, trust-boundary merging, destructive Git operations, broad exception handling, schema changes without Alembic, and deleting unrecognized user work.
9. **Verification matrix** — lists focused tests, lint/format/type checks, schema or pack checks, and conditional integration gates required before completion.
10. **Completion checklist and handoff** — requires diff/status review, progress evidence, compatibility notes, unresolved risks, and a conventional commit/PR summary without merging.

High-risk prompts additionally identify the required independent review focus. These are C03, C06, C07, C09, C10, C12, C17, C24, C26, C30, and C41, matching the blueprint.

## Dependency and execution model

The index groups the slices into the blueprint's logical phases, but dependencies are explicit rather than inferred from numbering. The first phase establishes the contract and vocabulary; catalogue and package moves precede application extraction; application extraction precedes platform delegation; contract and security work precede MCP/dbt readiness; test, packaging, and independent-review slices follow the structural migrations.

Each prompt must leave the repository in a buildable state or document a narrowly scoped, intentionally temporary compatibility facade. A prompt may not require a later slice to make its own tests pass.

## Safety and compatibility rules

- Agents work in a dedicated feature worktree and must preserve pre-existing user changes in any workspace they inspect.
- Agents must not use `git reset --hard`, broad `git checkout`, recursive deletion, force-push, or branch deletion.
- Existing public imports, CLI entry points, report JSON, policy schemas, and HTTP contracts remain compatible unless the prompt names the migration and its deprecation evidence.
- The canonical scan primitive remains `scan_repository()` until an application workflow has parity tests; no adapter may gain evaluation logic.
- Core modules may not import Typer, FastAPI, SQLAlchemy, MCP, or platform adapters.
- Fixing continues to require isolated apply followed by rescan and verification.
- Redaction, filesystem containment, runtime isolation, database transitions, and human merge authority remain explicit review concerns.
- The final prompt set must distinguish ordinary local gates from expensive Postgres, Docker, browser, packaging, benchmark, and independent-audit gates.

## Success criteria

The backlog is complete when:

1. `backlog.md` names all C01–C64 slices exactly once and links every prompt.
2. Every prompt has concrete paths, interfaces, test-first commands, allowed/non-allowed scope, and completion evidence.
3. Cross-slice names and dependencies are internally consistent.
4. No prompt contains unresolved placeholders such as `TBD`, `TODO`, or “add appropriate tests.”
5. The backlog preserves the supplied blueprint's invariants and final completion criteria.
6. The documentation passes Markdown/link checks available in the repository and is committed independently of later product implementation.
