# P1 — Foundation (backend, TDD)

Status: approved for implementation planning
Date: 2026-09-05

## Context

ConformDAG has a working enforcement loop (scan → triage → codemod → verify-by-rescan),
a platform (FastAPI + worker + Postgres), a dashboard, and 11 check kinds. A full audit
in `~/Documents/conformdag-research/conformdag-review-and-research.md` found 14 known
bugs (B1–B14), dead code, missing DX commands, and one strategic gap: blocking is a
blunt hammer (any FAIL blocks). The research doc's north star — SonarQube-style quality
gates — is the answer to that gap, plus the "compose, don't compete" Ruff strategy.

P1 makes the backend correct and complete before any UI work.

## Goals

- Fix B1–B14 (every known bug) — TDD, red test first
- Ship the four DX commands: `policy hash`, `policy new`, `doctor`, `init`
- Build the quality-gate engine (5 rule types) + baseline scans
- Add the `ruff-air` check kind
- Hold the gates: `mise run check` green, coverage ≥90%

## Non-goals

- No UI work (that's P2)
- No new check kinds beyond `ruff-air` (wave 2 is P7)
- No webhooks, scheduling, report diff (P6)
- No pack content beyond the org pack updates needed by B3/B4

## Design

### A. Bug fixes

**A1 — Pack-service wiring (B1).** `create_app` resolves the workspace file's
`policy_packs` entries (and `repositories[].policy_pack` paths) and registers them
into `PackService` at startup; `/workspace/load` re-registers. The Policies page
becomes alive without operator ceremony.

**A2 — Atomic pack writes (B2).** `_write_pack` writes `<pack>.tmp` in the same
directory then `os.replace()` onto the target. Failed validation discards the tmp.

**A3 — Org pack completion (B3).** Add `start-date-freshness`, `catchup-policy`,
`module-scope-variables`, `dynamic-dag-factory` to `policies/pack.yaml` with
auto-hashed provenance.

**A4 — Fixability matrix (B4, B8).** Register the new kinds in
`AUTOFIX_KINDS`/`MANUAL_KINDS`; `catchup-policy` gets the `set-kwarg` codemod.

**A5 — HTTP timeout (B5).** httpx client in `agent/pr.py` gets a 120s timeout,
matching the verifier.

**A6 — Worker graceful shutdown (B6).** SIGTERM handler in the worker: stop
claiming, let the in-flight subprocess finish (kill after grace period), write
final status, exit. Active scan ID tracked in the worker process.

**A7 — Structured logging (B7).** stdlib logging with a JSON formatter across
`platform/`: request log middleware (method, path, status, duration, request ID),
worker lifecycle events, runner phases. No new dependency.

**A8 — Pagination + retention (F5, F17).** `limit`/`offset` on
`/scans/{id}/findings` and `/repos/{id}/scans`; call `prune_scan_artifact` in the
worker after each scan.

**A9 — CORS (B14).** CORS middleware: same-origin SPA + configurable origins for
external clients.

**A10 — Dead code cleanup (B9/B10).** Remove unused `PolicySummary`,
`PackSummary`, `compute_content_hash` from `platform/packs.py`.

**A11 — TaskFlow DAG matching (B11).** TaskFlow tasks declared inside
`with DAG(...)` currently get `dag_name=None`; match them to the enclosing DAG
so `default_args` resolution works correctly.

**A12 — Iterated-line-shift edge (B12).** Fix the `_patch_candidates` edge in
`fixing/engine.py` where iterating while shifting lines corrupts candidate
locations.

**A13 — Branch name truncation (B13).** Truncate branch names derived from
applied-file paths in `agent/pipeline.py` to respect the 255-char git limit.

### B. DX commands

- `conformdag policy hash <document>` — prints SHA-256 of document text
- `conformdag policy new <id> --kind <check-kind>` — scaffolds a valid policy
  block with computed provenance; fails loudly on unknown kind
- `conformdag doctor` — checks: pack provenance, pack parseability, registry
  vs. pack kinds, config presence, Docker availability (runtime), platform DSN
  reachability
- `conformdag init` — additionally scaffolds a commented `conformdag-workspace.yaml`

### C. Quality gates

Gates live **in the policy pack** (top-level `quality_gates:`), versioned with
provenance like everything else. Baselines are per-repo platform state.

Rule types (discriminated union):

- `no-new-findings` — no failing findings absent from the baseline
- `max-severity` — nothing at or above the given severity
- `max-findings` — total failing findings below a count
- `always-block` — listed policy IDs always block
- `failure-rate` — failing/total findings below a percentage

Evaluation is a pure function in `gates.py`:
`evaluate_gate(gate, report, baseline_report) -> GateResult`.
Shared by CLI (exit code), platform (persisted on scan row), and the Action
(`fail-on-blocking` = "fail if the gate fails").

Packs without gates keep today's behavior (any FAIL blocks).

Baselines: `baseline set <scan-id>` (CLI + API). `no-new-findings` compares
structural fingerprints (path+anchor based — stable across runs). Platform
stores `baseline_scan_id` per repo; findings are marked `new`/`existing`.

Schema: `QualityGate`, `GateRule` (union by `type`), `GateResult` in `models.py`;
`validate-policies` validates gate syntax; report gains optional `gate_result`
(additive, minor version bump).

### D. Ruff AIR adapter

New check kind `ruff-air` with pack config:

```yaml
configuration:
  kind: ruff-air
  rules: [AIR001, AIR002, AIR301, AIR302, AIR311, AIR312]
```

One subprocess per scan: `ruff check --select <rules> --output-format json`.
Violations map to findings: location (file/line from ruff JSON), evidence
(ruff message), fingerprint (policy + rule + file + line). Missing ruff binary
→ structured `RUFF_UNAVAILABLE` issue, no crash. Findings carry a MANUAL fix
payload hinting `ruff check --select AIR --fix`; ruff never writes to sources
(verify-by-rescan model preserved). Ruff is already a dev dependency, so the
integration test runs real ruff against a fixture DAG.

## Data flow

```
scan_repository (unchanged pipeline)
  └─ evaluators: ... + RuffAirEvaluator (one ruff subprocess)
report
  ├─ gate evaluation: evaluate_gate(gate, report, baseline) → GateResult
  │    ├─ CLI: exit code
  │    ├─ platform: scan row + API
  │    └─ Action: exit code
  └─ findings (pagination in API)
```

## Error handling

- Gate evaluation never crashes a scan — malformed gates fail at pack
  validation time, not scan time
- Ruff unavailability degrades to an issue, not an exception
- Worker shutdown is idempotent; a killed subprocess is re-claimable by the
  next worker (the scans table is the source of truth)

## Testing (TDD)

Every fix gets its red test first. Notable tests:

- Atomic write survives a crash mid-write
- SIGTERM mid-scan lets the in-flight scan finish
- Gate evaluator: one test per rule type + combinations + baseline interaction
- Pack validation rejects malformed gates
- CLI exit codes are gate-driven
- Ruff adapter: mocked ruff JSON maps to findings; missing binary → issue;
  one real-ruff integration test
- API: pagination bounds, CORS headers present

Roughly 45 new tests total. Coverage gate (≥90%) enforces the discipline.

## Acceptance criteria

- All of B1–B14 closed with regression tests
- The four DX commands work against the real org pack
- A repo with a gate `no-new-findings` + baseline passes while a brand-new
  finding fails it — demonstrated end to end
- `ruff-air` produces findings/suppressible findings against a real AIR
  violation
- `mise run check` green; `mise run test:coverage` ≥90%
