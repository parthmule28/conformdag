# ConformDAG Fingerprint Contracts

**Contract established:** C19\
**Algorithms:** Existing unversioned contracts\
**Reference baseline:** `main@df6d2dde7165366fe24fd66599284aa84a40f3d2`

## Purpose

This document specifies the current identity algorithms for findings and canonical scan reports.

Fingerprints are compatibility-sensitive because they are used for suppression matching, baseline comparison, gate evaluation, report exports, and platform records.

A finding fingerprint identifies an evaluation outcome under its current inputs. A report fingerprint identifies a broader canonicalized report payload.

These are different kinds of identity and must not be interchanged.

## 1. Deterministic finding identity

**Owner:** `conformdag.checks.common.structural_fingerprint`

### Construction

```python
value = f"{policy.id}:{policy.version}:{path}:{anchor}:{status.value}"
fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()
```

No explicit version prefix, escaping of colon separators, or additional path normalization occurs inside this helper.

### Included inputs

| Input | Source |
|---|---|
| Policy ID | `policy.id` |
| Policy version | `policy.version` |
| Path | Caller-supplied string |
| Anchor | Caller-supplied string |
| Status | `status.value` |

Source line numbers are not separate parameters to this helper, but may be included inside an anchor.

Examples of existing anchors include DAG variables, source values, task identifiers, and `ruff:{code}:{row}`.

**Stability limitation:** A line shift does not change the fingerprint when all five inputs stay the same. A shift can change the fingerprint when the evaluator incorporates a line number into the anchor.

The contract does not guarantee stable identities after arbitrary source edits, renames, policy upgrades, or status transitions.

## 2. Semantic finding identity

**Owner:** `conformdag.semantic_evaluator.semantic_finding`

The payload is:

```python
{
    "policy_id": policy.id,
    "policy_version": policy.version,
    "finding_kind": "semantic",
    "status": status.value,
    "source_path": source_path.as_posix() if source_path is not None else None,
    "citations": sorted(
        [
            {
                "criterion": item.criterion,
                "source_type": item.source_type,
                "location": item.location,
                "unresolved": item.unresolved,
            }
            for item in audit_evidence
        ],
        key=lambda item: (
            str(item["criterion"]),
            str(item["source_type"]),
            str(item["location"]),
            bool(item["unresolved"]),
        ),
    ),
}
```

Serialization and hashing:

```python
payload_bytes = json.dumps(
    payload, sort_keys=True, separators=(",", ":")
).encode("utf-8")

fingerprint = hashlib.sha256(payload_bytes).hexdigest()
```

The actual implementation remains authoritative if the above descriptive transcription is later found to differ.

### Included

Normalized status, source path, policy identity/version, and normalized citation descriptors.

### Excluded

Provider explanation text, remediation prose, confidence, citation excerpt text, latency, token usage, and semantic context hash as direct inputs.

### Qualifications

The normalized citation list is not necessarily identical to raw provider-supplied citations. Unknown citation locations can become unresolved.

A provider decision can be normalized to a different status, including the existing `AIR-SEM-001` empty-evidence rule.

Changing the included citation descriptor fields, normalization rules, or status may change the fingerprint.

Excluding provider prose from *semantic finding identity* does not imply that the complete report fingerprint excludes it.

## 3. Canonical report identity

**Owner:** `conformdag.reporting.normalize.normalize_report`

### Ordering

Before calculating the hash:

| Collection | Sort key |
|---|---|
| Findings | `policy_id`, `str(location.file)`, `start_line or 0`, `fingerprint` |
| Issues | `phase`, `code`, `str(path)` |
| Files | `str(path)` |
| Runtime observations | `policy_id`, `status.value`, `message or ""` |
| Evaluated/skipped policies in hash payload | Lexicographic ordering |
| Input/prompt hash mappings | Sorted keys |

The returned report retains the existing order of `policies_evaluated` and `policies_skipped`; their sorted copies are used for hashing.

### Included payload fields

- `complete`
- `files_scanned`
- `policies_evaluated`
- `policies_skipped`
- `findings`, as complete `model_dump(mode="json")` values
- `runtime_observations`, as complete serialized values
- `issues`, as complete serialized values
- `input_hashes`
- `policy_pack_id`
- `policy_pack_version`
- `runtime_profile`
- `runtime_image_digest`
- `semantic_provider`
- `semantic_model`
- `prompt_hashes`

The payload is JSON-serialized with `sort_keys=True` and compact separators `(",", ":")`, encoded as UTF-8, then hashed using SHA-256.

### Excluded top-level fields

- Previous `result_fingerprint`
- Run timestamp
- Gate result
- Report version
- Tool version
- Repository revision
- Run environment
- Resolved configuration
- Semantic-run diagnostic metadata

These exclusions refer only to the fields omitted from the report hash payload. Complete included subobjects can themselves contain text, timestamps, and other variable fields.

### Important consequences

A changed report fingerprint does not necessarily indicate a newly introduced policy violation.

For example, report fingerprints may change because source-content hashes, explanatory text, evidence, suppression details, issues, runtime observations, or semantic provider/model metadata change.

Conversely, the excluded run timestamp alone does not change the result fingerprint.

## 4. Existing consumer contracts

**Suppressions:** Match `(policy_id, finding.fingerprint)`. They do not use the report fingerprint as the finding identifier.

**No-new-findings gate:** Compares finding fingerprints from the current report with those in its baseline.

**Platform:** Stores and exposes existing fingerprint values. C19 does not introduce a new version field, schema, or migration.

**Report exports:** JSON remains canonical. SARIF consumes the report fingerprint in `automationDetails.id` and finding fingerprints in result properties. HTML displays the report fingerprint.

**Fix verification:** Continues using the established scan/rescan workflow and existing finding/report identities.

## 5. Security and portability limitations

- The deterministic helper hashes the caller-provided path and anchor without independently sanitizing or canonicalizing them.
- A source-relative path is not interchangeable with an absolute path.
- An anchor can encode source values or line-dependent information.
- Hashing a value does not constitute redaction. Existing credential-redaction boundaries remain mandatory.
- The report hash includes serialized findings. Included content must continue to respect privacy and redaction requirements.
- Fingerprint stability is defined by the implemented input contract, not by a general promise that logically similar scans always hash identically.

## 6. Compatibility change policy

The current SHA-256 strings are **unversioned in their stored representation**.

The C19 documentation formalizes the legacy behavior without introducing a new fingerprint version.

Changing an algorithm requires an explicit compatibility review covering prior reports, stored suppressions, historical baselines, platform retention, and consumers of report identity.

Do not silently recompute legacy identities under a changed algorithm.

Any later versioned scheme must define coexistence and migration before deployment.

## 7. Required regression coverage

Maintain frozen reference values for deterministic, semantic, and report fingerprints, along with properties demonstrating expected stable and changed inputs.

For the report contract, retain the C18 fixed-fixture digest:

`8050ab09ad677b729bc5287e99347713afc10bf0d87957066b1494442f034e26`

This value must remain unchanged throughout C19.

The current implementation is the executable source of truth; test fixtures and this document guard against unreviewed future changes.
