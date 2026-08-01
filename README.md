# ConformDAG

Turn Apache Airflow engineering standards into enforceable, explainable checks.

ConformDAG is a local-first CLI that scans Airflow repositories against versioned organizational policies. It combines non-executing deterministic analysis with optional BYOK semantic review and produces cited terminal, JSON, SARIF, and static HTML reports.

## Status

ConformDAG is in active beta development. The current implementation includes:

- versioned YAML policy packs with provenance validation;
- offline, non-executing AST analysis for deterministic policy checks;
- JSON, terminal, SARIF, and self-contained HTML reports;
- suppressions with expiry and stale-suppression diagnostics;
- optional constrained Docker runtime inspection;
- optional BYOK semantic review through OpenAI-compatible endpoints; and
- privacy-preserving context redaction, normalized caching, and benchmark-manifest validation.

The benchmark corpus, offline execution, deterministic quality gates, semantic baseline
contracts, cache, and report generation are implemented. Runtime-profile release work,
security automation, CI, and publication gates remain before the public beta.

## Development

The project uses [mise](https://mise.jdx.dev/) as its tool and task entry point. After the toolchain is configured, run:

```bash
mise run setup
mise run check
```

The main commands are:

```bash
mise exec -- conformdag validate-policies --path policies/pack.yaml
mise exec -- conformdag list-policies --path policies/pack.yaml
mise exec -- conformdag explain AIR-DET-001 --path policies/pack.yaml
mise exec -- conformdag scan --path . --policy-pack policies/pack.yaml
```

See [docs/user-guide.md](docs/user-guide.md) for installation and operational usage,
[docs/architecture.md](docs/architecture.md) for implementation boundaries, and
[docs/roadmap.md](docs/roadmap.md) for planned milestones.

## License

Apache-2.0. See [LICENSE](LICENSE).
