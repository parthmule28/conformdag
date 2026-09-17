# P1 Remediation Design

## Goal

Make the P1 foundation safe for P2 by fixing every confirmed P1 correctness
blocker found in the readiness audit, without expanding P2 UI scope or adding
new product capabilities.

## Scope

This remediation covers four dependent workstreams:

1. Governance and scan integrity: validate evaluator kinds and gate references
   before scans; treat incomplete scans as failures; apply platform suppressions;
   enforce complete, successful, same-repository baseline eligibility; ensure
   `always-block` considers the listed policy regardless of finding blocking
   metadata.
2. Platform lifecycle: persist exhausted retry failures, define timeout and
   cancellation state transitions, preserve the newest retention artifact,
   make the Compose workspace accessible to API and worker, and serialize
   migration startup.
3. Policy persistence: make dashboard policy edits round-trip all required
   policy metadata, validate writes before publishing, and prevent concurrent
   pack mutations from losing updates or sharing temporary filenames.
4. Analysis and fix safety: require complete, parseable verification before
   applying patches; reject all conflicting edit spans; quote generated Python
   values; correct TaskFlow DAG identity/default resolution; and align declared
   fixability with actual TaskFlow codemods.

## Out Of Scope

- P2 visual/dashboard expansion, trends, and filtering UX.
- Semantic/BYOK platform configuration.
- OpenAPI documentation polish and endpoint-model cleanup.
- Unicode branch-name hardening, pagination tie-breakers, and other deferred
  nonblocking audit observations.

## Architecture

### Validation Boundaries

`load_policy_pack()` remains the authoritative pack parser. It must reject
unknown deterministic or hybrid evaluator references and invalid quality gates
before callers can construct a scan. CLI, platform startup, workspace loading,
and pack mutation all use this same validation boundary.

Scan completion is part of durable scan state: a scan with parser or discovery
errors cannot be marked `succeeded`, cannot pass gates, and cannot be selected
as a baseline. Baseline consumers validate repository ownership, successful
complete status, and use retained normalized fingerprints only after those
checks pass.

### Platform State Machine

Worker finalization is conditional on the current persisted scan state. A
cancelled scan remains cancelled; timeout or execution failure either enters a
retryable pending state when attempts remain, or is committed as failed when
they do not. Process control must terminate a running child when cancellation
is requested, so a later runner result cannot overwrite cancellation.

Retention always protects the newest scan artifact and validates configuration
as at least one retained artifact. Migration execution is a single deployment
startup responsibility, not a runner-side side effect. Compose mounts the
configured workspace consistently wherever workspace loading occurs.

### Pack Mutation Contract

The typed dashboard request preserves all immutable policy provenance,
ownership, and enforcement fields while applying editable title, status,
invariant, and check configuration. The complete reconstructed `Policy` is
validated before an atomic write. Pack-level synchronization serializes
read-modify-write operations; each atomic write gets a unique same-directory
temporary filename.

### Safe Fix Contract

A generated patch is eligible for `--apply` only after rescan is complete and
the modified file parses. All duplicate or overlapping spans, including
zero-width insertions at a shared offset, become residuals rather than source
writes. Generated Python string literals use Python-safe quoting. A finding is
autofixable only when its codemod supports its AST form; unsupported TaskFlow
forms remain residual/manual until their codemod exists.

TaskFlow context is identified by the concrete DAG record, not only an alias,
so reused aliases cannot share defaults. Unresolved decorator expressions do
not silently become a passing default.

## Error Handling

- Invalid pack, gate, or evaluator data fails early with a user-facing
  validation error and no scan report claiming success.
- Cancellation has precedence over runner completion.
- Retry exhaustion commits a terminal failure.
- Unsafe edits produce residual failures with a reason and leave sources
  untouched.
- Dashboard policy writes reject incomplete or invalid reconstructed policies
  before touching the persisted pack.

## Test Strategy

Every remediation behavior begins with a focused failing regression. Add
platform tests for state transitions, baseline eligibility, suppressions,
retention, concurrent pack writes, and Compose workspace loading. Add scan and
gate tests for invalid pack data and incomplete reports. Add analysis/fix tests
for reused TaskFlow aliases, unresolved arguments, malformed generated values,
and zero-width insertion conflicts. Run `mise run check`, `mise run
test:coverage`, `mise run schema --check`, and the Docker runtime suite after
the complete remediation.

## Acceptance Criteria

1. Invalid evaluator kinds and invalid gate references fail pack validation and
   cannot yield a passing scan.
2. No incomplete, cancelled, queued, failed, or cross-repository scan can act
   as a successful baseline.
3. Worker retry, timeout, cancellation, retention, Compose workspace, and
   migration behavior are durable under runtime tests.
4. Dashboard policy edits preserve valid policy metadata and concurrent writes
   do not corrupt or lose pack changes.
5. `--apply` never writes a file whose verification rescan is incomplete or
   unparsable, and never applies conflicting insertion spans.
6. TaskFlow effective configuration is correct for nested DAGs, reused aliases,
   unresolved expressions, and supported autofix forms.
7. `mise run check`, `mise run test:coverage` at least 90%, schema check, and
   Docker runtime tests all pass.
