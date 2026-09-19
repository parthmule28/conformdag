# ConformDAG Comprehensive Consolidation Backlog

This is the program index for the 64 PR-sized slices described in the approved consolidation blueprint. Each row links to one ready-to-paste Build prompt. The current status of every slice is `planned`; implementation evidence belongs in `progress.md`.

## Dependency notation

`—` means no consolidation dependency. A range such as `C01–C03` includes every slice in that range. Dependencies are acceptance dependencies, not a requirement to merge all listed commits into one branch.

## Phase gates

| Phase | Slices | Exit gate |
| --- | --- | --- |
| Foundation and vocabulary | C01–C02 | Baseline is reproducible; ownership rules and terminology are reviewed. |
| Registry, analysis, and application | C03–C11 | One catalogue and one complete application scan workflow have parity tests. |
| Platform and policy boundaries | C12–C20 | Routes delegate to services; policy/reporting/security ownership is explicit. |
| Models, persistence, and adapters | C21–C32 | Package facades, transaction rules, Postgres evidence, CLI, OpenAPI, and frontend contracts are stable. |
| Testing, architecture, and supply chain | C33–C44 | Test layers, true coverage, dependency/package/CI audits, architecture checks, filesystem and observability rules pass. |
| Governance and threat documentation | C45–C54 | Errors, configuration, demo/benchmark surfaces, docs, agent guidance, and threat model are current. |
| Adversarial and independent verification | C55–C60 | Permanent adversarial/stress/performance suites and fresh independent reviews replay the historical audit. |
| Release and completion | C61–C64 | Clean onboarding, package rehearsal, final enforcement, and evidence report pass. |

## Slice index

