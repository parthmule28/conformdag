# C18 — Reporting Package Extraction: Sequential TDD Plan

**Date:** 2026-10-16  
**Status:** Proposed; implementation begins only after the design and this plan are approved  
**Baseline:** `main@c94ad59b92719fb9b22649d1e4fa0b77a0a8eba2`  
**Design:** `docs/superpowers/specs/2026-10-16-c18-reporting-package-design.md`  
**Backlog:** `docs/consolidation/prompts/C18-reporting-package.md`

**Goal:** Replace `conformdag/reporting.py` with an explicit reporting package while preserving every public output and existing call site.

**Implementation mode:** Codex implements sequentially, one task at a time, with test-first red/green evidence. Do not delegate to subagents. ChatGPT owns architecture, decisions, this plan, task changes, and review. Codex must stop and report an unexpected contract disagreement instead of silently revising the plan. Never merge the implementation PR without user authorization.

## Global constraints

- Read `AGENTS.md`, `docs/consolidation/architecture-rules.md`, this design, C18 prompt, and previous C06/C11/C16/C17 context before editing.
- Do not change `ScanReport`, schemas, report_version, result/finding fingerprints, suppression semantics, SARIF/HTML bytes, CLI exit mapping, or platform export contracts.
- Preserve all five facade names: `apply_suppressions`, `normalize_report`, `render_sarif`, `render_html`, **and** `has_blocking_failures` (legacy compatibility).
- No imports from `application`, `platform`, CLI, FastAPI, Typer, SQLAlchemy, Docker, provider adapters, or persistence under `reporting`.
- The only expected product files are new reporting package modules, old reporting module deletion, and the one-line blocking helper in `gates.py`. Caller imports stay at the facade unless a narrower fix is necessary.
- Existing `tests/test_reporting.py` remains; new focused `tests/reporting/` tests may be added. Retarget only the known `datetime` monkeypatch in `tests/application/test_scan.py`.
- Do not force-push, reset hard, discard changes, edit another worktree, delete `.serena/`, or commit generated/static/cache artifacts. The docs-only PR must already be approved/merged before starting product work.
- Keep the implementation PR open and unmerged.

## Precondition: create isolated implementation branch/worktree

Codex verifies:

```bash
git status --short
git fetch origin
git rev-parse origin/main
# Confirm current main includes the approved C18 docs and C17 accepted ledger.
# Create a non-destructive named branch/worktree by the repository's established workflow.
mise run setup
```

If any local changes exist, leave them intact and choose a fresh worktree; do not clean them. Document the actual baseline SHA and toolchain versions. For the initial docs PR, no product changes are authorized; this implementation precondition applies only after docs acceptance.

---

## Task 1 — Baseline capture and report-contract characterization (GREEN on old module)

**Touch:** Add `tests/reporting/test_normalize_contract.py`, `tests/reporting/test_sarif_contract.py`, `tests/reporting/test_html_contract.py`, `tests/reporting/test_suppressions_contract.py`, plus shared typed fixture helper if useful. No product edits yet.

**Sequence:**

1. Read all `reporting.py` lines and the existing tests, `application/outcomes.py`, `gates.py`, `scan.py`, CLI exports, and `platform/routes/scans.py`.
2. Run the baseline focused suite:

```bash
mise exec -- uv run pytest tests/test_reporting.py tests/test_scan.py tests/application/test_scan.py tests/test_cli.py tests/test_platform.py -m 'not runtime' -x --tb=short
```

3. Construct at least one **fixed, nontrivial `ScanReport` fixture** with explicit UTC `RunMetadata.timestamp`, unsorted paths, two or more distinct policies/findings, mixed statuses, issues, runtime observations, nonempty input/prompt hashes, a suppression and sensitive explanation/remediation/evidence. Keep findings fully valid using existing model contracts. Avoid filesystem, random UUID, and wall-clock data.
4. While `reporting.py` is still authoritative, capture frozen expected normalized report JSON, **exact report fingerprint**, SARIF canonical dict/serialized JSON bytes, and HTML **full strings** for `include_evidence=True` and `False`. Place fixed fixtures or digest expectations in tracked tests/golden files as appropriate. Do not compute expected values from the function being tested at assertion time. If storing full HTML is unwieldy, store SHA-256 of complete UTF-8 HTML *plus* targeted escaping/redaction assertions; ensure it was generated from the untouched baseline.
5. Add independent characterization tests: result input isn't mutated; ordering keys (including equal-line ties); ignored timestamps/seed fingerprint; input/prompt dict ordering; policy evaluated/skipped hashing-vs-return behavior; existing gate result excluded from digest; SARIF rule order with PASS included as a rule but no PASS result; severity mapping/locations/suppression; HTML escaping, redaction, evidence toggle; suppressions duplicate/expired/unmatched/provenance/explicit time and original input list unchanged.
6. Run the new tests while still on the old module. Confirm **GREEN** before changing production code. Commit these baseline-only tests first if consistent with project workflow; record baseline evidence.

