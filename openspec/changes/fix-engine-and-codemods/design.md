## Context

See `proposal.md` for why. One scan engine (`src/conformdag/scan.py`) evaluates versioned YAML
policy packs against DAG repositories; six deterministic check kinds exist today
(`required-owner`, `required-tags`, `execution-timeout`, `retry-bounds`, `top-level-io`, plus
operator/idempotence-style rules), and the canonical scan report JSON is a stable contract.
ADR 0003 (drafted in parallel as `docs/adr/0003-v1-agentic-platform-architecture.md`) decides
that deterministic codemods generate fixes and that a separate agentic harness (later change)
consumes the report and raises PRs. This change is Phase 1 of that architecture: the fix engine
itself and the agent-readable output contract it depends on — fully offline, no LLM, no
credentials.

## Goals / Non-Goals

**Goals:**

- Specify and implement the deterministic fix engine as a standalone, offline phase.
- Make every scan finding self-contained for a model consumer (remediation payload, code
  anchors, fix hints) so the later harness never needs to re-derive context.
- Prove fix correctness mechanically: verify-by-rescan plus a round-trip benchmark release
  gate.

**Non-Goals:**

- LLM-generated patches or any model calls inside the fix engine.
- PR creation, PR commenting, or any agentic harness behavior (separate later change).
- Platform/dashboard integration of fixes (later changes).
- Autofixing judgment-call rules (`forbidden-operators`, `idempotence`).

## Decisions

1. **Fixers follow the evaluator registry pattern.** The fixer registry is keyed by check kind
   (e.g. `execution-timeout`), not policy ID, mirroring how deterministic evaluators register.
   Alternative: per-policy fixers. Rejected — policies compose from kinds; per-policy fixers
   would multiply with every pack.

2. **Patches are structured edit specs rendered to unified diffs — never raw string surgery.**
   A codemod emits (file, AST anchor, replacement); the engine renders a unified diff from the
   spec. Alternative: regex/string replacement. Rejected — silent mis-edits on formatting
   variance would poison trust in `--apply`.

3. **Verification happens before any write, on a temp copy.** The engine copies only the
   discovered/included files to a temporary directory, applies edit specs there, re-scans
   that copy with the same engine, and iterates until clean or a bounded iteration count
   is hit; only a verified patch is presented or applied. Git is never required and the
   user's `.git` state is never touched. Alternative: `git worktree add`. Rejected —
   makes git a hard dependency and mutates repo admin state. Alternative: write-then-
   verify with rollback. Rejected — rollback on a shared working tree risks destroying
   user state.

4. **`--apply` is the only path that writes sources.** Dry-run (print unified diff, write
   nothing) is the default behavior of `conformdag fix`. Alternative: an `--dry-run` opt-in
   flag. Rejected — destructive defaults are unacceptable for a source-mutating command.

5. **Fixability matrix is explicit per check kind.** `required-owner`, `required-tags`,
   `execution-timeout`, `retry-bounds` are mechanical autofix; `top-level-io` is
   proposed-diff-only (structural move of module-scope I/O into task callables, presented but
   never auto-applied); `forbidden-operators` and `idempotence` are NOT autofixed — reported
   as not-fixable for human/agent action. Alternative: best-effort fixes for all kinds.
   Rejected — guessing at semantic fixes breaks the verifier's authority.

6. **Finding schema gains optional remediation payload fields** (concrete configured values,
   code anchor, codemod fix hint) with a report schema minor version bump and backward
   compatibility: existing consumers of the canonical report JSON MUST keep parsing.
   Alternative: a sidecar file. Rejected — the report is the stable contract agents consume.

7. **Round-trip benchmark extends the existing 240-case deterministic gate.** Inject
   violations into a clean DAG corpus, run fix, assert a clean re-scan; regression fails the
   release. Alternative: new standalone harness. Rejected — the gate already exists and is
   wired to release evidence.

8. **Remediation payload schema is minimal and versioned.** Each finding's payload carries
   `fix_kind` (codemod id), `action` (`add-kwarg` / `set-kwarg` / `add-owner` / `add-tags` /
   `move-statement` / `manual`), `kwarg` (the target keyword for kwarg-scoped actions),
   `target` (file, 1-based line/column, enclosing callable, node kind), `value`
   (the concrete configured value), and `hint` (one sentence). The acceptance rule is the
   spec scenario: a model given only the report JSON can reproduce the fix.

## Risks / Trade-offs

- [AST anchor instability across formatting/tools] → Anchors are computed from the parsed AST
  each run, never persisted; the verify-by-rescan loop catches anchor misses as residual
  failures rather than bad writes.
- [Top-level-io structural move produces large, noisy diffs] → Proposed-diff-only, never
  auto-applied even under `--apply`.
- [Temp-copy fidelity vs the real tree] → The copy includes exactly the files the scanner
  discovers (respecting include/exclude); `--apply` replays the verified edit specs onto
  the real tree, so verification and application share one edit-spec source of truth.
- [Report schema bump breaks old consumers] → Minor bump, additive optional fields only;
  round-trip tests assert old parsers still load new reports.

## Migration Plan

Ship behind the new `conformdag fix` command only; `scan` behavior is unchanged except for
additive optional finding fields (minor schema bump). No data migration. Rollback is removal of
the command; the report bump is backward compatible by construction.

## Open Questions

None — resolved at planning (2026-09-02); see decisions 3 and 8.
