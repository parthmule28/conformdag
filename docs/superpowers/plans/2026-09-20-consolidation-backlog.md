# ConformDAG Consolidation Backlog Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a durable, exact OpenCode execution backlog for consolidation slices C01–C64.

**Architecture:** Keep the supplied consolidation blueprint as the governing design and split its execution record into one program index, one progress ledger, one architecture contract, one measured baseline, and one self-contained Build prompt per PR-sized slice. The artifacts are documentation-only and do not alter product behavior.

**Tech Stack:** Markdown, Git, `mise`, `uv`, Ruff, Pyright, pytest, and repository-local Markdown/link checks.

**Spec:** `docs/superpowers/specs/2026-09-20-consolidation-backlog-design.md`

## Global Constraints

- The backlog treats C01 through C64 as independently reviewable PR-sized slices.
- Every Build prompt requires current-file/caller inspection before editing.
- The canonical scan primitive remains `scan_repository()` until an application workflow has parity tests.
- Existing public imports, CLI entry points, report JSON, policy schemas, and HTTP contracts remain compatible unless a prompt names the migration and its deprecation evidence.
- Agents must not use destructive Git operations or delete unrecognized user work.
- The final prompt set must distinguish ordinary local gates from expensive Postgres, Docker, browser, packaging, benchmark, and independent-review gates.

## Review Focus

- A prompt could accidentally authorize a second scan pipeline; C03, C06, C10, and C27 explicitly test ownership and parity.
- A structural move could silently break imports or public wire shapes; C04, C16, C21, C30, and C31 require facade/schema checks.
- A generated link or prompt reference could drift; the final artifact validation checks every C01–C64 link and dependency name.
- Baseline measurements could be presented as guesses; `baseline.md` records commands and observed values separately.
- Repetitive prompts could omit a required contract section; a structural validator checks all 64 prompt headings.

---

### Task 1: Create the consolidation program contract

**Files:**
- Create: `docs/consolidation/README.md`
- Create: `docs/consolidation/architecture-rules.md`
- Create: `docs/consolidation/baseline.md`
- Create: `docs/consolidation/progress.md`
- Create: `docs/consolidation/backlog.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-09-20-consolidation-backlog-design.md` and the supplied C01–C64 blueprint.
- Produces: the stable paths and status vocabulary consumed by every prompt file.

- [x] **Step 1: Record measured repository state**

  Use the characterized local `main` snapshot (`68a837c`) and record observed values, commands, known exclusions, and the distinction between local and remote branch state.

- [x] **Step 2: Write ownership and safety rules**

  Preserve one scan engine, verify-by-rescan fixing, offline default, trust-boundary separation, canonical reports, compatibility facades, Alembic-only schema changes, and the authoritative check catalogue.

- [x] **Step 3: Write the index and execution ledger**

  Give every slice one title, one prompt link, dependencies, risk, required gates, and an initially planned status.

- [x] **Step 4: Validate the program contract**

  Run `git diff --check` and inspect the generated tables before adding prompts.

- [x] **Step 5: Commit**

  ```bash
  git add docs/consolidation
  git commit -m "docs: publish consolidation backlog contract"
  ```

### Task 2: Create self-contained Build prompts C01–C16

**Files:**
- Create: `docs/consolidation/prompts/C01-*.md` through `C16-*.md`

**Interfaces:**
- Consumes: the program contract from Task 1 and current source/test paths.
- Produces: prompts for baseline, vocabulary, check catalogue, analysis, deterministic checks, application scan, configuration, profile use, state typing, runner delegation, outcomes, services, routes, contracts, redaction, and policy decomposition.

- [x] **Step 1: Apply the required ten-section prompt contract**
- [x] **Step 2: Add exact files, symbols, test commands, allowed scope, and prohibitions**
- [x] **Step 3: Add risk-specific gates and compatibility evidence**
- [x] **Step 4: Validate headings and cross-slice names**
- [x] **Step 5: Commit**

  ```bash
  git add docs/consolidation/prompts/C0{1..9}-*.md docs/consolidation/prompts/C1{0..6}-*.md
  git commit -m "docs: add early consolidation build prompts"
  ```

### Task 3: Create self-contained Build prompts C17–C32

**Files:**
- Create: `docs/consolidation/prompts/C17-*.md` through `C32-*.md`

**Interfaces:**
- Consumes: the application/service boundaries named by C06–C16.
- Produces: prompts for policy editing, reporting, fingerprints, baseline unification, model/semantic/runtime/persistence packages, transactions, Postgres, worker cleanup, CLI packaging, CLI output, compatibility, OpenAPI types, and frontend API cleanup.

- [x] **Step 1: Describe exact domain interfaces before adapter migrations**
- [x] **Step 2: Pin persistence, schema, and generated-contract gates**
- [x] **Step 3: Add test-first sequences for each migration**
- [x] **Step 4: Validate prompt references against the index**
- [x] **Step 5: Commit**

  ```bash
  git add docs/consolidation/prompts/C1{7..9}-*.md docs/consolidation/prompts/C2{0..9}-*.md docs/consolidation/prompts/C3{0..2}-*.md
  git commit -m "docs: add boundary migration build prompts"
  ```

### Task 4: Create self-contained Build prompts C33–C64

**Files:**
- Create: `docs/consolidation/prompts/C33-*.md` through `C64-*.md`

**Interfaces:**
- Consumes: the migrated boundaries and contracts named by C01–C32.
- Produces: prompts for test structure, true coverage, property/mutation review, dependency/package/container/CI audits, architecture/import/filesystem/observability/error/config reviews, demo/benchmark cleanup, documentation, threat/adversarial/stress/performance review, release rehearsal, enforcement, and final reporting.

- [x] **Step 1: Keep every late-stage review tied to an observable gate**
- [x] **Step 2: Name permanent regression suites and independent-review evidence**
- [x] **Step 3: Add final accounting and clean-machine requirements**
- [x] **Step 4: Validate all 64 prompt files structurally**
- [x] **Step 5: Commit**

  ```bash
  git add docs/consolidation/prompts/C3{3..9}-*.md docs/consolidation/prompts/C4{0..9}-*.md docs/consolidation/prompts/C5{0..9}-*.md docs/consolidation/prompts/C6{0..4}-*.md
  git commit -m "docs: complete consolidation build prompt backlog"
  ```

### Task 5: Run final artifact self-review

**Files:**
- Modify: `docs/consolidation/backlog.md` if link or dependency corrections are required
- Modify: `docs/consolidation/progress.md` if validation evidence needs recording

**Interfaces:**
- Consumes: all files created by Tasks 1–4.
- Produces: a committed backlog whose 64 links, headings, dependency names, and prohibitions are internally consistent.

- [x] **Step 1: Check every prompt exists exactly once**

  Run a shell assertion over `docs/consolidation/backlog.md` and `docs/consolidation/prompts/`.

- [x] **Step 2: Scan for forbidden placeholders**

  Search prompts for unresolved `TBD`, `TODO`, `FIXME`, “implement later”, “add appropriate”, and “write tests for the above”.

- [x] **Step 3: Run Markdown hygiene checks**

  Run `git diff --check`, the concrete local-link command recorded in C01, and inspect the complete diff.

- [x] **Step 4: Record evidence in the ledger**

  Leave C01–C64 marked `planned`; this backlog does not claim any product slice is implemented.

- [x] **Step 5: Record the completed artifact commit**

  No additional commit is required here; the final artifact batch was committed as `71926be docs: complete consolidation build prompt backlog` after this validation.