**Pass:** Frozen outputs and all characterization assertions pass on the old code. A failure means the fixture/expectation needs investigation, not adjusting production behavior.

## Task 2 — Create the package import red test (RED on old module)

**Touch:** `tests/reporting/test_import_contract.py`.

1. Write tests using in-function imports (avoid collection-time failure) for:
   - `conformdag.reporting.normalize.normalize_report`
   - `conformdag.reporting.suppressions.apply_suppressions`
   - `conformdag.reporting.sarif.render_sarif`
   - `conformdag.reporting.html.render_html`
   - `conformdag.gates.has_blocking_failures`
   - Five `conformdag.reporting` facade names, each object identical (`is`) to its new owner. Make test assert `__all__` lists intended stable exports if provided.
2. Run `mise exec -- uv run pytest tests/reporting/test_import_contract.py -x --tb=short` against old module. Expect it to fail because reporting is not a package, or gates does not export the adapter. Record the expected red reason.
3. Do not add unrelated checks or skip the failing test to turn it green prematurely.

**Pass:** Expected RED from missing new module boundaries, not malformed test fixtures.

## Task 3 — Move suppression and normalization without changing behavior (GREEN)

**Touch:** `src/conformdag/reporting/{__init__.py,normalize.py,suppressions.py,sarif.py,html.py}`, `src/conformdag/gates.py`, remove old `src/conformdag/reporting.py`. This must be a coherent importable package in one bounded change.

1. Copy `normalize_report` to `normalize.py` with all sort keys, fingerprint payload, JSON serialization and SHA-256 unchanged. Do not extract a reusable hash helper or alter input fields.
2. Copy `apply_suppressions` to `suppressions.py` with exact identity matching, warnings, order, expiry, preservation rules, and explicit time signature. Keep module-level `datetime` and `UTC` there.
3. Move SARIF/HTML as exact copies concurrently so the facade can import all its renderer exports; Task 4 independently proves their byte parity. Do not leave the tree with broken `conformdag.reporting` imports between commits.
4. Add the one-line `has_blocking_failures` helper in `gates.py` **now**, since the existing `tests/test_reporting.py` imports it. Create the five-name `__init__.py` facade with explicit re-exports and `__all__`. Task 5 will independently prove ownership and object-identity parity.
5. Run `mise exec -- uv run pytest tests/reporting tests/test_reporting.py tests/test_scan.py -m 'not runtime' -x --tb=short`. The full import contract must be green: there are no intentional temporary failing imports at the end of this task.
6. Compare the frozen normalization and suppression assertions against baseline. Inspect a line-level diff between old functions and their new owners (imports aside).

**Pass:** Baseline golden digests/JSON remain identical and existing scan tests pass; no duplicate module remains.

## Task 4 — Prove SARIF and HTML exact parity (GREEN)

**Touch:** `src/conformdag/reporting/sarif.py`, `html.py`, focused renderer tests only.

1. Confirm `render_sarif` was copied without altering status filters, rule first-seen order, severity mapping, region emission, suppression metadata, free-text redaction or shape.
2. Confirm `render_html` was copied with its complete literal template, Jinja environment options, and `template.render(...)` call unchanged. No extraction to a template file or HTML redesign.
3. Run `mise exec -- uv run pytest tests/reporting/test_sarif_contract.py tests/reporting/test_html_contract.py tests/test_reporting.py -x --tb=short`.
4. Verify old-vs-new frozen canonical SARIF dict, the exact serialized JSON wire string using the existing export formatting, and full HTML (or baseline full-content hashes) for both `include_evidence` modes. Include redaction and escape regression assertions.
5. Prove rendering does not mutate the report, recalculate fingerprints, invoke gate evaluation, or write files.

**Pass:** Exact golden parity, no narrowed coverage, unchanged security behavior.

## Task 5 — Move blocking compatibility shim and fix narrow monkeypatch (GREEN)

**Touch:** `tests/application/test_scan.py`, `tests/reporting/test_import_contract.py`; revisit `gates.py` and `reporting/__init__.py` only if the Task 3 compatibility mapping needs correction.

1. Verify the simple compatibility helper added in Task 3 lives in `gates.py` and has the exact original behavior:

