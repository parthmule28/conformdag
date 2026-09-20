# C53 — Rewrite AGENTS.md for the Consolidated Architecture

## Role and objective

You are the Build agent for C53. Make coding-agent instructions enforceable and current after the consolidation docs and boundaries stabilize.

## Required reads

- `AGENTS.md`, `docs/consolidation/architecture-rules.md`, `progress.md`, and C41/C52.
- Current command/task definitions, package structure, migration rules, testing gates, compatibility docs, and security guidance.

## Current ownership and resulting owner

`AGENTS.md` currently describes the pre-consolidation module layout and important gotchas. After this PR, it directs agents to read consolidation rules before structural work and states exact ownership constraints for scans, checks, fixing, DB state, adapters, schemas, and generated frontend types.

## Interfaces

Required rules include: no evaluation logic in CLI/FastAPI/MCP/worker; new checks use `CheckSpec`; complete scan orchestration belongs to application; scan status uses approved transitions; DB changes require Alembic; report/fingerprint changes require compatibility review; `mise run check` and relevant expensive gates are named.

## Expected files

- Modify: root `AGENTS.md`, and only linked contributor/agent docs when a path changed.
- Do not change product code or weaken existing safety instructions.

## Test-first sequence

1. Compare every current instruction to `architecture-rules.md`, current tasks, and implementation packages.
2. Add the consolidated rules with exact paths and commands.
3. Search for contradictions/stale names and correct them.
4. Run documentation/link checks and default gate.

## Allowed changes

- Agent instructions, command references, architecture rules, and links.

## Non-goals and prohibitions

- Do not instruct agents to use destructive Git operations.
- Do not hide uncertainty with speculative architecture.
- Do not replace the canonical architecture contract with a second conflicting list.

## Verification matrix

- Instruction/link consistency, `mise run check`, architecture task, and fresh-agent read-through.

## Completion checklist and handoff

- [ ] AGENTS points to current ownership and gates.
- [ ] No rule contradicts architecture docs or project commands.
- [ ] Safety/compatibility constraints are explicit.
- [ ] Commit with `docs: update agent architecture instructions`; open the PR without merging.
