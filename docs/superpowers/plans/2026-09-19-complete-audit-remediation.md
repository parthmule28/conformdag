# ConformDAG Complete Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The audit request is the governing specification and this checklist is the execution record.

**Goal:** Close all 47 audit findings while preserving ConformDAG's governance, filesystem, evaluation, agent, state-machine, release, and production-SPA invariants.

**Architecture:** Keep the single scan/evaluation pipeline and add canonical boundary helpers rather than parallel implementations. Make unsafe or ambiguous states explicit in typed models, validate them before execution, and use conditional database transitions/immutable release identities where concurrency or provenance is involved. Every phase ends with focused regression tests, the affected subsystem suite, a diff review, and an issue-accounting update.

**Tech Stack:** Python 3.12, Pydantic, Ruff, AST analysis, FastAPI, SQLAlchemy/Alembic, SQLite/PostgreSQL, Typer, React 19, TypeScript, Vite, Vitest, Playwright, Docker/Compose, GitHub Actions.

**Spec:** The user's `ConformDAG — Complete Audit Remediation` request in this session.

## Global Constraints

- The scanned repository cannot control ConformDAG governance configuration.
- Internal symlink following never escapes the resolved repository root.
- ABSENT, RESOLVED, and UNRESOLVED static values remain distinct.
- Only verified repair files may enter an automated agent patch.
- Terminal state transitions are atomic and healthy workers retain ownership with heartbeats.
- Clean release builds contain the production dashboard and reviewed immutable runtime identities.
- Production SPA routes serve the shell without masking API or missing-asset 404s.
- Do not discard unrelated user changes or generated harness artifacts.

## Review Focus

- Repository-controlled Ruff configuration and malformed selectors: isolated execution and explicit selector validation.
- Deep nested exclusions, chained/external/broken symlinks, and read-only repositories: normalized containment-safe discovery.
- Dynamic timeout expressions and schema-valid check/configuration mismatches: structured incomplete/validation outcomes.
- Concurrent cancellation, long-running claims, migrations, and suppression creation: one-winner transitions and uniqueness.
- Clean package builds, stale runtime tags, deep links, pruned reports, and first-paint theme state: production verification rather than dev-server assumptions.

## Phase Checkpoints

### Phase 1 — Scanner trust boundary and Ruff

- [x] CR-1 Ruff governance isolation
- [x] IMP-1 recursive excludes
- [x] IMP-4 symlink containment
- [x] MIN-1 atomic parse-cache writes
- [x] MIN-3 typed discovery issue categories
- [x] MIN-10 canonical Ruff selector semantics
- [x] Focused Ruff, discovery, symlink, cache, scanner, and fix-engine tests
- [x] Diff/status review and architecture deviations recorded

### Phase 2 — Policy, evaluator, and semantic correctness

- [x] IMP-2 unresolved timeout cannot PASS
- [x] IMP-3 check/configuration compatibility validation
- [x] MIN-4 one semantic evaluation path
- [x] MIN-6 structured provenance read errors
- [x] MIN-7 provider-compatible structured output schemas
- [x] MIN-8 atomic/nonfatal semantic cache persistence
- [x] MIN-9 prose-independent semantic fingerprints
- [x] Focused policy/evaluator/semantic/cache/fingerprint tests and affected suite

### Phase 3 — Agent, pack-pull, CLI, runtime isolation

- [x] IMP-9 explicit verified-file staging
- [x] MIN-2 preserved intentional CLI failures
- [x] MIN-5 pack name/timeout/last-known-good hardening
- [x] MIN-11 runtime manifests outside scanned repositories
- [x] Agent, CLI, pack-pull, runtime, and integration tests

### Phase 4 — Platform state, concurrency, database, API

- [x] IMP-5 atomic cancellation
- [x] IMP-6 worker heartbeat ownership
- [x] IMP-7 application-owned logging
- [x] MIN-12 serialized first-boot migrations
- [x] MIN-13 locked PackService snapshots
- [x] MIN-14 constant-time auth and safe CORS
- [x] MIN-15 DSN absent from subprocess argv
- [x] MIN-16 consistent unknown-scan 404 contract
- [x] MIN-17 airflow profile length validation
- [x] MIN-18 worker timing validation
- [x] MIN-19 retention ordering and claim indexes
- [x] MIN-20 unique suppression identity
- [x] Platform, migration, API, logging, and concurrency suites — 169 passed; Ruff, format, and Pyright clean

### Phase 5 — Release, packaging, runtime, supply chain