```python
def has_blocking_failures(report: ScanReport) -> bool:
    """Return whether the report contains an unsuppressed blocking failure."""
    return bool(blocking_findings(report))
```

2. Verify `reporting/__init__.py` imports and re-exports it alongside the four canonical reporting symbols; `__all__` must list five names and the facade objects must be identical to their owners.
3. Change the one known test monkeypatch target from `"conformdag.reporting.datetime"` to `"conformdag.reporting.suppressions.datetime"` in `tests/application/test_scan.py`. Preserve `application.scan.datetime` patch, the fixed clock and all assertions.
4. Run `mise exec -- uv run pytest tests/reporting/test_import_contract.py tests/application/test_scan.py tests/test_reporting.py -x --tb=short`.
5. Confirm `application/outcomes.py` retains its existing outcome authority; do not rewrite it to import the facade or alter its behavior. Existing consumer imports remain `from conformdag.reporting import ...`.

**Pass:** Five identity-based public imports and fixed-clock application test pass, with gates still the sole blocking owner.

## Task 6 — Full regression and packaging gate

**Touch:** Tests only for a genuinely missing coverage gap; no broader production changes.

Run, in order:

```bash
mise exec -- uv run pytest tests/reporting tests/test_reporting.py tests/test_scan.py tests/application/test_scan.py tests/test_cli.py tests/test_platform.py -m 'not runtime' -x --tb=short
mise run check
mise run test:coverage
mise run schema
mise run validate:packs
mise run privacy
mise run build
git diff --check
```

**Wheel check (not just editable source import):** Inspect the built `.whl` with Python `zipfile` or `unzip -l`; assert the five package files are present, no `conformdag/reporting.py`, and wheel metadata is intact. If practical install that wheel in an isolated throwaway venv and import the five facade entries. Use a path outside the source checkout for the smoke so Python does not accidentally import the local checkout. Do not stage build/static artifacts.

Run an explicit dependency/import audit, ideally via AST or a simple source grep, proving `reporting/` has no app/platform/CLI adapter imports. Review all `git diff --stat`, `git diff`, and `git status --short`, paying special attention to unexpected files or generated output. Check exact text of normalized fingerprint payload before/after. Confirm `conformdag.reporting` is importable in both source and wheel builds.

**Pass:** All gates pass; Pyright 0 errors; >=90% coverage; no schema drift; CLI and platform exports unchanged; no unexpected changes.

## Task 7 — Documentation, commit, and unmerged implementation PR

**Touch:** `docs/consolidation/progress.md` C18 row only (plus tests/product changes already made).

1. Mark C18 `review` (not accepted), with implementation branch/commit and focused/full validation evidence available at the moment. Record all intentional limitations, including private monkeypatch target migration. Never alter C19/C20 status.
2. Commit using `refactor: split reporting package` (docs-only follow-up commit if needed after CI/test evidence). Do not stage `.serena/`, `dist/`, `node_modules/`, `src/conformdag/platform/static/`, build outputs, or unrelated files.
3. Push implementation branch `refactor/c18-reporting-package` and open an **unmerged** PR targeting `main`. Include exact base/head SHA, touched-file summary, frozen fingerprint/renderer comparisons, full command outputs, coverage %, zero type errors, wheel inspection and privacy evidence.
4. Wait for exact-final-head CI and report CI run link/results to ChatGPT. If CI requires fixes, make scoped commits and repeat the gate; do not rewrite history or merge.
5. Preserve the branch/worktree and return to the reviewer with PR URL, exact SHA, review notes, any skipped runtime/semantic checks, and known test limitations.

**Pass:** One focused C18 implementation PR open and green, ready for independent review; no merger performed.

---

## Final reviewer checklist

- [ ] Frozen normalization JSON and fingerprint match untouched C17-accepted baseline.
- [ ] SARIF dict and wire bytes equal baseline; HTML both evidence modes match full baseline.
- [ ] All five facade names import and are identity-equal to canonical owners.
- [ ] Legacy blocking helper delegates to gates, not reporting business logic.
- [ ] All suppression diagnostic, expiry, duplicate and provenance behavior unchanged.
- [ ] Fixed-clock test's monkeypatch target migrated correctly without any assertion weakening.
- [ ] No `conformdag/reporting.py` or duplicated functions remain.
- [ ] No model, fingerprint, schema, CLI exit, API, platform storage, or gate behavior changed.
- [ ] Test/coverage/schema/privacy/build checks and GitHub CI pass.
- [ ] Wheel contains the reporting package; no source-only import illusion.
- [ ] No unapproved scope; C18 PR is **open, unmerged** and ledger `review` only.
