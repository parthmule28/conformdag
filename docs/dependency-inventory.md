# Dependency and license inventory

This inventory is reviewed against the declared manifests, lockfiles, and maintained
runtime constraints during release preparation. Run `mise run inventory` to verify the
package names, declared ranges, lock coverage, and supported Airflow profile versions.
The project prefers licenses compatible with Apache-2.0 distribution; any dependency
with a non-permissive or unclear license requires a documented release review.

## Python package declarations

The rows below cover the base package, the optional platform extra, and the development
group declared in `pyproject.toml`. The exact lock graph is recorded in `uv.lock`.

| Package | Scope | Declared specification | License policy | Purpose |
|---|---|---|---|---|
| `httpx` | runtime | `httpx>=0.28,<1` | BSD-3-Clause | OpenAI-compatible provider transport |
| `jinja2` | runtime | `jinja2>=3.1,<4` | BSD-3-Clause | Static HTML report rendering |
| `pydantic` | runtime | `pydantic>=2.11,<3` | MIT | External contract and schema validation |
| `rich` | runtime | `rich>=14,<15` | MIT | Terminal tables and readable output |
| `ruamel.yaml` | runtime | `ruamel.yaml>=0.18,<1` | MIT | YAML policy, config, and manifest parsing |
| `typer` | runtime | `typer>=0.16,<1` | MIT | CLI declaration and help |
| `alembic` | platform | `alembic>=1.16,<2` | MIT | Database migration runner |
| `fastapi` | platform | `fastapi>=0.128,<1` | MIT | Platform HTTP API |
| `psycopg[binary]` | platform | `psycopg[binary]>=3.2,<4` | LGPL-3.0-or-later / PostgreSQL | PostgreSQL driver and binary client |
| `sqlalchemy` | platform | `sqlalchemy>=2.0,<3` | MIT | Platform persistence layer |
| `uvicorn` | platform | `uvicorn>=0.40,<1` | BSD-3-Clause | ASGI server |
| `coverage[toml]` | development | `coverage[toml]>=7.9,<8` | Apache-2.0 | Coverage measurement |
| `pip` | development | `pip>=26.2,<27` | MIT | Isolated packaging tooling |
| `pip-audit` | development | `pip-audit>=2.9,<3` | Apache-2.0 | Dependency vulnerability audit |
| `pytest` | development | `pytest>=9.0.3,<10` | MIT | Test runner |
| `pytest-cov` | development | `pytest-cov>=6,<7` | MIT | Pytest coverage integration |
| `pytest-mock` | development | `pytest-mock>=3.14,<4` | MIT | Test fixture helpers |
| `ruff` | development | `ruff>=0.12,<1` | MIT | Linting and formatting |

## Frontend package declarations

The dashboard's direct dependencies are declared in `frontend/package.json` and fully
resolved in `frontend/package-lock.json` (lockfile version 3). The inventory names both
runtime and development packages; transitive packages remain in the npm lockfile.

| Package | Scope | Declared range | License policy | Purpose |
|---|---|---|---|---|
| `@tanstack/react-query` | runtime | `^5.90.0` | MIT | Server-state queries and cache |
| `react` | runtime | `^19.2.0` | MIT | UI runtime |
| `react-dom` | runtime | `^19.2.0` | MIT | Browser rendering |
| `react-router-dom` | runtime | `^7.18.4` | MIT | SPA routing |
| `@playwright/test` | development | `^1.63.0` | Apache-2.0 | Browser acceptance tests |
| `@tailwindcss/vite` | development | `^4.1.0` | MIT | Tailwind Vite integration |
| `@testing-library/jest-dom` | development | `^7.0.1` | MIT | DOM assertions |
| `@testing-library/react` | development | `^16.3.3` | MIT | React component tests |
| `@types/node` | development | `^26.6.1` | MIT | Node.js type definitions |
| `@types/react` | development | `^19.2.0` | MIT | React type definitions |
| `@types/react-dom` | development | `^19.2.0` | MIT | React DOM type definitions |
| `@vitejs/plugin-react` | development | `^5.1.0` | MIT | React Vite integration |
| `jsdom` | development | `^30.1.0` | MIT | DOM test environment |
| `tailwindcss` | development | `^4.1.0` | MIT | Utility-first styling |
| `typescript` | development | `^5.9.0` | Apache-2.0 | TypeScript compiler |
| `vite` | development | `^7.1.0` | MIT | Frontend build tool |
| `vitest` | development | `^5.0.1` | MIT | Frontend test runner |

## Runtime profile constraints

Airflow and provider dependencies are isolated in the maintained runtime image rather
than installed into the host CLI. `runtime/airflow-3.3.0/constraints.txt` is the
runtime profile's version source of truth and the image is recorded by immutable digest
in the release evidence.

| Package | Constraint | Role | License policy |
|---|---|---|---|
| `apache-airflow` | `==3.3.0` | Maintained runtime | Apache-2.0 |
| `apache-airflow-providers-standard` | `==1.15.0` | Maintained provider | Apache-2.0 |
| `apache-airflow-providers-postgres` | `==6.8.0` | Maintained provider | Apache-2.0 |
| `apache-airflow-providers-http` | `==6.0.4` | Maintained provider | Apache-2.0 |
| `apache-airflow-providers-google` | `==22.2.2` | Maintained provider | Apache-2.0 |

The Docker CLI is an external system dependency for the explicit runtime boundary. The
runtime image also carries its own transitive operating-system and Python dependency
SBOM; release image scans and provenance attestations are recorded in `docs/release.md`.

## Lockfile coverage

- `uv.lock` currently records **63** resolved Python package records for the declared
  project, platform, and development environments.
- `frontend/package-lock.json` currently records **241** resolved npm package records
  beneath its root package (the root workspace entry is not counted).
- The inventory check fails when a declared direct package is absent from its lockfile,
  when a lockfile count changes without an inventory update, or when the runtime
  constraints disagree with the maintained profile metadata.

Generated reports, benchmark fixtures, and caches must not bundle third-party source
code without an explicit redistribution review.
