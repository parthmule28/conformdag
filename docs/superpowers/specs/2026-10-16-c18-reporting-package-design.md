# C18 — Canonical Reporting Package Extraction: Design

**Date:** 2026-10-16  
**Status:** Proposed for approval; no implementation authorized by this document alone  
**Consolidation slice:** C18 — Decompose Reporting  
**Baseline:** accepted `main@c94ad59b92719fb9b22649d1e4fa0b77a0a8eba2` (C17 acceptance merge)  
**Required reference:** `docs/consolidation/prompts/C18-reporting-package.md`

## 1. Intent and decision

Refactor the single `src/conformdag/reporting.py` module into a cohesive `conformdag.reporting` package. This is an **ownership-only extraction**, not a reporting redesign. The canonical `ScanReport` model, report/result fingerprint algorithm, suppression behavior, SARIF payload, HTML bytes, CLI/API exports, and exit/gate decisions must remain unchanged.

The report is already the canonical typed scan artifact and JSON is its public serialization. The four responsibilities currently combined in `reporting.py` will have one owner each; public callers retain imports from `conformdag.reporting`. The old `has_blocking_failures()` compatibility entry point will also remain available, but blocking semantics will be owned by `conformdag.gates`.

## 2. Verified baseline and dependencies

- The source module currently defines `apply_suppressions()`, `normalize_report()`, `has_blocking_failures()`, `render_sarif()`, and `render_html()`.
- `src/conformdag/scan.py` and `src/conformdag/application/scan.py` import `apply_suppressions` and `normalize_report` from `conformdag.reporting`.
- `src/conformdag/cli.py` and `src/conformdag/platform/routes/scans.py` import `render_sarif` and `render_html` from `conformdag.reporting`. The platform export endpoint formats SARIF using `json.dumps(..., indent=2, sort_keys=True) + "\n"`; the CLI uses the same representation.
- `src/conformdag/application/outcomes.py` already calls `conformdag.gates.blocking_findings` and owns outcome classification. `src/conformdag/gates.py` owns blocking finding selection and gate evaluation.
- `tests/test_reporting.py` characterizes local/operational suppressions, duplicated/expired/unmatched cases, projection redaction, and blocking. `tests/application/test_scan.py` includes a clock-patching test that targets `conformdag.reporting.datetime`. `tests/test_platform.py` checks byte-equal platform SARIF/HTML exports against the renderer functions.
- The C18 backlog requires import parity, report/fingerprint/output regression tests and no change to fingerprint inputs. C19 will specify the explicit fingerprint contract and C20 will address baseline/suppression unification.

## 3. Final ownership and package topology

```text
src/conformdag/
  gates.py                         # Existing owner: blocking_findings, gate semantics
  reporting/
    __init__.py                    # Stable compatibility facade (explicit re-exports)
    normalize.py                   # normalize_report and unchanged fingerprint payload
    suppressions.py                # apply_suppressions and diagnostics
    sarif.py                       # render_sarif and SARIF projection/redaction
    html.py                        # render_html and exact HTML template/redaction
```

Remove `src/conformdag/reporting.py` in the *same change* that introduces the package. Never leave competing module/package owners in the final tree. Leave `models.ScanReport` in `models.py`; do not add another report DTO or serialized representation.

| Function | Canonical owner | Public compatibility entry |
| --- | --- | --- |
| `normalize_report(report: ScanReport) -> ScanReport` | `reporting.normalize` | `conformdag.reporting.normalize_report` |
| `apply_suppressions(findings, suppressions, now=None, *, preserve_existing_provenance=False) -> tuple[list[Finding], list[RunIssue]]` | `reporting.suppressions` | `conformdag.reporting.apply_suppressions` |
| `render_sarif(report: ScanReport) -> dict[str, object]` | `reporting.sarif` | `conformdag.reporting.render_sarif` |
| `render_html(report: ScanReport, include_evidence: bool = True) -> str` | `reporting.html` | `conformdag.reporting.render_html` |
| `has_blocking_failures(report: ScanReport) -> bool` | `conformdag.gates` (thin `bool(blocking_findings(report))` adapter) | `conformdag.reporting.has_blocking_failures` |

`reporting/__init__.py` re-exports these five names via explicit imports and an explicit `__all__`, without copied business logic or wrapper differences. Their existing public positional/keyword signatures and return types stay identical. Tests must prove facade objects are identical to their canonical implementations (`is`, not merely equivalent calls). Avoid new cross-module helper abstractions where a straightforward move preserves existing behavior.

### Dependency direction

- `reporting.normalize`: standard library `hashlib`/`json`, plus `conformdag.models`.
- `reporting.suppressions`: standard library `datetime`, plus `conformdag.models`.
- `reporting.sarif`: `conformdag.models` and the existing `conformdag.security.redaction.redact_credentials`.
- `reporting.html`: `jinja2`, `conformdag.models`, and the same redaction helper.
- `conformdag.gates`: existing core models and blocking/gate semantics; no reporting imports.
- `reporting.__init__`: exports from the reporting submodules and the established gates owner.

