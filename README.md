# ConformDAG

Turn Apache Airflow engineering standards into enforceable, explainable checks.

ConformDAG is a local-first CLI that scans Airflow repositories against versioned
organizational policies. Source analysis is offline and non-executing by default.
Dockerized Airflow import validation and BYOK semantic review are explicit opt-ins.
Every engine contributes to one versioned JSON report that can also be rendered as
terminal output, SARIF, or self-contained HTML.

## Public beta

ConformDAG `0.1.0b1` includes:

- six deterministic Airflow policy evaluators with versioned policy contracts;
- policy provenance validation and human/machine-readable policy inspection;
- expiring suppressions with stale and unmatched-suppression diagnostics;
- constrained Docker runtime profiles for Airflow 2.11.2 and 3.3.0;
- four opt-in semantic policies through OpenAI-compatible endpoints, with local
  redaction, strict response validation, bounded concurrency, and normalized caching;
- canonical JSON, terminal, SARIF, and static HTML reports; and
- a 240-case offline deterministic benchmark with per-policy release gates.

Provider-backed semantic accuracy baselines are not claimed because the public benchmark
does not yet contain a redistributable, labelled semantic corpus. The recorded provider
smoke measurements validate integration, provenance, schema rejection, and cache behavior;
they are not accuracy measurements. This limitation does not weaken the offline
deterministic gate.

## Installation and quick start

ConformDAG requires Python 3.12. With Python and uv managed through mise, run the pinned
beta without installing it globally:

```bash
mise use python@3.12 uv@0.12.0
mise exec -- uvx --from conformdag==0.1.0b1 conformdag version
```

In an Airflow repository, create the non-destructive starter files and review the empty
policy scaffold before adding organizational rules:

```bash
mise exec -- uvx --from conformdag==0.1.0b1 conformdag init
mise exec -- uvx --from conformdag==0.1.0b1 conformdag validate-policies \
  --path policies/pack.yaml
mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan \
  --path . \
  --policy-pack policies/pack.yaml
```

Source analysis is offline and non-executing unless runtime or semantic evaluation is
explicitly enabled. See the user guide before enabling either networked opt-in.

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
[release checklist](docs/release.md) for publication evidence and verification.

## License

Apache-2.0. See [LICENSE](LICENSE).
