# ConformDAG user guide

## Installation and setup

Run the pinned public beta without installing it globally:

```bash
mise use python@3.12 uv@0.12.0
mise exec -- uvx --from conformdag==1.0.0b1 conformdag version
```

Contributors working from a checkout use the locked development environment:

```bash
mise install
mise run setup
mise exec -- uv run conformdag version
```

Initialize ConformDAG metadata in an Airflow repository:

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag init
```

This creates `conformdag.yaml`, a policy-pack scaffold, authoring standards, and an
empty suppression file. Review and populate the policy pack before scanning.

## Policy-pack review

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag validate-policies --path policies/pack.yaml
mise exec -- uvx --from conformdag==1.0.0b1 conformdag list-policies --path policies/pack.yaml
mise exec -- uvx --from conformdag==1.0.0b1 conformdag policy show AIR-DET-001 --path policies/pack.yaml
mise exec -- uvx --from conformdag==1.0.0b1 conformdag policy review AIR-DET-001 --path policies/pack.yaml
mise exec -- uvx --from conformdag==1.0.0b1 conformdag policy explain AIR-DET-001 --path policies/pack.yaml
mise exec -- uvx --from conformdag==1.0.0b1 conformdag policy reference all
```

`show` is a concise human summary. `review` adds provenance, configuration,
exceptions, and enforcement details. `explain` emits the complete machine-readable JSON
contract. `reference` documents outcomes, reports, runtime terms, and exit codes.

### Community quickstart pack

For a first scan of a public or unfamiliar repository, use the built-in community pack.
It checks DAG safety (timeouts, retries, and module-scope I/O) without
organization-specific owner or tag rules:

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag validate-policies --path community
mise exec -- uvx --from conformdag==1.0.0b1 conformdag list-policies --path community
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan \
  --path /path/to/airflow-repo/dags \
  --policy-pack community \
  --format terminal
```

The alias `community` (also accepted as `builtin:community`) resolves to the policy pack
shipped inside the ConformDAG package. Use `policies/pack.yaml` when authoring an
organizational contract in your own repository.

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
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan \
  --path . --policy-pack policies/pack.yaml
```

JSON is the canonical machine-readable output. Other projections are:

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan --path . --format terminal
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan --path . --format sarif --output report.sarif
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan --path . --format html --output report.html
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

## Deterministic fixes

`conformdag fix` proposes source patches for deterministic findings, verifies them by
re-scanning an isolated patched copy, and writes nothing unless `--apply` is passed:

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag fix --path .
mise exec -- uvx --from conformdag==1.0.0b1 conformdag fix --path . --apply
```

Dry run prints a unified diff identical to what `--apply` would write. Generation is
deterministic: identical inputs produce byte-identical diffs. Every finding carries a
machine-readable remediation payload (action, target anchor, concrete configured value),
so agents and other tools can act on the report JSON without re-reading the repository.

The fixability matrix is explicit per check kind:

- `required-owner`, `required-tags`, `execution-timeout`, `retry-bounds` are mechanical
  autofix; patches are applied only after a clean re-scan of the patched copy.
- `top-level-io` produces a proposed-only structural move diff that is never applied,
  including under `--apply`.
- `forbidden-operators`, `idempotence`, and other judgment-call kinds are reported as
  not fixable with remediation guidance.

`--apply` writes only verified patches. A fixable finding that still fails after the
bounded verification loop is reported as a residual, blocks the apply exit code, and
leaves that file untouched.

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
  mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan \
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
mise exec -- uvx --from conformdag==1.0.0b1 conformdag scan --path . --runtime 3.3.0
```

The profile image is pulled and resolved to an immutable digest before execution. Airflow
3.3.0 is the maintained beta profile. Airflow 2.11.2 was initially evaluated as a
compatibility profile but excluded before publication because it reached upstream end of
life and would weaken the beta's security/update maintenance boundary. Docker and the
selected image are trusted dependencies, so this boundary is not a perfect sandbox. A
custom runtime image is unsupported and must be supplied by digest with `--runtime-image`.

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
mise exec -- uvx --from conformdag==1.0.0b1 conformdag benchmark benchmarks/synthetic \
  --policy-pack policies/pack.yaml \
  --output .conformdag/benchmark-report.json \
  --technical-report .conformdag/benchmark-report.md
```

The checked-in benchmark verifies fixture hashes, provenance, and labels before running
240 offline cases. It reports per-policy and aggregate quality metrics plus explicit
`null`/provenance values for measurements unavailable without a semantic corpus or
provider telemetry.

## Agentic fix loop

`conformdag agent run` turns findings into human-merged pull requests. The agent
is a tool user of the deterministic engine, never a second evaluation path:
triage and patch generation are pure rules, the deterministic re-scan proves
policy compliance, and an LLM performs only one bounded role — a semantic
sanity review of the diff against a strict verdict schema (`approve`, `reject`,
or `escalate`; reject and escalate block the pull request).

Configure through namespaced environment variables:

| Variable | Meaning |
|---|---|
| `CONFORMDAG_AGENT_BASE_URL` | OpenAI-compatible chat endpoint for the verifier |
| `CONFORMDAG_AGENT_MODEL` | Exact verifier model ID |
| `CONFORMDAG_AGENT_API_KEY_ENV` | Name of the env var holding the API key (default `CONFORMDAG_MODEL_API_KEY`) |
| `CONFORMDAG_GITHUB_TOKEN` | GitHub App installation token used to open PRs |
| `CONFORMDAG_GITHUB_REPO` | `owner/name` slug for PR creation |
| `CONFORMDAG_AGENT_BASE_BRANCH` | PR base branch (default `main`) |

The agent identity is a GitHub App installation token with least-privilege
permissions: `contents: write` (branch push) and `pull_requests: write` only.
There is no merge, approve, or force-push capability in the harness by
construction.

```bash
mise exec -- uvx --from conformdag==1.0.0b1 conformdag agent run --path .
mise exec -- uvx --from conformdag==1.0.0b1 conformdag agent run --path . --open-pr
```

Safety properties: every mechanical patch comes from the deterministic codemod
registry; no PR is opened unless its re-scan is clean and the verifier approves;
diff content is credential-redacted and delimited as untrusted evidence before a
model call; verdicts are cached by diff hash and report fingerprints.

`conformdag agent policy-review` aggregates scan reports on disk into a
governance proposal (fail rates, suppression rates, stale suppressions) for the
next pack version — committing and tagging the pack remains a human git
operation.

## Governance platform

The self-hosted team server (dashboard API, durable scan worker, Postgres) is
deployed with Docker Compose. See the [platform deploy
guide](platform-deploy.md) for the documented deploy, workspace registration,
the stable `/api/v1` contract, and the single-admin authentication posture.

## Current limitations

- The default scanner intentionally supports a bounded subset of Python/Airflow syntax;
  unresolved dynamic behavior becomes review evidence rather than guessed execution.
- Runtime mode requires Docker and does not replace review of untrusted code.
- Semantic findings depend on the configured provider and remain advisory unless their
  policy contract declares blocking behavior.
- The dashboard SPA covers repo status, scan triggering, history, findings,
  suppression management, and exports; multi-user RBAC, MCP for IDE agents, SSO
  pack download, and signed policy distribution are follow-up capabilities.
