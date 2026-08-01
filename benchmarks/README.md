# Benchmark corpus

The checked-in beta corpus is a controlled hybrid. Its labelled fixtures are
project-owned and generated from named deterministic recipes, while the manifest
records pinned public Airflow repositories used as pattern and compatibility
references. This keeps the labels reproducible without claiming that every public
DAG follows ConformDAG's organization-specific policy pack.

It contains 40 applicable cases for each deterministic policy: 20 violations and
20 valid or safe-counterexample cases. Public source admission records are in
`../public-sources.yaml` and are copied into the generated manifest with exact
revisions, licensing, transformation, privacy and secrets review metadata.

Regenerate it with:

```text
mise exec -- uv run python scripts/generate_synthetic_benchmark.py
```

Verify hashes and execute the deterministic cases offline with:

```text
mise run benchmark
```

The JSON result includes per-policy and aggregate precision, recall, F1,
false-positive/negative rates, abstention and invalid-output rates, plus
operational metric fields. Metrics that require a semantic provider or
provider telemetry are reported as `null` with an explicit provenance value.
The deterministic release gate requires at least 40 cases per policy, at
least 20 violations and 20 valid or safe-counterexamples, 95% precision, and
90% recall.

To save both report formats:

```text
mise exec -- uv run conformdag benchmark benchmarks/synthetic \
  --policy-pack policies/pack.yaml \
  --output .conformdag/benchmark-report.json \
  --technical-report .conformdag/benchmark-report.md
```

`synthetic/manifest.yaml` records fixture hashes, policy versions and hashes,
source attribution, licensing, transformation history, and privacy/secrets review.
No external organizational data or public source files are redistributed by this
fixture release.