| ID | Prompt | Focus | Dependencies | Risk | Gates |
| --- | --- | --- | --- | --- | --- |
| C01 | [Baseline and architecture contract](prompts/C01-baseline-contract.md) | Establish measurements, rules, ADR, and ledger | — | low | L |
| C02 | [Domain vocabulary](prompts/C02-domain-vocabulary.md) | Separate policy, check, configuration, and fix terms | C01 | medium | L, S, FE |
| C03 | [Authoritative check catalogue](prompts/C03-check-catalogue.md) | Derive evaluator, fixability, legacy, and scaffold metadata | C01–C02 | high | L, B, REV |
| C04 | [Analysis package](prompts/C04-analysis-package.md) | Split discovery, models, cache, and Airflow analysis behind a facade | C01 | medium | L, C |
| C05 | [Deterministic checks](prompts/C05-deterministic-checks.md) | Split evaluator families and preserve the legacy facade | C03–C04 | high | L, C, B, REV |
| C06 | [Application scan workflow](prompts/C06-application-scan.md) | Add reusable complete scan orchestration over `scan_repository` | C03–C05 | critical | L, C, REV |
| C07 | [Effective configuration](prompts/C07-effective-configuration.md) | Centralize precedence and dependency construction | C06 | high | L, C, REV |
| C08 | [Airflow profile use](prompts/C08-airflow-profile.md) | Make platform repository profile overrides effective | C07 | medium | L, C |
| C09 | [Typed scan state](prompts/C09-typed-scan-state.md) | Type statuses, triggers, and transition tests | C01 | high | L, PG, REV |
| C10 | [Platform runner delegation](prompts/C10-platform-runner.md) | Make runner call application workflow and persist results | C06–C09 | critical | L, C, PG, REV |
| C11 | [Outcome classification](prompts/C11-outcome-classification.md) | Centralize success, policy failure, and incomplete semantics | C06, C10 | medium | L, C |
| C12 | [Platform services](prompts/C12-platform-services.md) | Extract reusable repository, scan, baseline, and suppression services | C10–C11 | high | L, C, REV |
| C13 | [FastAPI routes](prompts/C13-fastapi-routes.md) | Split transport modules and leave `app.py` as composition root | C12 | high | L, FE, PW, REV |
| C14 | [Platform contracts](prompts/C14-platform-contracts.md) | Centralize typed request/response wire contracts | C02, C13 | high | L, FE, S |
| C15 | [Security redaction](prompts/C15-security-redaction.md) | Establish one credential redaction implementation | C05, C10 | high | L, SEC, REV |
| C16 | [Policy package](prompts/C16-policy-package.md) | Split loading, provenance, validation, and hashing | C01 | medium | L, C |
| C17 | [Policy editing](prompts/C17-policy-editing.md) | Extract canonical pack mutation service | C03, C12, C16 | high | L, C, SEC, REV |
| C18 | [Reporting package](prompts/C18-reporting-package.md) | Split normalization, suppressions, and renderers | C01, C06 | medium | L, C |
| C19 | [Fingerprint contract](prompts/C19-fingerprint-contract.md) | Document and version finding/report identity | C18 | high | L, C, REV |
| C20 | [Baseline and suppression unification](prompts/C20-baseline-suppression.md) | Share baseline value semantics across CLI/platform/future adapters | C11, C19 | high | L, C, REV |
| C21 | [Models package](prompts/C21-models-package.md) | Split domain models while preserving exports and schemas | C02, C18–C20 | high | L, C, S |
| C22 | [Semantic package](prompts/C22-semantic-package.md) | Split context, prompts, provider, cache, and evaluator | C15, C21 | high | L, C, SEC |
| C23 | [Runtime package](prompts/C23-runtime-package.md) | Separate profiles, manifests, and Docker execution if cohesion warrants it | C06, C21 | medium | L, RT, SEC |
| C24 | [Platform persistence](prompts/C24-platform-persistence.md) | Split ORM, migrations, scans, baselines, and retention | C09, C10, C21 | high | L, PG, REV |
| C25 | [Transaction ownership](prompts/C25-transaction-ownership.md) | Document and test transaction boundaries and failure atomicity | C24 | high | L, PG |
| C26 | [Postgres integration](prompts/C26-postgres-integration.md) | Add production-database concurrency and migration suite | C24–C25 | critical | L, PG, REV |
| C27 | [Worker and runner cleanup](prompts/C27-worker-runner.md) | Enforce process-lifecycle versus application/persistence ownership | C10, C24–C26 | high | L, PG, REV |
| C28 | [CLI package](prompts/C28-cli-package.md) | Split Typer adapters after business extraction | C06, C12, C16 | high | L, C |
| C29 | [CLI output](prompts/C29-cli-output.md) | Centralize error boundary, formats, rendering, and exit mapping | C11, C18, C28 | medium | L, C |
| C30 | [Compatibility layer](prompts/C30-compatibility.md) | Make legacy imports, IDs, commands, and deprecations explicit | C02, C28–C29 | high | L, C, REV |
| C31 | [OpenAPI TypeScript types](prompts/C31-openapi-types.md) | Generate frontend API types from FastAPI OpenAPI | C13–C14 | high | L, FE, PW |
| C32 | [Frontend API cleanup](prompts/C32-frontend-api.md) | Remove redundant client surface and backend domain duplication | C31 | medium | FE, PW |
| C33 | [Test suite split](prompts/C33-test-suite-split.md) | Split platform/CLI/check tests with focused fixtures | C12–C14, C28 | medium | L, C |
| C34 | [Layered tests](prompts/C34-layered-tests.md) | Move behavior assertions to application/domain layers | C06, C10, C12, C33 | high | L, C, PG |
| C35 | [True production coverage](prompts/C35-production-coverage.md) | Remove exclusions with meaningful tests | C33–C34 | high | L, C, B |
| C36 | [Property and mutation review](prompts/C36-property-mutation.md) | Assess high-value invariants and test strength | C19–C20, C35 | medium | C, REV |
| C37 | [Dependency ownership](prompts/C37-dependency-audit.md) | Audit direct/dev dependencies and remove proven dead entries | C35 | low | L, SEC |
| C38 | [Packaging audit](prompts/C38-packaging-audit.md) | Verify wheel, sdist, static assets, bundled pack, and installed smoke | C31, C37 | high | P, SEC |
| C39 | [Container audit](prompts/C39-container-audit.md) | Audit runtime/platform images, users, caches, and sizes | C23, C38 | high | P, RT, SEC |
| C40 | [CI consolidation](prompts/C40-ci-consolidation.md) | Align local tasks and CI jobs with explicit verification tiers | C35, C37–C39 | medium | L, P, SEC |
| C41 | [Architecture tests](prompts/C41-architecture-tests.md) | Add import/dependency direction validator | C12–C14, C24, C28 | high | L, ARCH, REV |
| C42 | [Import side effects](prompts/C42-import-side-effects.md) | Prove imports do not migrate, connect, execute, or mutate | C41 | medium | L, ARCH |
| C43 | [Filesystem boundary](prompts/C43-filesystem-boundary.md) | Centralize containment helpers without changing discovery symlink semantics | C04, C15, C41 | high | L, SEC, REV |
| C44 | [Observability](prompts/C44-observability.md) | Normalize events, correlation fields, and privacy rules | C10, C12, C27 | medium | L, SEC |
| C45 | [Error taxonomy](prompts/C45-error-taxonomy.md) | Replace message parsing with typed adapter-boundary errors | C11–C13, C17 | medium | L, C |
| C46 | [Configuration inventory](prompts/C46-config-inventory.md) | Inventory environment variables and keep secrets out of domain config | C07, C22, C45 | medium | L, SEC |
| C47 | [Demo code](prompts/C47-demo-code.md) | Separate synthetic demo construction from production package code | C28, C38 | low | L, P |
| C48 | [Benchmark package](prompts/C48-benchmark-package.md) | Split benchmark concerns and keep production dependency direction | C35, C37 | medium | L, B |
| C49 | [Dead-code audit](prompts/C49-dead-code-audit.md) | Review wrappers, aliases, inert fields, and tool findings | C33, C37, C47–C48 | medium | L, C |
| C50 | [Complexity pass](prompts/C50-complexity-pass.md) | Refactor mixed-responsibility hotspots based on measurements | C33, C49 | medium | L, C, REV |
| C51 | [Backlog-marker and legacy audit](prompts/C51-todo-audit.md) | Resolve or track all backlog markers and temporary paths | C49, C52 | low | L |
| C52 | [Documentation architecture](prompts/C52-docs-overhaul.md) | Rewrite architecture, security, compatibility, and development docs | C16, C18, C21, C28–C30 | medium | L |
| C53 | [AGENTS rewrite](prompts/C53-agents-rewrite.md) | Encode architecture rules and gates for coding agents | C41, C52 | medium | L |
| C54 | [Threat model](prompts/C54-threat-model.md) | Reassess repository, pack, provider, MCP, filesystem, and persistence threats | C15, C24, C27, C43–C46 | high | SEC, REV |
| C55 | [Adversarial suite](prompts/C55-adversarial-suite.md) | Add permanent hostile-input regression fixtures | C43, C54 | high | L, SEC, REV |
| C56 | [Postgres stress](prompts/C56-postgres-stress.md) | Exercise repeated worker claims, cancellation, reclaim, and first boot | C26–C27 | high | PG, REV |
| C57 | [Performance characterization](prompts/C57-performance.md) | Record cold/warm scans, ingest, history, fix, and large-repo baselines | C35, C48, C56 | medium | B |
| C58 | [Independent security review](prompts/C58-security-review.md) | Fresh security audit across all trust boundaries | C54–C57 | critical | SEC, REV |
| C59 | [Independent architecture review](prompts/C59-architecture-review.md) | Fresh duplication, cohesion, and extension review | C41, C52, C57 | high | ARCH, REV |
| C60 | [Historical audit replay](prompts/C60-audit-replay.md) | Replay all recorded historical remediation findings and evidence | C58–C59 | critical | L, SEC, REV |
| C61 | [Clean onboarding](prompts/C61-onboarding.md) | Verify clone-to-check workflow using docs only | C52–C53, C60 | high | L, P, PW |
| C62 | [Release rehearsal](prompts/C62-release-rehearsal.md) | Build/install/serve/image/SBOM rehearsal without publishing | C38–C40, C61 | high | P, RT, SEC |
| C63 | [Final enforcement](prompts/C63-enforcement.md) | Tighten `mise run check` with architecture and generated-contract gates | C41–C42, C46, C52, C62 | high | L, ARCH, SEC |
| C64 | [Final report](prompts/C64-final-report.md) | Publish evidence, metrics, limitations, and MCP/dbt readiness | C60–C63 | medium | REV |

## Program completion

The consolidation is complete only when C64 records evidence for one application scan workflow, one check catalogue, reusable service boundaries, typed contracts, shared security rules, real Postgres testing, true production coverage, audited package/container/release artifacts, current documentation, and readiness for MCP, dbt, scheduler, webhook, and report-diff consumers.
