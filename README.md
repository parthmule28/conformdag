# ConformDAG

Turn Apache Airflow engineering standards into enforceable, explainable checks.

ConformDAG is a local-first CLI that scans Airflow repositories against versioned organizational policies. It combines non-executing deterministic analysis with optional BYOK semantic review and produces cited terminal, JSON, SARIF, and static HTML reports.

## Status

ConformDAG is in active development. The first public release is planned as a beta focused on ten Airflow policies, reproducible benchmarks, and transparent limitations.

## Development

The project uses [mise](https://mise.jdx.dev/) as its tool and task entry point. After the toolchain is configured, run:

```bash
mise run setup
mise run check
```

See [docs/project-brief.md](docs/project-brief.md) for the product definition and [docs/roadmap.md](docs/roadmap.md) for implementation milestones.

## License

Apache-2.0. See [LICENSE](LICENSE).
