# ConformDAG user guide

## Installation and setup

Run the pinned public beta without installing it globally:

```bash
mise use python@3.12 uv@0.12.0
mise exec -- uvx --from conformdag==0.1.0b1 conformdag version
```

Contributors working from a checkout use the locked development environment:

```bash
mise install
mise run setup
mise exec -- uv run conformdag version
```

Initialize ConformDAG metadata in an Airflow repository:

```bash
mise exec -- uvx --from conformdag==0.1.0b1 conformdag init
```

This creates `conformdag.yaml`, a policy-pack scaffold, authoring standards, and an
empty suppression file. Review and populate the policy pack before scanning.

## Policy-pack review

```bash
mise exec -- uvx --from conformdag==0.1.0b1 conformdag validate-policies --path policies/pack.yaml
mise exec -- uvx --from conformdag==0.1.0b1 conformdag list-policies --path policies/pack.yaml
mise exec -- uvx --from conformdag==0.1.0b1 conformdag policy show AIR-DET-001 --path policies/pack.yaml
mise exec -- uvx --from conformdag==0.1.0b1 conformdag policy review AIR-DET-001 --path policies/pack.yaml
mise exec -- uvx --from conformdag==0.1.0b1 conformdag policy explain AIR-DET-001 --path policies/pack.yaml
mise exec -- uvx --from conformdag==0.1.0b1 conformdag policy reference all
```

`show` is a concise human summary. `review` adds provenance, configuration,
exceptions, and enforcement details. `explain` emits the complete machine-readable JSON
contract. `reference` documents outcomes, reports, runtime terms, and exit codes.

## Configuration precedence

Configuration resolves in this order:

1. command-line options;
2. `conformdag.yaml`;
3. environment-only secrets such as `CONFORMDAG_MODEL_API_KEY`;
4. package defaults.

Credentials are never accepted from YAML, policy packs, source files, command-line
arguments, or cache files.

## Offline scans and reports

The default scan never imports repository Python and never contacts a provider:

```bash
mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan \
  --path . --policy-pack policies/pack.yaml
```

JSON is the canonical machine-readable output. Other projections are:

```bash
mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan --path . --format terminal
mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan --path . --format sarif --output report.sarif
mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan --path . --format html --output report.html
```

Use `--no-evidence` when a rendered artifact must exclude source excerpts. Generated
reports should be treated as potentially sensitive even though credential-like values
are redacted.

Exit codes are `0` for a complete successful run, `1` for a complete blocking policy
failure, `2` for invalid input/configuration, and `3` for an incomplete or failed phase.

## Suppressions

A suppression is a time-bounded, owned exception for one exact finding fingerprint and
policy ID. It requires a reason and expiry. Expired suppressions reopen findings;
duplicate or unmatched records are reported so stale exceptions remain auditable. A
suppression does not change the policy contract or hide unrelated future findings.

## Semantic review

Semantic evaluation is BYOK, opt-in, and networked. Configure non-secret settings in
`conformdag.yaml`:

```yaml
semantic:
  enabled: false
  base_url: https://openrouter.ai/api/v1
  model: deepseek/deepseek-v4-flash
  api_key_env: CONFORMDAG_MODEL_API_KEY
  temperature: 0.0
  max_input_tokens: 32000
  max_output_tokens: 4000
  max_concurrency: 4
  native_structured_output: true
  cache_path: .conformdag/semantic-cache.json
```

Inject the key into only the child process. For the Infisical project already linked to
the checkout:

```bash
infisical run --env=dev --path=/ -- \
  mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan \
  --path . \
  --semantic \
  --semantic-base-url https://openrouter.ai/api/v1 \
  --semantic-model deepseek/deepseek-v4-flash \
  --semantic-structured-output
```

Before each request, ConformDAG bounds and redacts context locally. Repository text is
delimited as untrusted evidence, model tools are disabled, and responses must satisfy a
strict schema. The normalized cache stores validated decisions and audit metadata—not
API keys or raw provider payloads. Use `--preview-model-context` to inspect exactly what
would be sent without calling a provider.

Provider-backed accuracy measurements are not part of the current public corpus. The
deterministic benchmark therefore reports semantic baselines as `not_executed`. Recorded
provider smoke measurements cover integration, provenance, schema rejection, and cache
behavior—not model accuracy; see the [release checklist](release.md).

## Runtime inspection

Runtime mode imports DAGs inside a constrained Docker container after validating a host
manifest. Supported profiles use no network, a read-only repository and root filesystem,
a non-root user, dropped capabilities, `no-new-privileges`, and bounded resources:

```bash
mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan --path . --runtime 3.3.0
mise exec -- uvx --from conformdag==0.1.0b1 conformdag scan --path . --runtime 2.11.2
```

The profile image is pulled and resolved to an immutable digest before execution. Airflow
3.3.0 is maintained; 2.11.2 is an EOL compatibility profile. Docker and the selected
image are trusted dependencies, so this boundary is not a perfect sandbox. A custom
runtime image is unsupported and must be supplied by digest with `--runtime-image`.

## Benchmarks and local gates

```bash
mise run check
mise run benchmark
mise run test:coverage
mise run schema
mise run security
mise run privacy
```

Save deterministic benchmark evidence with:

```bash
mise exec -- uvx --from conformdag==0.1.0b1 conformdag benchmark benchmarks/synthetic \
  --policy-pack policies/pack.yaml \
  --output .conformdag/benchmark-report.json \
  --technical-report .conformdag/benchmark-report.md
```

The checked-in benchmark verifies fixture hashes, provenance, and labels before running
240 offline cases. It reports per-policy and aggregate quality metrics plus explicit
`null`/provenance values for measurements unavailable without a semantic corpus or
provider telemetry.

## Current limitations

- The default scanner intentionally supports a bounded subset of Python/Airflow syntax;
  unresolved dynamic behavior becomes review evidence rather than guessed execution.
- Runtime mode requires Docker and does not replace review of untrusted code.
- Semantic findings depend on the configured provider and remain advisory unless their
  policy contract declares blocking behavior.
- Interactive policy authoring, signed policy distribution, central synchronization,
  multi-user roles, and dashboards are follow-up capabilities.