No reporting module may depend on `cli`, `application`, `platform`, FastAPI, SQLAlchemy, Typer, Docker, provider transport, or other adapters. Report production can import reporting inward; reporting must not import those producers.

## 4. Exact contracts to retain

### 4.1 Normalization and fingerprint

Move the complete implementation of `normalize_report` to `normalize.py` without modifying computation, sort keys, serialization, `model_copy` behavior, or hash input selection. Specifically preserve:

- Findings order: `(policy_id, str(location.file), start_line or 0, fingerprint)`.
- Issues order: `(phase, code, str(path))`.
- `files_scanned` order: `str(path)`.
- Runtime observations order: `(policy_id, status.value, message or "")`.
- Fingerprint payload fields **exactly** as presently implemented: `complete`, sorted files, sorted `policies_evaluated` and `policies_skipped` *for hashing*, serialized findings/observations/issues, sorted run input hashes, policy pack ID/version, runtime profile/image digest, semantic provider/model, and sorted prompt hashes.
- Preserve `json.dumps(payload, sort_keys=True, separators=(",", ":"))`, UTF-8 encoding, and SHA-256 hex digest.
- Keep exclusions from the payload: timestamp, incoming `result_fingerprint`, gate result, run repository revision, environment, resolved configuration, and semantic-run diagnostics. Do not extend or reduce inputs as part of C18.
- `normalize_report` returns a model copy; it must not mutate the supplied `ScanReport`. It must not silently reorder the `policies_evaluated` / `policies_skipped` lists in the *returned report* merely because sorted copies are used in the fingerprint payload.
- Finding fingerprints are produced elsewhere and remain untouched. Report `report_version`, JSON keys, and schema stay unchanged.

Baseline parity MUST compare at least one fixed, nontrivial report's exact fingerprint and complete normalized `model_dump(mode="json")` with baseline output **captured before extraction**. Also assert timestamp-only, pre-existing fingerprint-only, and input-order variations according to existing normalization behavior. Never rewrite the expected digest after a mismatch without diagnosing it.

### 4.2 Suppression behavior

Move `apply_suppressions` as-is to `suppressions.py`:

- `now=None` uses `datetime.now(UTC)`; an explicit `now` is honored exactly.
- Duplicate suppression identities `(policy_id, fingerprint)` generate `SUPPRESSION_DUPLICATE` diagnostics in current sequence.
- Unmatched suppressions generate `SUPPRESSION_UNMATCHED` and have no effect.
- Expiry comparison stays `expires_at <= current`, with the same `SUPPRESSION_EXPIRED` messages and already-suppressed provenance warning semantics.
- Active matches suppress each matching finding; by default later duplicates replace suppression provenance. With `preserve_existing_provenance=True`, an already-suppressed finding retains prior provenance.
- Diagnostics retain code, text, phase, sequence, and nonfatal defaults; returned findings remain in input order and the input list is not mutated.
- Do not unify local/operational stores or alter suppression expiry semantics (C20).

**Known test monkeypatch:** `tests/application/test_scan.py::test_execute_scan_ignores_operational_suppression_expired_before_application` currently calls `monkeypatch.setattr("conformdag.reporting.datetime", fixed_clock)`. After the extraction, retarget **only that test's clock patch** to `conformdag.reporting.suppressions.datetime`. Keep the `conformdag.application.scan.datetime` patch and all outcome assertions. Do **not** introduce a facade-to-submodule dynamic clock dependency to preserve a private monkeypatch seam; the public suppression API's explicit `now` parameter remains the stable test seam. Document this narrow test-only migration in the implementation PR.

### 4.3 SARIF

Copy the existing `render_sarif` implementation verbatim into `sarif.py` aside from local imports. Preserve SARIF version `2.1.0`, top-level `$schema`, dictionary and array ordering, `tool.driver` metadata, `automationDetails.id`, rule first-seen order, rule inclusion for `PASS` findings even though PASS results are skipped, severity mapping, emitted non-PASS results, physical locations/regions, suppression markers, redaction of explanations and remediation, and JSON wire encoding by downstream consumers.

No SARIF renderer may infer gate outcomes, recalculate report/finding fingerprints, or reorder findings. Add exact dictionary/serialized-output regression fixtures, including PASS, FAIL, ERROR and suppressed findings; include source locations and redacted secrets. Do not silently modernize SARIF format.

### 4.4 HTML

Copy the `render_html` implementation, embedded Jinja template **verbatim**, and existing environment configuration to `html.py` (including autoescaping, trimming/lstrip, CSS, markup, and whitespace). The returned HTML string must compare byte-for-byte with the same fixed report on baseline. Preserve `include_evidence=True` default, `False` behavior, accessible headers/table markup, credential redaction, Jinja escaping of text, and standalone offline output. Do not extract or restyle the template, add dependencies/CDNs/JS, or alter escaping as part of C18.

