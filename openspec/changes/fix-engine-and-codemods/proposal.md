## Why

The agentic enforcement vision (ADR 0003) stands on a deterministic fix engine: the agentic
harness that consumes reports and raises PRs is a later change, and its ceiling is set by the
quality of the fixes and the verbosity of the report it reads. Phase 1 is that engine — fully
offline, no LLM, no credentials — plus the agent-readable output contract the fix loop depends
on. Because fix-loop quality is bounded by report verbosity, the finding schema must be hardened
first so every finding is self-contained for a model consumer.

## What Changes

- Add a fixer protocol and a fixer registry mirroring the evaluator registry (registered by
  check kind, not policy ID).
- Ship one codemod per check kind behind an explicit fixability matrix: `required-owner`,
  `required-tags`, `execution-timeout`, `retry-bounds` are mechanical autofix; `top-level-io`
  is proposed-diff-only (structural move); `forbidden-operators` and `idempotence` are NOT
  autofixed (human/agent-only).
- Add `conformdag fix` with dry-run default and `--apply` as the only path that writes sources,
  with `--policy-pack` passthrough to the scan engine.
- Verify-by-rescan on an isolated patched git worktree (or temp copy) BEFORE any write,
  re-scanning until clean or a bounded iteration count is hit.
- Add a round-trip benchmark gate: inject violations into a clean DAG corpus, run fix, assert a
  clean re-scan — extending the existing 240-case deterministic gate.
- Run a report-verbosity audit making every finding self-contained for a model consumer:
  remediation payloads carrying concrete values from pack config, code anchors, and codemod fix
  hints. Report schema gets a minor version bump with backward compatibility.

## Capabilities

### New Capabilities

- `fix-engine`: Deterministic fix engine and agent-readable finding contract — dry-run by
  default with `--apply` as the only write path, per-check-kind codemods with an explicit
  fixability matrix, verify-by-rescan on an isolated copy with bounded iterations,
  self-contained findings with remediation payloads, a round-trip benchmark release gate, and
  fully offline operation (no network, no credentials, no provider).

### Modified Capabilities

None (no main specs exist yet; the report schema minor bump is carried inside this change).

## Impact

- `src/conformdag`: new fix module (protocol, registry, codemods, worktree verify loop) and
  models additions (remediation payload fields, report schema minor version bump).
- CLI: new `conformdag fix` command (dry-run default, `--apply`, `--policy-pack` passthrough).
- Benchmarks and CI: round-trip benchmark and release-gate wiring.
- Docs: user-guide fix section.
- No LLM, no network, no credentials anywhere in this change.
