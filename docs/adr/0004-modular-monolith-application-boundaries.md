# ADR 0004: Modular-monolith application boundaries

## Status

Proposed (2026-09-20)

## Context

ConformDAG combines an offline Python scanner and fix engine with a self-hosted
FastAPI platform, a subprocess worker, policy-pack tooling, semantic and runtime
adapters, and an agent that opens pull requests. The current repository already
has the right product trust boundaries, but responsibilities are distributed
across large CLI, evaluator, analysis, model, reporting, policy, and platform
modules. The C01–C64 program must improve ownership without creating a second
scan engine, breaking public contracts, or turning a cohesive product into a
network of prematurely separated services.

ADR 0001 establishes one orchestration path and thin adapters. ADR 0002 and ADR
0003 establish the self-hosted platform, stable report/API contracts, optional
semantic behavior, and the rule that the agent never merges. This decision
records the module and application boundaries that the consolidation slices use
to apply those principles consistently.

## Decision

### 1. Use a modular monolith

ConformDAG remains one repository with explicit Python package boundaries and
small, testable interfaces. The offline package and the platform image may have
different deployment processes, but their shared domain, application, policy,
reporting, and check contracts remain in one codebase. We do not introduce
internal network calls or split services merely to move files.

### 2. Assign one owner to each responsibility

The target ownership model is:

| Boundary | Owns | Must not own |
| --- | --- | --- |
| Core models | Typed domain values, validation, and serialized contracts | FastAPI, Typer, SQLAlchemy, Docker, GitHub, or provider clients |
| Analysis | Repository discovery, parsing, cache, and family-specific source models | Policy mutation, persistence, HTTP, or CLI rendering |
| Checks | Deterministic evaluator contracts, the authoritative check catalogue, and check-family implementations | Platform operations, semantic transport, or CLI behavior |
| Application | Complete scan/fix/policy workflows, configuration composition, and outcome classification | HTTP binding, Typer decorators, SQL queries, or transport-specific auth |
| Reporting | Canonical normalization, suppression application, and SARIF/HTML projections | Exit codes, persistence transactions, or adapter orchestration |
| Policy | Pack loading, provenance, validation, hashing, and canonical editing semantics | FastAPI registration or workspace process lifecycle |
| Platform services/persistence | Repository/scan/baseline/suppression operations, durable state, and transactions | AST evaluation, Docker command construction, or HTTP serialization |
| Transports and infrastructure adapters | CLI/HTTP binding and filesystem, SQL, Docker, Git, or provider side effects | Governance policy and a second application workflow |

The worker owns process lifecycle and the runner owns claimed application
execution, canonical report ingestion, and fenced completion. They do not
become alternative application layers.

### 3. Keep one scan and report contract

`scan_repository()` remains the canonical core evaluation primitive. A single
application workflow may compose configuration, core scanning, optional runtime
or semantic phases, suppression, normalization, and gates around it. CLI,
platform, agent, and future adapters delegate to that workflow rather than
reimplementing evaluation.

`ScanReport` is the canonical typed result. JSON is its public serialized form;
terminal, SARIF, HTML, platform persistence, future MCP, and report-diff
surfaces are projections or consumers of that result. Finding and report
fingerprints remain deterministic and require a compatibility decision before
their inputs change.

### 4. Keep dependency direction inward

Transport adapters call application services, which call core domain,
analysis, checks, policy, and reporting code. Persistence and infrastructure
adapters are composed through application-facing ports or service boundaries.
Core and application packages must not import FastAPI, Typer, SQLAlchemy, MCP,
or platform adapters; analysis and checks must not import platform code.

### 5. Preserve explicit trust and lifecycle boundaries

Offline deterministic scanning remains the default. Runtime Docker execution,
semantic providers, Ruff, Git/GitHub, filesystem writes, and database
transitions remain distinct boundaries with their existing validation,
redaction, isolation, fencing, and human-merge controls. Fixing continues to
use isolated apply followed by rescan and verification, and `--apply` remains
the fix engine's only source-code mutation path.

Platform schema changes use Alembic migrations only. Scan status changes use
typed values and approved conditional transition primitives; a cancelled or
stale attempt cannot be overwritten by a late runner result.

### 6. Prefer explicit compatibility over silent breaks

Package moves retain import facades, the `conformdag.cli:app` entry point,
report JSON, policy schemas, and `/api/v1` wire contracts unless a slice names
an additive migration, deprecation condition, and consumer evidence. Legacy
policy IDs derive from the modern check catalogue; they are not a second
registry.

### 7. Extend by family and catalogue, not speculation

Deterministic checks are registered by check kind in one authoritative
catalogue. Airflow analysis remains family-specific. A future analysis family
such as dbt may add its own models and adapters after a real requirement exists;
it must not force an abstract multi-family framework into the current Airflow
path. Future MCP, scheduling, webhook, and report-diff consumers call the
application/report contracts rather than adding parallel governance logic.

## Consequences

Positive consequences:

- Ownership and dependency direction can be reviewed mechanically and tested
  without requiring a microservice deployment.
- CLI, platform, and future transports can share scan, policy, report, and
  outcome behavior.
- Package movement can preserve public imports and wire contracts through
  explicit facades.
- Trust-boundary controls remain visible instead of being hidden in a generic
  adapter layer.

Costs and trade-offs:

- The repository must maintain clear package boundaries and compatibility
  facades during the migration.
- Some integration tests remain necessary because SQLite, unit mocks, and
  in-process calls cannot prove Postgres, Docker, browser, or package behavior.
- A modular monolith does not remove the need for explicit process isolation in
  the platform worker and runtime executor.

## Migration guardrails

Every consolidation PR must name the current owner and resulting owner, remove
or derive duplicate sources of truth, preserve the relevant public contract,
test behavior at the lowest useful layer, and record intentional limitations in
`docs/consolidation/progress.md`. A proposed split that cannot satisfy those
guardrails is recorded as `split` or `blocked` rather than silently broadened.

## Rejected alternatives

- **Immediate microservices:** adds deployment, network, and contract overhead
  before the ownership boundaries are proven.
- **A generic plugin/analyzer framework now:** creates speculative abstractions
  before a second analysis family exists.
- **A transport-owned scan implementation:** duplicates evaluation and makes
  report, fixing, and gate semantics drift.
