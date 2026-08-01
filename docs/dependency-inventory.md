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
| Docker SDK optional extra | Optional host runtime integration | Apache-2.0 |
| pytest and coverage | Development and test tooling | MIT / Apache-2.0 |
| Ruff | Development lint and formatting | MIT |
| Pyright | Development type checking | MIT |

Airflow and provider dependencies are isolated in pinned runtime images and
are not package dependencies of the host CLI. Each runtime profile records its
base image digest, constraints, provider versions, and image scan results.

Any dependency with a non-permissive or unclear license requires a documented
review before release. Generated reports, benchmark fixtures, and caches must
not bundle third-party source code without an explicit redistribution review.