### 4.5 Blocking classification and compatibility

`has_blocking_failures` currently lives in reporting but delegates to `gates.blocking_findings`. C18 should place the same one-line boolean adapter in `gates.py` and re-export it through `reporting/__init__.py`. `classify_report` remains in `application/outcomes.py` and gate policy remains in `gates.py`; neither is modified. Existing `from conformdag.reporting import has_blocking_failures` must continue to work. No new CLI exit code, gate policy, or adapter-specific outcome logic.

## 5. Import, packaging, and migration strategy

1. Characterize the old module on the accepted C17 baseline with deterministic fixture output before moving the code.
2. Add a test-first new submodule import contract and prove it fails because the package does not exist.
3. In one bounded refactor, create package files and facade, and delete the old `reporting.py`.
4. Prefer leaving existing `from conformdag.reporting import ...` import statements in the scanner, application, CLI, platform, and existing tests in place; this is the compatibility contract. Narrow importer changes are allowed only where strictly required and with tests.
5. Retarget the single known internal `datetime` monkeypatch to the canonical suppression module.
6. Keep existing `tests/test_reporting.py` as end-to-end public API coverage; add focused `tests/reporting/` characterization and ownership tests. Avoid unrelated test reshuffling.
7. Verify editable-install imports **and built wheel** contents: wheel must contain `conformdag/reporting/__init__.py`, `normalize.py`, `suppressions.py`, `sarif.py`, and `html.py`, with no orphan `conformdag/reporting.py` entry. Verify package exports using installed wheel if practical, not just source checkout.

No update to Python models/schema files, config, migrations, frontend, API operation IDs, JSON schema, policies, engine workflows, evaluator, fix engine, or packaging configuration should be necessary.

## 6. Test and acceptance matrix

| Layer | Required assertion |
| --- | --- |
| Facade | Five public imports work, identities match new owners, signatures and keywords preserved |
| Normalization | Frozen before/after fingerprint and report JSON parity; sort, timestamp, ignored-field behavior |
| Suppressions | Active, duplicate, expired, unmatched, multi-finding, explicit time, provenance preservation, no input mutation |
| SARIF | Exact canonical dict + serialized bytes; pass/nonpass, rules order, suppression, region, redaction |
| HTML | Exact fixed output, evidence on/off, escaping, redaction, accessible table, offline self-containment |
| Application | Complete flow still normalizes and applies operational suppressions; clock test migrated |
| CLI/API | JSON/SARIF/HTML exports and byte parity, no exit code/auth/status/content-type changes |
| Packaging | Built wheel contains package modules and stable facade imports; no stale module |
| Boundaries | Reporting has no app, platform, HTTP, Typer, SQLAlchemy, gate outcome policy, or persistence logic |

**Verification commands:**

```bash
mise run setup
mise exec -- uv run pytest tests/test_reporting.py tests/test_scan.py tests/application/test_scan.py tests/test_cli.py tests/test_platform.py -m 'not runtime' -x --tb=short
mise run check
mise run test:coverage
mise run schema
mise run validate:packs
mise run privacy
mise run build
git diff --check
```

CI must pass its required jobs on the final implementation PR head. Optional semantic provider smoke may remain skipped. Coverage must pass >=90% and Pyright strict must report zero errors. No comparison is considered complete if generated fixture bytes are recalculated from the post-refactor code alone.

## 7. Explicit non-goals and deferred work

- **C19:** Change/specification/versioning of fingerprint inputs, finding identity, and hashing contract.
- **C20:** Unification of baseline/suppression workflows and persistence.
- **C21+:** Model, platform persistence, transports, or concurrency redesign.
- No new renderer formats, CLI options, release behavior, notification/callbacks, storage, Docker, semantic execution, or UI changes.
- No SQL or platform ownership imported into the reporting core.
- No unrelated formatting churn; retain minimal diff for independent review.

## 8. PR boundary and review criteria

**Docs approval first:** this design and its task plan are authored by ChatGPT and should be committed through a docs-only PR, reviewed and merged before implementation starts. Do not alter C18 progress state to `accepted` merely because design docs are approved.

**Implementation PR:** branch `refactor/c18-reporting-package`; conventional commit `refactor: split reporting package`; leave open/unmerged with test evidence. Move C18 progress row to `review` on the implementation PR with exact head SHA, CI results when available, and known limitations; `accepted` requires an authorized merge plus post-merge main CI and a separate acceptance record.

Reviewers should focus on byte/fingerprint parity, five-symbol import parity, suppression clock migration, dependency direction, wheel packaging, and the absence of scope creep. Any proposed behavior change must stop and return for an explicit design decision; it is not authorized by C18.
