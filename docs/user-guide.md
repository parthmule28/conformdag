# ConformDAG user guide

## Installation and setup

ConformDAG is currently developed from a checkout. Install and lock the project
through mise:

    mise install
    mise run setup

The supported local entry point is mise exec -- conformdag ...; mise owns the
Python, uv, Ruff, Pyright, OpenSpec, and security-tool versions.

Initialize a new project:

    mise exec -- conformdag init

This creates conformdag.yaml, a policy-pack scaffold, authoring standards, and
an empty suppression file. Review and populate the policy pack before scanning.

## Policy-pack review

Validate provenance and schema:

    mise exec -- conformdag validate-policies --path policies/pack.yaml

List active and inactive policies:

    mise exec -- conformdag list-policies --path policies/pack.yaml

Use policy show for a concise human summary, policy review for provenance,
configuration, exceptions, and enforcement details, and policy explain for the
complete machine-readable JSON contract:

    mise exec -- conformdag policy show AIR-DET-001 --path policies/pack.yaml
    mise exec -- conformdag policy review AIR-DET-001 --path policies/pack.yaml
    mise exec -- conformdag policy explain AIR-DET-001 --path policies/pack.yaml

## Configuration precedence

Defaults are built into the package. The precedence order is:

1. command-line arguments;
2. conformdag.yaml;
3. environment-only secrets such as CONFORMDAG_MODEL_API_KEY;
4. package defaults.

The project configuration controls scan include/exclude patterns, policy-pack
selection, suppressions, semantic budgets, and runtime settings. Credentials
are never read from YAML, policy packs, source files, or cache files.

## Scanning and reports

Run the default offline source scan:

    mise exec -- conformdag scan --path . --policy-pack policies/pack.yaml --format json

The canonical JSON report is machine-readable. Terminal output is for triage,
SARIF is for code-scanning integrations, and HTML is a self-contained offline
artifact:

    mise exec -- conformdag scan --path . --policy-pack policies/pack.yaml --format terminal
    mise exec -- conformdag scan --path . --policy-pack policies/pack.yaml --format sarif --output report.sarif
    mise exec -- conformdag scan --path . --policy-pack policies/pack.yaml --format html --output report.html

Use the built-in reference to explain outcomes, exit codes, runtime contracts,
and report formats:

    mise exec -- conformdag policy reference all

Exit codes are 0 for a complete successful run, 1 for a complete blocking
failure, 2 for invalid input, and 3 for an incomplete or failed evaluation.

## Semantic privacy and baselines

Semantic evaluation is opt-in and BYOK. It is disabled by default. Before any
provider-backed evaluation, ConformDAG selects bounded context, redacts
credential-like values locally, hashes the context and prompt, and wraps
repository text as untrusted evidence. Raw prompts and responses are not
written to the normalized cache by default.

The semantic provider requires an exact configured model and an environment
variable containing the API key. Unknown pricing remains unknown. The
benchmark reports provider-dependent baselines as not_executed unless they are
explicitly configured.

## Runtime trust boundary

Runtime mode is an explicit Docker execution boundary for Airflow import
validation. The host validates a runtime manifest first; the image then reads
the repository through a read-only mount. Supported profiles disable network
access, drop capabilities, use a non-root user, use a read-only root
filesystem, and apply CPU, memory, process, temporary-storage, and wall-clock
limits. This is a constrained boundary, not a complete security sandbox.

Select a published profile explicitly:

    mise exec -- conformdag scan --path . --policy-pack policies/pack.yaml --runtime 3.3.0

Airflow 3.3.0 is the maintained profile. Airflow 2.11.2 is retained as a
legacy compatibility profile and is labelled EOL. Custom images are opt-in,
must be explicitly supplied, and receive no supported-profile compatibility
guarantee.

## Offline benchmark

The deterministic benchmark verifies fixture hashes before non-executing
analysis and does not contact a provider:

    mise run benchmark

Save machine-readable and human-readable reports:

    mise exec -- conformdag benchmark benchmarks/synthetic \
      --policy-pack policies/pack.yaml \
      --output .conformdag/benchmark-report.json \
      --technical-report .conformdag/benchmark-report.md

The report includes dataset identity, provenance, per-policy metrics, quality
gates, operational fields, cache state, and explicit status for unexecuted
semantic baselines.

## Limitations

ConformDAG does not execute repository Python source in the default scan, does
not claim Docker to be a perfect sandbox, and does not infer organizational
approval from public DAG frequency. Semantic results remain advisory unless a
policy explicitly defines blocking behavior. Policy authoring, distribution,
multi-user roles, and centralized synchronization are deferred to a follow-up
change.
