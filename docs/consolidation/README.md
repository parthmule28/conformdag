# ConformDAG Consolidation Backlog

This directory is the execution backlog for the C01–C64 consolidation program. It converts the approved consolidation blueprint into independently reviewable OpenCode Build prompts.

## Read order

1. `../superpowers/specs/2026-09-20-consolidation-backlog-design.md` — artifact design and prompt contract.
2. `architecture-rules.md` — invariants every slice must preserve.
3. `baseline.md` — measured starting state and evidence commands.
4. `backlog.md` — program index, dependencies, risk, and phase gates.
5. `progress.md` — execution ledger.
6. `prompts/CNN-*.md` — the ready-to-paste Build prompt for one PR.

## How to execute one slice

Use a dedicated feature worktree and start from the branch state named by the owning PR. A Build agent must:

1. Read `AGENTS.md`, `architecture-rules.md`, `progress.md`, the slice prompt, and every dependency prompt listed in `backlog.md`.
2. Inspect the current symbols, callers, tests, generated artifacts, and Git status before editing.
3. Record any mismatch between the prompt and the current tree in the progress ledger before changing scope.
4. Add a focused regression or characterization test before implementation whenever the behavior is testable.
5. Implement the smallest ownership-preserving change described by the prompt.
6. Run the focused test repeatedly, then the affected subsystem suite.
7. Run format, lint, Pyright, pack/schema checks, and any conditional integration gates named by the prompt.
8. Inspect `git diff --check`, `git diff`, and `git status`; preserve unrelated user work.
9. Update only the slice's progress row with commands, results, compatibility notes, and remaining risks.
10. Commit the slice with a Conventional Commit message and open a PR; do not merge it.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `planned` | Prompt exists and the slice has not started. |
| `ready` | Dependencies are accepted and the slice can be assigned. |
| `in-progress` | A Build agent is actively working on the slice. |
| `blocked` | Work cannot proceed until a named dependency or decision changes. |
| `review` | Implementation is complete and awaiting independent review. |
| `accepted` | PR and required evidence are accepted; the next slice may consume it. |
| `split` | The proposed slice was safely divided; child PRs are recorded in the ledger. |

The generated backlog starts every slice at `planned`. It does not claim that any product consolidation has been implemented.

## Verification tiers

| Code | Gate |
| --- | --- |
| `L` | `mise run check` (format, Ruff, Pyright, default tests, pack validation). |
| `C` | `mise run test:coverage` and the configured 90% gate. |
| `S` | JSON schema export check after model changes. |
| `FE` | Frontend build and relevant Vitest checks. |
| `PW` | Packaged-server or frontend Playwright verification. |
| `PG` | Real PostgreSQL migration/concurrency integration suite. |
| `RT` | Dockerized Airflow/runtime verification. |
| `B` | Benchmark or round-trip fixing verification. |
| `P` | Wheel/sdist and installed-wheel smoke verification. |
| `SEC` | Privacy, dependency, secret, filesystem, or threat-model gate. |
| `ARCH` | Import/dependency architecture validator. |
| `REV` | Independent reviewer or fresh audit replay. |

## Scope discipline

The prompts are intentionally explicit about non-goals. Do not combine package moves with semantic redesign, add speculative dbt/MCP abstractions before their slice, or use a consolidation PR to clean unrelated code. If the current tree makes a slice unsafe, record the reason and split it; do not silently broaden it.
