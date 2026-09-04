## Purpose

Amends the `org-governance-1-0` stable-contracts requirement per ADR 0003: the
dashboard HTTP API becomes a stable versioned compatibility surface. The
non-goals amendments (single-admin auth scope, auto-PR relocation) live in the
`agent-harness` change delta to keep each requirement modified in exactly one
change.

## MODIFIED Requirements

### Requirement: Stable 1.0.0 contracts

The 1.0.0 release SHALL treat policy pack YAML schema, canonical scan report
JSON, public CLI commands `scan`, `serve`, `fix`, and `validate-policies`, and
the platform dashboard HTTP API as compatibility surfaces. The dashboard HTTP
API SHALL be stable, versioned under `/api/v1`, and documented via OpenAPI;
it SHALL remain compatible within a major platform version (supersedes the
earlier allowance that the dashboard API may be internal and unstable).

#### Scenario: Report JSON remains canonical

- **WHEN** any 1.0.0 adapter renders findings
- **THEN** it is a projection of the versioned scan report JSON contract

#### Scenario: Dashboard API is a compatibility surface

- **WHEN** a platform release within the same major version changes `/api/v1`
- **THEN** existing documented API consumers keep working without modification
