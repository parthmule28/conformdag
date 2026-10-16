# C19 — Fingerprint Contract Formalization: Design

**Date:** 2026-10-16\
**Status:** Proposed for documentation review\
**Baseline:** `main@df6d2dde7165366fe24fd66599284aa84a40f3d2`\
**Backlog:** `docs/consolidation/prompts/C19-fingerprint-contract.md`

## 1. Objective

Formalize the existing finding and report fingerprint contracts so that downstream consumers can rely on explicitly documented, independently tested identity behavior.

C19 is a contract-hardening slice, not an identity migration.

No existing fingerprint may change. No public report schema, persistence contract, suppression lookup, gate behavior, or serialized output may change.

## 2. Ownership

Three existing implementations retain their responsibilities:

- `src/conformdag/checks/common.py` owns deterministic finding fingerprint construction through `structural_fingerprint()`.
- `src/conformdag/semantic_evaluator.py` owns semantic finding fingerprint construction through `semantic_finding()`.
- `src/conformdag/reporting/normalize.py` owns canonical report fingerprint construction through `normalize_report()`.

The new `docs/architecture/fingerprints.md` is the authoritative written compatibility contract. It documents existing source behavior rather than introducing a parallel hashing implementation.

`ScanReport` and `Finding` remain canonical models in `models.py`.

## 3. Finding fingerprint contract

### 3.1 Deterministic findings

The existing helper constructs:

```python
value = f"{policy.id}:{policy.version}:{path}:{anchor}:{status.value}"
fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()
```

The contract therefore depends on policy ID, policy version, the supplied path string, the caller-provided structural anchor, and finding status.

Do not change separators, encoding, field order, status representation, or path handling.

The anchor is selected by each evaluator. Some anchors are structural, while others contain source line numbers, source values, or fallback identifiers derived from line numbers.

Consequently, line-shift stability is conditional, not universal.

### 3.2 Semantic findings

The semantic fingerprint uses canonical JSON comprising:

- `policy_id`
- `policy_version`
- `finding_kind`, fixed to `"semantic"`
- normalized `status`
- `source_path` converted through `as_posix()`, or `None`
- sorted citation descriptors containing `criterion`, `source_type`, `location`, and `unresolved`

Serialization uses:

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"))
```

The resulting UTF-8 bytes are SHA-256 hashed.

Provider explanations, remediation prose, confidence, and citation excerpts are not direct fingerprint inputs. Citation identity and normalized status are inputs.

The `AIR-SEM-001` empty-evidence rule can change normalized status to `NEEDS_REVIEW`; a resulting fingerprint change is therefore expected.

Citation location and unresolved flags can change when validation against included source files changes.

## 4. Report fingerprint contract

`normalize_report()` is the only canonical report fingerprint owner.

It sorts findings, issues, files, and runtime observations according to the currently implemented comparison keys. It creates a separate fingerprint payload and serializes that payload as sorted-key compact JSON, UTF-8 encoded, SHA-256 hashed.

The payload includes complete serialized findings, runtime observations, issues, input hashes, evaluated/skipped policies, completion state, policy-pack metadata, runtime profile/image digest, semantic provider/model, and prompt hashes.

The payload excludes the incoming report fingerprint, run timestamp, gate result, repository revision, resolved configuration, environment, semantic-run diagnostics, tool version, and report version.

**Important distinction:** exclusions from the top-level payload do not imply that similarly named fields embedded within included findings or issues are excluded.

In particular:

- Finding evidence, explanation, remediation, suppression metadata, and other serialized finding fields affect the report fingerprint.
- Suppression provenance and its timestamps can affect the report fingerprint.
- Runtime observation messages and payloads affect the report fingerprint.
- Issue messages affect the report fingerprint.
- Changing semantic provider prose can affect the report fingerprint even when semantic finding identity stays unchanged.

Do not reinterpret report identity as the hash of finding fingerprints alone.

## 5. Compatibility and versioning decision

The current persisted fingerprints are unprefixed SHA-256 hexadecimal strings. Their algorithms do not currently encode an explicit fingerprint version.

C19 will retain that representation.

Do not introduce a version prefix, new JSON field, alternative hash API, or code-only version constant without a concrete consumer requirement and an approved compatibility migration.

The documentation must record the existing algorithms as the **legacy unversioned fingerprint contracts**, with C19 establishing the written reference.

A future change to field selection, source normalization, anchors, hashing, or serialization requires:

1. A reviewed compatibility decision.
2. Golden examples for old and proposed behavior.
3. A migration or coexistence strategy for historical baselines and suppressions.
4. Consumer impact analysis for CLI, platform, agents, reports, and future MCP.
5. Explicit permission to change fingerprints.

## 6. Tests and acceptance

Create focused regression tests under `tests/fingerprints/` without duplicating production hashing helpers.

Required scenarios:

- Deterministic repeatability and exact SHA-256 reference values.
- Policy ID/version, path, anchor, and status sensitivity.
- Stable fingerprint when only an external line argument changes but the anchor stays fixed.
- Changed fingerprint when a line number is embedded within the anchor.
- Semantic citation-order invariance.
- Semantic status, policy version, source path, citation location, and unresolved sensitivity.
- Semantic provider prose exclusion from finding identity.
- Report timestamp, incoming fingerprint, and gate-result exclusion.
- Report sensitivity to serialized finding prose, suppression metadata, source hash changes, and runtime content.
- Frozen C18 report fingerprint and normalized JSON parity.
- Existing suppression and baseline consumers behaving identically.

All tests should use fixed values, explicit dates, and no live semantic provider or network calls.

## 7. Non-goals

C19 must not:

- Redesign finding identity for report diff.
- Replace line-dependent anchors.
- Introduce a new hash algorithm or version prefix.
- Change the report JSON schema or `report_version`.
- Add database migrations.
- Change suppression matching, baseline construction, or gate evaluation.
- Change semantic prompt/cache identities.
- Change renderer output, CLI behavior, platform API, or user interface.
- Begin C20 work.

## 8. Delivery boundaries

**Stage A — Documentation:** Commit this design, its implementation plan, and `docs/architecture/fingerprints.md` in a docs-only PR. Do not begin implementation before approval and merge.

**Stage B — Contract tests:** Add the focused tests, preserve every existing digest, and record C19 as `review`. Open a separate unmerged PR for independent review.

**Acceptance:** Only after Stage B is reviewed, merged with authorization, and post-merge CI passes should C19 be recorded as `accepted` in a subsequent documentation PR.
