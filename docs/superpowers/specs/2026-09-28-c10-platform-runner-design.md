# C10 — Platform Runner Delegation Design

## Goal

Make the platform runner an adapter around `application.execute_scan()` rather than a second implementation of complete scan orchestration, while preserving the persisted report, scan lifecycle, and platform behavior established by C06–C09.

## Scope and ownership

The application scan workflow owns the complete scan execution result: core scan invocation, operational suppression application, final normalization, complete-only gate evaluation, and the canonical `ScanExecutionResult`. The platform runner owns subprocess-facing orchestration: loading the claimed scan/repository, resolving platform overrides, converting SQL-backed baseline and suppression records to application values, invoking the workflow, ingesting its canonical report, and fencing terminal state updates by status and claim attempt. The worker continues to own claims, heartbeat, timeout, cancellation process control, retries, and retention.

The application receives only application/core types. SQLAlchemy rows and sessions remain in the platform adapter. The runner does not evaluate gates, apply suppressions, normalize reports, or call `scan_repository()` directly after delegation.

## Application boundary

The runner will call the existing `execute_scan(options, configuration, *, baseline, operational_suppressions, parse_cache)` API, reusing `ScanOptions`, `EffectiveScanConfiguration`, `BaselineInput`, `Suppression`, and `ScanExecutionResult`. The platform's persisted policy-pack and Airflow-profile values continue to enter through `ScanOverrides` and `resolve_effective_configuration()`. Platform scans continue not to enable semantic or runtime execution implicitly; this change does not add a runtime executor or provider wiring.

For baselines, the adapter first applies `eligible_baseline()`. If the eligible scan retains `report_json`, it validates that artifact as a `ScanReport` and supplies `BaselineInput(report=...)`. If retention has pruned the artifact, it loads the baseline's finding fingerprints and supplies `BaselineInput(fingerprints=...)`. Missing or ineligible baselines continue to mean no baseline. The application remains responsible for complete-baseline validation and gate evaluation.

For operational suppressions, the adapter selects only rows whose `expires_at` is later than the current UTC time and converts each row's identity, reason, owner, and timestamps to the canonical `Suppression` model. The application performs suppression matching and preserves existing repository-local suppression provenance. Expired rows are never supplied.

This intentionally corrects one existing report behavior. Today, the runner's private suppression helper sets only `Finding.suppressed=True` for a platform-only suppression. The canonical application helper also attaches that operational `Suppression` as `Finding.suppression`; `normalize_report()` includes the serialized finding in the report fingerprint payload. After delegation, a newly operationally-suppressed finding therefore gains its canonical suppression provenance and the enclosing `ScanReport.result_fingerprint` changes. Its finding-level `fingerprint` remains unchanged. This is the sole expected canonical report difference for an operational-only suppression; no runner shim may strip provenance to preserve the old report digest. When repository-local provenance already exists, the application preserves it and the matching operational suppression does not replace it.

## Outcomes and persistence

The runner persists exactly the application result's normalized report, including its gate result when complete. An incomplete report is ingested for diagnosis and transitions to `FAILED`, using the existing concise fatal-issue error summary. A complete report is ingested and may transition to `SUCCEEDED`; a failing policy gate is represented in the report and does not itself make the scan execution incomplete or change the existing platform scan status contract.

Application/configuration failures continue to produce a failed scan through the existing persistent-failure handling. Cancellation and stale-attempt fencing remain authoritative: before report ingestion the runner checks cancellation using a fresh read, and terminal transitions remain conditional on `RUNNING` plus the exact claimed attempt. No late result may overwrite cancellation or a reclaimed attempt. The runner's subprocess exit semantics remain unchanged.

## Compatibility and constraints

- Preserve report JSON shape, finding-level fingerprints/identities, finding rows, gate outcomes, baseline eligibility, suppression expiry behavior, and scan status/error/exit semantics. The one intentional content/digest correction is the operational suppression provenance and consequent report `result_fingerprint` described above; no schema fields are added.
- Preserve project configuration plus platform policy-pack/profile override precedence through the existing resolver.
- Keep all SQLAlchemy access in `platform/`; do not add SQLAlchemy dependencies to `application/`.
- Keep worker lifecycle, retention, API contracts, migrations, ORM mappings, and C11 outcome-classification scope unchanged.
- Do not delegate suppression selection or baseline record loading to a new service; those are platform adapters for this slice.

## Verification and acceptance

Before changing runner orchestration, add a golden comparison between application execution and the runner's canonical pre-persistence report. The comparator excludes only `run.timestamp` by default. `ScanReport` has no platform scan ID; there is no general platform-metadata exclusion. Any additional excluded field must be named individually and justified before implementation proceeds. Characterize ordinary deterministic execution, report baseline, fingerprint-only baseline after report pruning, repository-local suppression, operational-only suppression, matching local plus operational suppression, complete/incomplete reports, and passing/failing gate outcomes, as well as cancellation/stale-attempt behavior. For operational-only suppression, assert exactly the documented `Finding.suppression` and `ScanReport.result_fingerprint` difference; finding-level identity/fingerprint and every other canonical field must match. Keep or adapt existing tests so they exercise real runner-to-application wiring rather than a mocked alternate pipeline.

Acceptance requires focused application/platform runner/worker/gate/suppression/retention tests, `mise run check`, `mise run test:coverage`, `mise run schema --check`, whitespace validation, and PostgreSQL concurrency evidence when a configured Postgres gate is available. An independent review must trace each former runner responsibility to exactly one new owner and verify that no second orchestration path remains.
