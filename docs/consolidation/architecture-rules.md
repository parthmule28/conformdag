# Consolidation Architecture Rules

These rules are the standing contract for C01–C64. A later slice may refine a rule only by recording a reviewed decision in an ADR and updating the affected prompts.

## Product invariants

1. **One scan engine.** `src/conformdag/scan.py:scan_repository()` remains the canonical core evaluation primitive until an application workflow wraps it with parity evidence. CLI, platform, agent, future MCP, and future schedulers must not implement separate evaluation paths.
2. **Verify-by-rescan fixing.** The fix engine remains `scan → generate patch → apply in isolation → rescan → present only verified patches`. `--apply` is the only write path.
3. **Human merge authority.** Agent automation may triage, verify, branch, and open a PR; it may not merge or approve its own changes.
4. **Offline default.** Core scans do not execute repository Python, access the network, or call semantic providers unless an explicit invocation enables the relevant boundary.
5. **Canonical report.** `ScanReport` is the public serialized product result. Terminal, JSON, SARIF, HTML, platform persistence, future MCP, and report diff are projections or consumers of it.
6. **Stable identity.** Finding and report fingerprints are deterministic, documented, and reviewed before changes to their inputs or versions.

## Layer ownership

| Layer | Owns | Must not own |
| --- | --- | --- |
| Core models | Typed domain values and validation | FastAPI, Typer, SQLAlchemy, Docker, GitHub, provider clients |
| Analysis | Discovery, parsing, cache, family-specific source models | Policy mutation, HTTP, persistence, CLI rendering |
| Checks | Deterministic evaluator contracts, check metadata, check-family implementations | Platform operations, semantic transport, CLI behavior |
| Application | Complete scan/fix/policy workflows and outcome classification | HTTP binding, Typer decorators, SQL queries, transport-specific auth |
| Reporting | Normalization, suppression application, SARIF/HTML projections | Exit codes, persistence transactions, adapter orchestration |
| Policy | Pack loading, provenance, validation, editing semantics | FastAPI route registration, workspace process lifecycle |
| Platform services | Repository/scan/baseline/suppression operations and persistence coordination | AST evaluation, Docker command construction, HTTP serialization |
| CLI | Argument parsing, dependency composition, rendering, exit mapping | Governance logic and a second scan workflow |
| FastAPI routes | Request/response binding, auth dependency, service invocation, status mapping | SQL business logic and policy evaluation |
| Worker | Claim, subprocess lifecycle, heartbeat, timeout, cancellation, retry, retention trigger | Finding semantics and gate calculation |
| Runner | Claimed-scan application invocation, canonical ingestion, fenced completion | A second scan orchestration or HTTP behavior |
| Infrastructure adapters | Filesystem, SQL, Docker, Git, HTTP/provider integration | Cross-adapter governance policy |

## Dependency direction

Allowed direction is inward/downward:

```text
transport adapters → application services → core domain/analysis/checks/reporting
platform persistence/infrastructure → application-facing ports
```

Core and application packages must not import Typer, FastAPI, SQLAlchemy, MCP, or platform adapters. Analysis and checks must not import platform. A small architecture verifier becomes a required gate after C41.

## Trust boundaries

Keep these boundaries distinct even when they share process APIs:

- Ruff runs with repository-controlled configuration isolated from ConformDAG policy decisions.
- Docker runtime execution is a host trust boundary with immutable image identity, no network, read-only mounts, bounded resources, and non-root execution.
- Git/GitHub operations have dirty-tree and verified-file rules; the agent cannot merge.
- Semantic providers receive bounded, redacted, explicitly untrusted evidence and return validated schemas; raw prompts and provider payloads are not persisted.
- Policy-pack Git pulls validate source, name, timeout, and last-known-good state.
- SQL persistence owns migrations and conditional state transitions; SQLite tests do not replace Postgres concurrency evidence.

## Compatibility rules

- Preserve `conformdag.cli:app` unless a packaged-wheel smoke test proves the replacement entry point.
- Preserve old import paths through explicit `__init__.py` facades during module-to-package moves.
- Preserve report JSON and policy schema shapes unless the prompt names additive fields, deprecation timing, schema regeneration, and consumer migration.
- Legacy policy IDs route through generated compatibility mappings; they are not a second registry.
- Every compatibility surface records why it exists, the version that introduced it, and the removal condition.

## Persistence and lifecycle rules

- Platform schema changes use Alembic migrations only; never call `Base.metadata.create_all()`.
- Scan status mutations use the approved transition primitives and typed status/trigger values.
- Transition primitives may own a transaction only when atomic winner/fencing semantics require it; multi-step services prefer caller-owned transactions.
- A cancelled or stale attempt cannot be overwritten by a late runner result.
- Retention may prune large report artifacts only when finding fingerprints and baseline behavior remain correct.

## Security and privacy rules

- Credential redaction has one canonical implementation; semantic cache, evidence, agent verification, logs, and exports use it.
- Repository paths are normalized and contained; symlink semantics remain explicit rather than replaced by an unsafe generic helper.
- Never log API keys, admin tokens, DSN credentials, raw source by default, semantic prompts, or raw provider payloads.
- Any new write capability is explicit, separately authorized, and never silently enabled by a read-only adapter.

## Review rules

Every PR identifies the new owner, removes or derives duplicate sources of truth, names public-contract effects, proves behavior at the lowest useful layer, runs the relevant gate tier, and records intentional limitations. No prompt authorizes `git reset --hard`, broad checkout/revert, recursive deletion, force-push, or deletion of unrecognized user changes.
