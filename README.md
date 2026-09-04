# ConformDAG

Turn Apache Airflow engineering standards into enforceable, explainable checks.

ConformDAG is a local-first CLI that scans Airflow repositories against versioned
organizational policies. Source analysis is offline and non-executing by default.
Dockerized Airflow import validation and BYOK semantic review are explicit opt-ins.
Every engine contributes to one versioned JSON report that can also be rendered as
terminal output, SARIF, or self-contained HTML.

## Public beta

ConformDAG `1.0.0b1` includes:

- six deterministic Airflow policy evaluators with versioned policy contracts;
- policy provenance validation and human/machine-readable policy inspection;
- expiring suppressions with stale and unmatched-suppression diagnostics;
- a constrained Docker runtime profile for maintained Airflow 3.3.0;
- four opt-in semantic policies through OpenAI-compatible endpoints, with local
  redaction, strict response validation, bounded concurrency, and normalized caching;
- canonical JSON, terminal, SARIF, and static HTML reports; and
- a 240-case offline deterministic benchmark with per-policy release gates.

Provider-backed semantic accuracy baselines are not claimed because the public benchmark
does not yet contain a redistributable, labelled semantic corpus. The recorded provider
smoke measurements validate integration, provenance, schema rejection, and cache behavior;
they are not accuracy measurements. This limitation does not weaken the offline
deterministic gate.

Airflow 2.11.2 was evaluated as a legacy candidate but is not shipped in the beta. It
reached upstream end of life, and maintaining an EOL image would undermine the beta's
security and update cadence. Users who must inspect that version can provide their own
digest-pinned image with `--runtime-image`; it is outside the supported beta profile
matrix and benchmark gate.

## Installation and quick start

ConformDAG requires Python 3.12. With Python and uv managed through mise, run the pinned
beta without installing it globally:

```bash
mise use python@3.12 uv@0.12.0
mise exec -- uvx --from conformdag==1.0.0b1 conformdag version
```

In an Airflow repository, create the non-destructive starter files and review the empty
policy scaffold before adding organizational rules:

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag init
mise exec -- uvx --from conformdag==1.0.0b1 conformdag validate-policies \
  --path policies/pack.yaml
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan \
  --path . \
  --policy-pack policies/pack.yaml
```

Source analysis is offline and non-executing unless runtime or semantic evaluation is
explicitly enabled. See the user guide before enabling either networked opt-in.

### Scan a public Airflow repository

The built-in **community** policy pack focuses on DAG safety checks (timeouts, retries,
and module-scope I/O) without organization-specific owner or tag rules. Pass
`--policy-pack community` from any directory — the pack ships inside the ConformDAG
package, so no checkout of this repository is required:

```bash
git clone --depth 1 https://github.com/apache/airflow.git /tmp/airflow-examples
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan \
  --path /tmp/airflow-examples/airflow-core/src/airflow/example_dags \
  --policy-pack community \
  --format terminal
```

When developing from this repository, the same alias works with `uv run`:

```bash
mise exec -- uv run conformdag scan \
  --path examples/sample-repository \
  --policy-pack community
```

The pack definition lives at
[`src/conformdag/bundled/community-pack.yaml`](src/conformdag/bundled/community-pack.yaml).
The organizational example pack in `policies/pack.yaml` remains available for
platform-team policy contracts with provenance and semantic policies.

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
