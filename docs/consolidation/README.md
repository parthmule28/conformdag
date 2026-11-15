# ConformDAG Consolidation Backlog

This directory is the execution backlog for the C01–C64 consolidation program. It converts the approved consolidation blueprint into independently reviewable OpenCode Build prompts.

## Read order

1. `../superpowers/specs/2026-09-20-consolidation-backlog-design.md` — artifact design and prompt contract.
2. `../adr/0004-modular-monolith-application-boundaries.md` — the proposed durable boundary decision for this program.
3. `architecture-rules.md` — invariants every slice must preserve.
4. `baseline.md` — measured starting state and evidence commands.
5. `backlog.md` — program index, dependencies, risk, and phase gates.
6. `progress.md` — execution ledger.
7. `prompts/CNN-*.md` — historical Build prompts and constraints. For new milestones, the canonical GitHub Issue is the authoritative implementation and acceptance contract.
8. [`c24-persistence-architecture.md`](c24-persistence-architecture.md) — accepted C24 persistence decision; [Issue #88](https://github.com/parthmule28/conformdag/issues/88) is closed.
9. [`c25-transaction-architecture.md`](c25-transaction-architecture.md) — accepted C25 transaction ownership and failure-atomicity verification; [Issue #92](https://github.com/parthmule28/conformdag/issues/92) is closed.
10. [`c26-postgres-architecture.md`](c26-postgres-architecture.md) — **formally accepted C26** PostgreSQL 17 integration and seven-job CI; [Stage A PR #97](https://github.com/parthmule28/conformdag/pull/97), [Stage B PR #98](https://github.com/parthmule28/conformdag/pull/98) and [Stage C PR #99](https://github.com/parthmule28/conformdag/pull/99) merged. [Post-merge main CI #43594331554](https://github.com/parthmule28/conformdag/actions/runs/43594331554) passed seven of seven required jobs; [Issue #96](https://github.com/parthmule28/conformdag/issues/96) closed.
11. [`c27-worker-runner-architecture.md`](c27-worker-runner-architecture.md) — **C27 Stage A ACCEPTED**, Worker/Runner lifecycle versus application/fenced-ingestion ownership and structured attempt correlation; [Issue #100](https://github.com/parthmule28/conformdag/issues/100) owns WR01–WR12/T0–T8. [PR #101](https://github.com/parthmule28/conformdag/pull/101) merged as `73896ce57942f7b95bb3dd9cc053c642114d6bf6`; exact-SHA [main CI #43616969873](https://github.com/parthmule28/conformdag/actions/runs/43616969873) passed all seven mandatory jobs. **Stage B implementation NOT AUTHORIZED**.

## Current issue-first Stage A/B/C workflow (effective from C27)

This process applies to **all future ConformDAG milestones**, not only consolidation. [Governance Issue #102](https://github.com/parthmule28/conformdag/issues/102) records the approved transition; historical architecture and acceptance PRs remain valid evidence but are **not** the future default.

1. **Stage A — ChatGPT architecture:** Create one canonical GitHub Issue using the consolidation milestone form. ChatGPT source-audits ownership and interfaces, makes architecture decisions, documents constraints, acceptance criteria, TDD sequence, risks and the accepted baseline directly in that Issue. **Stage B remains PENDING** until the user explicitly authorizes implementation; Issue creation, board status and prior-stage approval are not authorizations. ADR/docs PRs are exceptions for durable cross-cutting architecture, public behavior, or tooling changes.
2. **Stage B — OpenCode implementation, only when separately authorized:** GPT-6.1 Sol coordinates bounded Luna Max subagents; **one writer per worktree**. OpenCode implements and tests exactly the Issue contract, reports local evidence, and opens **one unmerged implementation PR** referencing the Issue with **Refs #N** (never Closes/Fixes/Resolves #N). ChatGPT independently audits the exact head and all required CI evidence; implementation agents do not accept or merge their own work. Any scope mismatch returns to ChatGPT for a design decision.
3. **Merge gate — explicit user authority:** Seven mandatory GitHub checks must pass on the **exact reviewed PR head**: Fast checks; Offline benchmark gate; Release validation; macOS host CLI and source analysis; Airflow runtime profile (3.3.0); PostgreSQL integration; Browser journeys (Playwright). Required head freshness and protected main rules still apply. The user must **separately approve every PR merge**; GitHub approving-review count 0 does **not** substitute for independent ChatGPT review or user authorization. Use a guarded merge tied to the approved head SHA. Optional semantic smoke is not a mandatory check.
4. **Stage C — ChatGPT acceptance:** After merge, independently verify the same seven jobs succeed on the **exact main merge SHA**. ChatGPT records disposition, tests, head/merge SHAs, review evidence, caveats and outstanding risks **in the same Issue**; close the Issue as completed only after verified post-merge CI. **No routine Stage C acceptance-documentation PR**. For an exceptional normative docs/ADR change, make a separately reviewed PR and request separate merge authorization.
5. **Project tracking:** The ConformDAG-wide [GitHub Project](https://github.com/users/parthmule28/projects/1) tracks Issues and PRs (new/updated items auto-add with is:issue,pr). Board status is visibility, not authorization. Close the milestone Issue only after Stage C acceptance; a merged implementation PR must not auto-accept the milestone.

This procedure supersedes historical text requiring a standard Stage A planning PR or Stage C docs PR; it does **not** rewrite past merge/acceptance evidence. C27 Stage A is accepted, **C27 Stage B is NOT AUTHORIZED**, and C28 is not authorized.

## How to execute one slice

**Only after explicit Stage B authorization**, use a dedicated feature worktree and start from the accepted `main` baseline recorded in the canonical Issue. A Build agent must:

1. Read `AGENTS.md`, `architecture-rules.md`, `progress.md`, the slice prompt, and every dependency prompt listed in `backlog.md`.
2. Inspect the current symbols, callers, tests, generated artifacts, and Git status before editing.
3. Report any mismatch between the prompt and the current tree to ChatGPT; scope changes and planning-document updates require ChatGPT's architecture decision.
4. Add a focused regression or characterization test before implementation whenever the behavior is testable.
5. Implement the smallest ownership-preserving change described by the prompt.
6. Run the focused test repeatedly, then the affected subsystem suite.
7. Run format, lint, Pyright, pack/schema checks, and any conditional integration gates named by the prompt.
8. Inspect `git diff --check`, `git diff`, and `git status`; preserve unrelated user work.
9. Return commands, results, compatibility notes, and remaining risks as implementation evidence; **ChatGPT alone** updates the progress ledger and acceptance documentation.
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
