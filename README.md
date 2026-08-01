# ConformDAG

Turn Apache Airflow engineering standards into enforceable, explainable checks.

ConformDAG is a local-first CLI that scans Airflow repositories against versioned
organizational policies. Source analysis is offline and non-executing by default.
Dockerized Airflow import validation and BYOK semantic review are explicit opt-ins.
Every engine contributes to one versioned JSON report that can also be rendered as
terminal output, SARIF, or self-contained HTML.

## Beta release candidate

The `0.1.0b1` release candidate includes:

- six deterministic Airflow policy evaluators with versioned policy contracts;
- policy provenance validation and human/machine-readable policy inspection;
- expiring suppressions with stale and unmatched-suppression diagnostics;
- constrained Docker runtime profiles for Airflow 2.11.2 and 3.3.0;
- four opt-in semantic policies through OpenAI-compatible endpoints, with local
  redaction, strict response validation, bounded concurrency, and normalized caching;
- canonical JSON, terminal, SARIF, and static HTML reports; and
- a 240-case offline deterministic benchmark with per-policy release gates.

The package has not been published yet. Provider-backed semantic accuracy baselines
remain a release-evidence item because the public benchmark currently contains no
redistributable, labelled semantic corpus. This limitation does not weaken the offline
deterministic gate and is tracked explicitly in the release checklist.

## Development

The project uses [mise](https://mise.jdx.dev/) as its tool and task entry point:

```bash
mise install
mise run setup
mise run check
```

Run the CLI from a checkout through the locked uv environment:

```bash
mise exec -- uv run conformdag validate-policies --path policies/pack.yaml
mise exec -- uv run conformdag list-policies --path policies/pack.yaml
mise exec -- uv run conformdag policy review AIR-DET-001 --path policies/pack.yaml
mise exec -- uv run conformdag scan --path . --policy-pack policies/pack.yaml
```

See the [user guide](docs/user-guide.md) for setup and operational usage, the
[architecture](docs/architecture.md) for trust boundaries and data flow, and the
[release checklist](docs/release.md) for the remaining publication gates.

## License

Apache-2.0. See [LICENSE](LICENSE).
