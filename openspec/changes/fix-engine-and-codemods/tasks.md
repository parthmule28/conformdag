## 1. Report verbosity audit

- [x] 1.1 Audit every check kind's findings for self-containment: a reader with only the report
      JSON can act without re-reading the repository
- [x] 1.2 Catalog missing context per check kind (concrete configured values, code anchors,
      policy contract references) and record gaps as schema requirements

## 2. Models / remediation payload schema

- [x] 2.1 Add optional remediation payload fields to the finding model (configured values from
      pack config, code anchor, codemod fix hint)
- [x] 2.2 Bump the canonical report schema minor version; assert backward compatibility (old
      parsers load new reports; absent fields behave as today)
- [x] 2.3 Populate remediation payloads from the evaluator for all check kinds, including
      not-fixable kinds

## 3. Fixer protocol and registry

- [x] 3.1 Define the fixer protocol (finding + pack config in; structured edit spec or
      not-fixable out) mirroring the evaluator protocol
- [x] 3.2 Implement the fixer registry keyed by check kind (not policy ID), with an explicit
      fixability matrix entry per registered kind
- [x] 3.3 Render structured edit specs (file, AST anchor, replacement) to unified diffs; no raw
      string surgery anywhere

## 4. Mechanical codemods

- [x] 4.1 `required-owner` codemod: set the configured owner value
- [x] 4.2 `required-tags` codemod: add missing configured tags, preserving existing ones
- [x] 4.3 `execution-timeout` codemod: add/raise the `execution_timeout` kwarg to the
      configured bound
- [x] 4.4 `retry-bounds` codemod: clamp `retries` into the configured min/max window
- [x] 4.5 Unit tests: each codemod is deterministic (same input, byte-identical diff) and
      reports `forbidden-operators` / `idempotence` findings as not-fixable

## 5. Proposed-diff path for top-level-io

- [x] 5.1 Structural-move codemod: relocate module-scope I/O into task callables as a
      proposed-only diff (never auto-applied, including under `--apply`)

## 6. Worktree verify loop

- [x] 6.1 Apply edit specs to an isolated patched copy (temp-copy of discovered files; git is
      never required and `.git` state is never touched) — never the shared working tree
- [x] 6.2 Re-scan the patched copy with the same scan engine; iterate until clean or the
      bounded iteration count is hit
- [x] 6.3 Surface residual failures (finding id, iteration count) when the loop exits unclean

## 7. `conformdag fix` CLI

- [x] 7.1 Add `conformdag fix` with dry-run default: print unified diff, write nothing
- [x] 7.2 Add `--apply` as the only path that writes sources (post-verification only)
- [x] 7.3 Add `--policy-pack` passthrough to the scan engine

## 8. Round-trip benchmark and CI gate

- [x] 8.1 Extend the existing 240-case deterministic gate with a round-trip stage: inject
      violations into a clean DAG corpus, run fix, assert a clean re-scan
- [x] 8.2 Wire the round-trip benchmark into CI; regression fails the build

## 9. Docs and release evidence

- [x] 9.1 Add the fix section to the user guide (dry-run default, `--apply`, fixability
      matrix, residual-failure meaning)
- [x] 9.2 Record release-gate evidence: round-trip benchmark results attached to the release
      checklist
