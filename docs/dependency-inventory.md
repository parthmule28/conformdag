# Dependency and license inventory

This inventory is reviewed against pyproject.toml and the lockfile during
release preparation. The project prefers permissive licenses compatible with
Apache-2.0 distribution.

| Component | Purpose | License policy |
|---|---|---|
| Python standard library | AST analysis, hashing, filesystem and process boundaries | Python Software Foundation License |
| Pydantic | External contract and schema validation | MIT |
| ruamel.yaml | YAML policy, config, and manifest parsing | MIT |
| Typer | CLI declaration and help | MIT |
| Rich | Terminal tables and readable output | MIT |
| Jinja2 | Static HTML report rendering | BSD-3-Clause |
| HTTPX | OpenAI-compatible provider transport | BSD-3-Clause |
| Docker CLI | Explicit host runtime boundary, invoked without a shell | External system dependency |
| pytest and coverage | Development and test tooling | MIT / Apache-2.0 |
| Ruff | Development lint and formatting | MIT |
| Pyright | Development type checking | MIT |

Airflow and provider dependencies are isolated in versioned runtime images and
are not package dependencies of the host CLI. Published profile tags are resolved
to immutable digests before execution. Each release records constraints, provider
versions, SBOM/provenance attestations, and image scan results.

Any dependency with a non-permissive or unclear license requires a documented
review before release. Generated reports, benchmark fixtures, and caches must
not bundle third-party source code without an explicit redistribution review.
