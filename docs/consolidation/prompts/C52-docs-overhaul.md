# C52 — Rewrite Architecture, Security, Compatibility, and Development Docs

## Role and objective

You are the Build agent for C52. Bring documentation in line with the consolidated boundaries and teach contributors how to add checks, analysis families, adapters, migrations, and contracts safely.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C16/C18/C21/C28/C30.
- `docs/architecture.md`, `docs/security.md` if present, `docs/compatibility.md`, `docs/development.md`, `docs/user-guide.md`, ADRs, and current package structure.

## Current ownership and resulting owner

Architecture docs currently describe a modular CLI but not the application/service/transport boundaries introduced by C01–C51. After this PR, docs explain domain, application, analysis families, checks, reporting, policy, persistence, runtime, semantic, agent, CLI, HTTP, and future MCP boundaries.

## Interfaces

Document exact extension recipes:

- Add a deterministic check through `CheckSpec`.
- Add an analysis family without making Airflow models generic.
- Add a transport adapter through application services.
- Change DB schema through Alembic.
- Add an API contract through Pydantic/OpenAPI/generated TypeScript.

## Expected files

- Modify: `docs/architecture.md`, `docs/security.md`, `docs/compatibility.md`, `docs/development.md`, `docs/policy-authoring.md`, `README.md`, and linked docs.
- Create missing docs named above and update relative links.
- Do not duplicate implementation logic in docs or change product code.

## Test-first sequence

1. Audit stale claims against current code and backlog evidence.
2. Add/update docs with diagrams, ownership tables, security assumptions, compatibility promises, and extension recipes.
3. Run relative-link/documentation checks and inspect every command for current task names.
4. Perform a clean-reader review: a new contributor can add a check, migrate a model, and add an adapter without hidden knowledge.
5. Run `mise run check` and docs/security checks.

## Allowed changes

- Architecture/security/compatibility/development/policy docs and links.

## Non-goals and prohibitions

- Do not document planned MCP/dbt behavior as shipped functionality.
- Do not leave contradictory diagrams or stale module names.
- Do not use documentation to waive a tested invariant.

## Verification matrix

- Relative-link check, command snippets review, default gate, security/privacy docs review.

## Completion checklist and handoff

- [ ] Architecture ownership matches implementation.
- [ ] Security and compatibility promises are current.
- [ ] Extension procedures name exact files/commands.
- [ ] Commit with `docs: update consolidated architecture guidance`; open the PR without merging.
