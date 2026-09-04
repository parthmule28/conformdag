# ADR 0001: Architecture principles

## Status

Accepted (2026-08-29)

Principle 5 is **superseded in part** by [ADR 0002](0002-v1-product-thesis.md):
ConformDAG 1.0.0 includes a self-hosted dashboard. Plugin registry and
multi-pack composition remain deferred.

## Context

ConformDAG is a local policy linter for Airflow DAG repositories. The beta CLI is
shipped; new work must keep the codebase understandable as policies, packs, and
integrations grow.

## Decision

1. **Policy-as-data, checks-as-code** — Organizational rules live in versioned YAML
   packs. Python implements reusable check kinds (`effective-timeout`, `retry-bounds`,
   and so on), not one-off org rules.
2. **One orchestration path** — `scan.py` owns the scan pipeline. Optional runtime and
   semantic phases attach at explicit boundaries; do not duplicate orchestration in the
   CLI.
3. **Adapters stay thin** — Filesystem, HTTP, Docker, and terminal rendering belong in
   adapter modules. The CLI wires configuration and I/O only.
4. **Stable contracts** — `models.py`, JSON schemas, and report fingerprints are
   compatibility surfaces. Breaking changes require version bumps and migration notes.
5. **YAGNI for platform features** — No plugin registry, dashboard, or multi-pack
   composition until real usage justifies them.
6. **Two pack profiles for the beta** — `policies/pack.yaml` demonstrates
   organizational contracts; the bundled `community` pack is the default quickstart.

## Consequences

- New deterministic policies should prefer `enforcement.deterministic_checks` routing
  over hard-coded policy IDs in evaluators.
- Foreign-repository scans resolve `--policy-pack` from the invoker's working directory,
  built-in aliases such as `community`, or the pack tree for provenance.
- Documentation should lead with the community pack; the organizational pack remains
  the reference for platform teams.
