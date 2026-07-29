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

The public beta still requires the full benchmark corpus, runtime profile release work, and release automation before publication.

## Development

The project uses [mise](https://mise.jdx.dev/) as its tool and task entry point. After the toolchain is configured, run:

```bash
mise run setup
mise run check
```

The main commands are:

```bash
uv run conformdag validate-policies --path policies/pack.yaml
uv run conformdag list-policies --path policies/pack.yaml
uv run conformdag explain AIR-DET-001 --path policies/pack.yaml
uv run conformdag scan --path . --policy-pack policies/pack.yaml
```

See [docs/architecture.md](docs/architecture.md) for implementation boundaries and [docs/roadmap.md](docs/roadmap.md) for planned milestones.

## License

Apache-2.0. See [LICENSE](LICENSE).
