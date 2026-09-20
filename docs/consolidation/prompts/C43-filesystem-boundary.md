# C43 — Consolidate Filesystem Containment Helpers

## Role and objective

You are the Build agent for C43. Centralize reusable repository-relative path containment checks for future MCP and adapters while preserving analysis discovery's specialized symlink policy.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C04/C15/C41.
- `src/conformdag/analysis/discovery.py` or current analysis module, platform repository registration, fixing/Git staging paths, runtime mounts, and all path helpers.
- Symlink/traversal tests and agent Git safety tests.

## Current ownership and resulting owner

Path normalization/containment logic is repeated or embedded in discovery, platform, fixing, and agent code. After this PR, a small security/filesystem module owns generic `resolve_repository_root`, `ensure_child_path`, and repository-relative normalization helpers; discovery retains its own internal/external/broken symlink semantics.

## Interfaces

Define typed helpers with explicit symlink-following policy and errors. A path outside the resolved root, absolute outside path, traversal normalization, or escaping symlink must fail; internal symlink handling remains caller-controlled.

## Expected files

- Create: `src/conformdag/security/filesystem.py` or the agreed security boundary and focused tests.
- Modify: platform registration, fixing/Git staging, agent verifier, application/MCP-ready boundaries, and discovery only where generic containment is appropriate.
- Do not replace specialized discovery symlink logic with a generic helper.

## Test-first sequence

1. Add adversarial tests for `../`, absolute outside paths, normalization tricks, internal/external/broken symlinks, read-only roots, and dirty target files.
2. Run current discovery/fixing/agent/platform tests.
3. Implement helpers with explicit root and symlink semantics and migrate callers one boundary at a time.
4. Run security, discovery, fixing, agent, platform, and architecture tests.

## Allowed changes

- Containment helpers, caller migration, typed errors, and permanent adversarial tests.

## Non-goals and prohibitions

- Do not follow external symlinks, execute repository code, or broaden write roots.
- Do not conflate repository containment with pack provenance or Docker mount policy.

## Verification matrix

- Adversarial filesystem suite, default gate, architecture task, privacy/security checks.
- Independent review of every caller's symlink policy.

## Completion checklist and handoff

- [ ] Generic containment has one owner.
- [ ] Discovery retains specialized symlink behavior.
- [ ] Fixing/agent writes remain explicitly scoped and verified.
- [ ] Commit with `fix: centralize filesystem containment`; open the PR without merging.