- [x] CR-2 enforceable reviewed immutable runtime identity policy
- [x] IMP-8 frontend build is a package-build prerequisite
- [x] MIN-32 occurrence-level artifact privacy checks
- [x] MIN-33 reviewed SHA-pinned release Actions
- [x] MIN-34 production Compose credentials are required
- [x] MIN-35 correct `.superpowers/` ignore decision
- [x] Clean frontend/wheel/install/server smoke verification — 34 affected tests passed; wheel/sdist include static assets; installed server API/SPA/404 smoke passed

### Phase 6 — Production SPA and frontend

- [x] IMP-10 production SPA fallback preserving APIs/assets
- [x] MIN-21 artifact-aware report/export actions
- [x] MIN-22 demo-tour restart route handling
- [x] MIN-23 modal initial focus
- [x] MIN-24 real React act environment/test fixes
- [x] MIN-25 FieldShell ID contract
- [x] MIN-26 pre-paint theme bootstrap
- [x] MIN-27 frontend consistency cleanup
- [x] Frontend tests and packaged-server Playwright verification — platform 171 passed; frontend 121 passed; build, Ruff, Pyright, and packaged Playwright checks passed

### Phase 7 — Documentation and source of truth

- [x] MIN-28 stale release references
- [x] MIN-29 benchmark count
- [x] MIN-30 evaluator registration documentation
- [x] MIN-31 dependency inventory and automated consistency check
- [x] Documentation/inventory/link checks — documentation regressions 6 passed; `mise run inventory`, Ruff, Pyright, diff, and relative-link checks clean

### Phase 8 — Cross-cutting verification

- [x] Adversarial repository fixture — scanner/evaluator/fix regression set 96 passed
- [x] Multi-worker platform scenario — platform state, migration, heartbeat, cancellation, and API suite 171 passed
- [x] Clean release build — `mise run build`; wheel and sdist each contain 3 dashboard assets
- [x] Production browser suite — frontend 6/6 journeys passed; fresh wheel install passed packaged deep-link/theme/tour/API/asset checks
- [x] Complete Python/frontend/platform/integration verification — fresh `mise run check` 481 passed; coverage 90.90%; runtime 15 passed; frontend 148 Vitest tests and 7 Playwright journeys passed; packaged wheel SPA/API/404 smoke, security, privacy, schema, inventory, and 240-case benchmark gates passed
- [x] Final accounting for all 47 IDs and remaining risks — 2 Critical + 10 Important + 35 Minor; every ID is closed in Phases 1–7

## Implementation Method

For each defect: inspect callers and existing abstractions, add a regression test that fails when practical, implement the smallest invariant-preserving change, run the focused test, run the affected subsystem suite, inspect `git diff`/`git status`, and update this checklist. Logical commits may be created only for files belonging to this remediation; unrelated existing changes remain untouched.

## Numbered Execution Tasks

### Task 1: Scanner trust boundary and Ruff enforcement

Implement CR-1, IMP-1, IMP-4, MIN-1, MIN-3, and MIN-10 in `analysis.py`, `ruff_adapter.py`, `evaluator.py`, `scan.py`, and their tests. Finish with the Phase 1 exit gate.

### Task 2: Policy, evaluator, and semantic correctness

Implement IMP-2, IMP-3, MIN-4, MIN-6, MIN-7, MIN-8, and MIN-9 in policy/evaluator/semantic modules with regression tests. Finish with the Phase 2 exit gate.

### Task 3: Agent, pack-pull, CLI, and runtime filesystem isolation

Implement IMP-9, MIN-2, MIN-5, and MIN-11 in the agent, CLI, pack-pull, and runtime paths with regression tests. Finish with the Phase 3 exit gate.

### Task 4: Platform state machine, concurrency, database, and API hardening

Implement IMP-5, IMP-6, IMP-7, MIN-12 through MIN-20 in the platform and migration paths with concurrency/API regression tests. Finish with the Phase 4 exit gate.

### Task 5: Release integrity, packaging, runtime image, and supply chain

Implement CR-2, IMP-8, and MIN-32 through MIN-35 in runtime, packaging, workflows, deployment, and privacy verification. Finish with the Phase 5 exit gate.

### Task 6: Production SPA and frontend correctness

Implement IMP-10, MIN-21 through MIN-27 in the packaged server and frontend with unit, accessibility, and production Playwright tests. Finish with the Phase 6 exit gate.

### Task 7: Documentation and source-of-truth cleanup

Implement MIN-28 through MIN-31 and add inventory/drift checks where practical. Finish with the Phase 7 exit gate.

### Task 8: Cross-cutting integration and final accounting

Run the adversarial repository, multi-worker platform, clean release, and packaged production browser scenarios, then reconcile every audit ID and run the complete verification gates.
