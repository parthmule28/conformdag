# ConformDAG

> **Turn Apache Airflow engineering standards into enforceable, explainable checks.**

## Project status

- **Stage:** Project definition and research planning
- **Primary domain:** Apache Airflow
- **Primary user:** Airflow platform engineers and architecture teams
- **Initial product:** DAG conformance checker
- **Second product capability:** Policy compiler
- **Distribution:** Open source, local CLI, BYOK semantic evaluation
- **Interface:** CLI and static HTML report
- **Initial policy count:** 10
- **Initial release target:** Public, reproducible, benchmarked, and suitable for a Product Hunt launch

---

# 1. Executive summary

ConformDAG is an open-source policy conformance tool for Apache Airflow repositories. It enables platform and architecture teams to define versioned engineering policies, scan DAG code against those policies, and generate reproducible reports that explain every violation.

The project addresses a common organisational problem: coding standards are distributed across documentation, reference implementations, templates, code reviews, operational knowledge, and individual developers' memories. As a result, developers and AI coding assistants often produce valid Airflow code that does not conform to the organisation's engineering standards.

ConformDAG will combine deterministic static analysis with optional LLM-based semantic analysis. Deterministic checks will cover requirements that can be tested precisely. LLM-based checks will be reserved for semantic engineering requirements that cannot be reliably represented as simple lint rules.

The first release will focus only on Apache Airflow. dbt may later be added as an adapter after the Airflow implementation has demonstrated technical quality, user demand, and a stable domain-independent policy model.

The project must not be positioned as a universal AI governance platform or regulatory compliance product. Its initial promise is narrower:

> Scan an Airflow repository against a team's engineering standards and receive an explainable report showing every violation, its policy source, and how to resolve it.

---

# 2. Recommended project name

## Primary name: ConformDAG

**Rationale:**

- Immediately communicates DAG conformance.
- Does not imply regulatory certification.
- Works as both a CLI name and repository name.
- Leaves room for later product modules without pretending to support every engineering domain.
- Is descriptive enough for GitHub and Product Hunt users to understand quickly.

Suggested repository name:

```text
conformdag
```

Suggested Python package and CLI name:

```text
conformdag
```

Example usage:

```bash
conformdag scan dags/
conformdag validate-policies policies/
conformdag explain AIR-ORG-007
conformdag benchmark benchmarks/
```

## Alternative names

- PolicyDAG
- DAGConform
- AirPolicy
- DAGStandard
- DAGVeritas
- Airflow Conformance Kit

ConformDAG is the recommended working name. A trademark and package-name availability check should be completed before public launch.

---

# 3. Origin of the project

The project emerged from a concrete data-engineering problem.

Developers frequently use GitHub Copilot or other coding agents to create Apache Airflow DAGs. These assistants can generate syntactically valid and generally reasonable DAGs, but they usually lack access to the organisation's architecture standards, approved patterns, historical decisions, internal abstractions, and operational constraints.

This produces generic DAGs rather than organisation-conformant DAGs.

Developers can partially address this by maintaining local agent instructions, skills, prompt files, or repository-specific guidance. However, those mechanisms have limitations:

- They are difficult to maintain consistently across teams.
- They are not necessarily approved by architecture owners.
- They do not guarantee enforcement.
- They are often tied to a specific coding assistant.
- They do not provide an auditable conformance report.
- They do not distinguish deterministic requirements from subjective guidance.
- They can become stale or contradict the actual platform standards.

The broader organisational problem is that standards are fragmented across multiple sources:

- Architecture documents
- Engineering standards
- Existing DAG repositories
- Approved templates
- Pull-request comments
- Operational incidents
- Platform-team knowledge
- Deprecated implementations
- Informal conventions

This causes inconsistency, repeated review work, difficult audits, and avoidable production risk.

---

# 4. Project-selection methodology

The project was narrowed using the portfolio-project methodology from Alexey Grigorev's AI Engineering Field Guide.

The relevant principles are:

1. Start with a real user and problem, not an AI technology.
2. Choose one domain.
3. Identify organisations and communities working in that domain.
4. Study existing tools, engineering blogs, issues, case studies, and job requirements.
5. Extract recurring problems.
6. Select one problem.
7. Define the user, input, output, value, and strategic fit.
8. Build one small end-to-end version before expanding.
9. Include evaluation, testing, monitoring, reproducibility, and documentation.

The project was evaluated using the following questions:

- Who is the first user?
- Why must the tool run locally?
- What repeated activity is painful?
- What evidence exists that the problem is real?
- What is the atomic user workflow?
- Is an LLM actually necessary?
- What adjacent tools already exist?
- What must be excluded from version one?
- How will success be measured?
- What capabilities should the project demonstrate professionally?

---

# 5. Final problem definition

## First user

An Airflow platform engineer, platform maintainer, or architecture-team member responsible for reviewing DAGs contributed by multiple development teams.

## Recurring problem

Organisation-specific Airflow standards are distributed across documentation, reference implementations, templates, review comments, and institutional knowledge. They are therefore communicated and enforced inconsistently.

## Current workaround

Teams rely on combinations of:

- Documentation
- Approved templates
- Reviewer memory
- Repeated pull-request comments
- Repository-specific instruction files
- Custom lint rules
- Airflow cluster policies
- Manual architecture reviews
- Local coding-agent skills

No single mechanism provides complete, versioned, explainable, and reproducible enforcement.

## Required input

Version one will accept:

1. An Apache Airflow DAG repository
2. A manually authored policy pack
3. Explicit standards documents in Markdown
4. Approved reference DAGs where relevant
5. User configuration for deterministic and semantic checks

The first conformance checker should not depend on automatic policy extraction.

## Useful output

A reproducible conformance report containing:

- Policy identifier
- Policy version
- Policy owner
- Source-document citation
- Affected file and lines
- Severity
- Finding status
- Code evidence
- Explanation
- Textual remediation
- Enforcement method
- Model confidence where applicable
- Whether the finding is deterministic or semantic
- Exception and suppression information
- Run metadata

The tool should support machine-readable JSON and SARIF, a human-readable terminal report, and a static HTML report.

## Success metric

The initial product should detect known Airflow-policy violations with high precision, cite the correct policy source, avoid findings on valid counterexamples, and produce locally reproducible results.

---

# 6. Atomic user workflow

> When an Airflow platform engineer needs to review a DAG repository, they run ConformDAG with an approved policy pack. The tool evaluates the DAGs using deterministic and optional semantic checks, then returns a cited conformance report showing violations and textual remediation, reducing repetitive review work and inconsistent approvals.

Product Hunt-oriented version:

> Scan an Airflow repository against your team's engineering standards and get an explainable report showing every violation, its policy source, and how to resolve it.

---

# 7. Why Apache Airflow is the correct v1 scope

## 7.1 Strong first-hand problem evidence

The motivating problem comes from direct experience with Airflow DAG development and review. AI assistants frequently generate generic DAGs because they lack organisation-specific platform context.

This firsthand exposure provides stronger product judgement than selecting a domain solely because it is technically interesting.

## 7.2 Airflow has a valuable policy surface

Airflow policies can operate at multiple levels:

- Python syntax
- Python abstract syntax tree
- Imports and dependencies
- DAG metadata
- Task metadata
- DAG topology
- Operator configuration
- Runtime DAG objects
- Architectural boundaries
- Operational behaviour

This makes Airflow suitable for a hybrid policy engine.

## 7.3 Airflow supports both deterministic and semantic checks

Examples of deterministic checks:

- Required DAG owner
- Required organisational tags
- Required task timeout
- Retry bounds
- Forbidden operators
- Deprecated APIs
- Top-level network calls
- Missing callbacks

Examples of semantic checks:

- Whether external writes are idempotent
- Whether business transformation logic is embedded in orchestration code
- Whether logs may expose sensitive information
- Whether an approved internal abstraction should have been used

## 7.4 Airflow has existing enforcement primitives but no unified policy product

Airflow cluster policies, static analysis, Ruff rules, repository tests, and custom scripts can enforce parts of a standard. However, teams must manually convert standards into multiple enforcement mechanisms and retain provenance independently.

ConformDAG's opportunity is to provide a versioned policy layer, consistent reporting, provenance, hybrid enforcement, and evaluation.

---

# 8. Why dbt is deferred

The product should not support both Airflow and dbt in version one.

Supporting both would increase complexity across:

- Parsers
- Domain models
- Policy semantics
- Fixtures
- Benchmarks
- Documentation
- Error handling
- User onboarding
- Product messaging

Additionally, dbt already provides strong declarative mechanisms and has a mature surrounding ecosystem:

- Data tests
- Unit tests
- Model contracts
- Documentation requirements
- SQLFluff
- Metadata linters
- Project-evaluation packages

A dbt adapter may still be valuable later, particularly for organisational architecture rules not already handled by dbt's native tooling.

Potential future dbt policies include:

- Required model-layer boundaries
- Prohibited source-to-mart dependencies
- Mandatory contracts for published models
- Approved materialisations by layer
- Required documentation for exposed models
- Restricted macros or packages
- PII handling rules
- Naming and ownership requirements
- SQL/metadata semantic consistency
- Migration and deprecation policies

## Conditions for adding dbt

Do not add dbt until all of the following are true:

- All ten Airflow policies work.
- The benchmark is reproducible.
- The false-positive rate is acceptable.
- Policy provenance works.
- Contradiction approval works.
- At least three external users have tested ConformDAG.
- At least two users explicitly request dbt.
- The intermediate policy representation supports dbt without an Airflow-specific redesign.
- At least five proposed dbt policies are not adequately covered by dbt tests, contracts, or SQLFluff.

---

# 9. Competitive landscape

The broad category of organisational coding standards and AI-assisted code review already exists.

Relevant adjacent products include:

- Packmind
- Agent OS
- Kodus
- Greptile
- CodeRabbit
- GitHub Copilot custom instructions
- OpenAI Codex repository instructions and code review
- Semgrep
- Open Policy Agent

These tools cover combinations of:

- Standards discovery
- Repository instructions
- Code review
- Rule generation
- Self-hosted deployment
- Deterministic policy checks
- Agent context distribution

The closest overlap is Packmind, which centralises engineering standards, discovers conventions, and distributes instructions into coding agents.

Kodus also overlaps with the idea of generating rules from historical code-review activity.

Therefore, ConformDAG should not position itself as:

- A general engineering standards platform
- A universal AI governance layer
- A generic AI pull-request reviewer
- A central prompt-management product
- A tool that merely writes instruction files

Its differentiation should be:

> Domain-specific, testable, provenance-preserving enforcement of Apache Airflow engineering invariants.

---

# 10. Product sequence

## Phase 1: DAG conformance checker

The first implementation uses manually authored policies and focuses on enforcement quality.

This isolates the enforcement problem and allows accurate evaluation.

## Phase 2: Policy compiler

The second capability converts explicit standards documents and approved examples into draft structured policies.

All generated policies require human approval before activation.

## Phase 3: Optional adapters and exports

Possible later additions:

- dbt adapter
- Generic Python adapter
- Airflow cluster-policy exporter
- Semgrep rule exporter
- Agent-instruction exporter
- CI integrations

The project must not expose a premature plugin framework in version one.

---

# 11. Policy ownership and lifecycle

The architecture or platform team should own platform-engineering policies because it controls the platform decisions that define acceptable development standards.

However, the open-source product should use the general term **policy owner**.

Each policy should contain:

- Owner
- Approvers
- Approval state
- Version
- Source
- Effective date
- Review date
- Optional expiry date
- Enforcement type
- Severity

Suggested policy lifecycle:

```text
DRAFT
APPROVED
ACTIVE
CONFLICTED
DEPRECATED
REJECTED
```

Only `ACTIVE` policies may fail a conformance scan.

Example:

```yaml
ownership:
  owner: data-platform-architecture
  approvers:
    - platform-maintainers
  approved_at: 2026-07-29
  review_before: 2027-01-29
```

---

# 12. Contradiction handling

Codebase patterns are evidence, not policy.

An existing repository may contain:

- Approved current architecture
- Legacy architecture
- Temporary workarounds
- Technical debt
- Deprecated APIs
- Copy-and-paste mistakes
- One-off exceptions
- Contradictory implementations

The tool must not silently infer hard policies from code frequency.

When source documents, approved examples, and code patterns disagree, ConformDAG must:

1. Report the contradiction.
2. Show supporting and contradicting evidence.
3. Mark the policy as `CONFLICTED`.
4. Prevent the policy from becoming active.
5. Require approval from the policy owner.

The system must never silently select one source as authoritative.

---

# 13. Enforcement model

ConformDAG should use a hybrid enforcement architecture.

## Tier 1: Deterministic rules

Use deterministic analysis whenever the requirement can be tested precisely.

Potential techniques:

- Python AST
- Semgrep
- ast-grep
- Airflow DagBag inspection
- Airflow runtime-object inspection
- Repository tests
- Airflow cluster-policy generation

Deterministic findings can fail the CLI and CI process.

## Tier 2: Semantic rules

Use an LLM only for requirements that require contextual or architectural judgement.

Allowed semantic statuses:

```text
PASS
FAIL
NEEDS_REVIEW
NOT_APPLICABLE
```

Abstention is a first-class feature.

Semantic findings should initially be advisory or configurable rather than hard blockers.

## Tier 3: Human judgement

Some policies require explicit reviewer approval. The tool must distinguish:

- Hard deterministic violations
- Deterministic warnings
- Semantic findings
- Needs-review findings
- Informational observations

---

# 14. Initial ten-policy catalogue

The first release will include exactly ten manually authored Airflow policies.

## Deterministic policies

### AIR-DET-001: Required DAG ownership metadata

Every DAG must declare a valid owner or approved ownership reference.

### AIR-DET-002: Required organisational tags

Every DAG must include required tags for environment, domain, ownership, or operational classification.

### AIR-DET-003: Task execution timeout required

Every task covered by the policy must declare an execution timeout or inherit an approved default.

### AIR-DET-004: Retry configuration bounds

Retries and retry delays must remain within approved limits.

### AIR-DET-005: Forbidden top-level I/O

DAG import and parsing must not execute network requests, database queries, or other expensive top-level operations.

### AIR-DET-006: Deprecated or forbidden operators

DAGs must not use deprecated, restricted, or organisation-disallowed operators.

## Semantic policies

### AIR-SEM-001: External writes must be idempotent

Retrying a task must not create duplicate externally visible records or side effects.

### AIR-SEM-002: DAG files should contain orchestration logic

Substantial transformation or business logic should be implemented in separately testable modules rather than embedded directly in DAG definitions.

### AIR-SEM-003: Sensitive information must not be exposed in logs

Task code and logging statements must avoid exposing secrets, credentials, tokens, or sensitive payloads.

### AIR-SEM-004: Approved organisational abstractions should be used

When an approved internal abstraction applies, the DAG should use it rather than reimplementing equivalent behaviour.

---

# 15. Policy representation

The central product object should be a versioned policy pack, not a prompt.

Example:

```yaml
id: AIR-SEM-001
title: External writes must be idempotent
version: 1.0.0
status: ACTIVE
severity: high

scope:
  files:
    - "dags/**/*.py"
  operators:
    - "PythonOperator"

ownership:
  owner: data-platform-architecture
  approvers:
    - platform-maintainers

source:
  document: "standards/dag-authoring.md"
  section: "Idempotency and retries"
  version: "1.3"

invariant: >
  Retrying a task must not create duplicate externally visible records.

safe_path: >
  Use an idempotency key, merge or upsert operation, partition replacement,
  or another documented deduplication mechanism.

enforcement:
  type: hybrid
  deterministic_checks:
    - detect-direct-insert
  model_check: true
  allow_abstention: true

exceptions:
  require_reason: true
  require_expiry: true
```

The same policy representation may later compile into:

- Deterministic checks
- Airflow cluster policies
- Repository tests
- Agent instruction files
- Pull-request review guidance
- Audit reports

---

# 16. Local execution, BYOK, and model support

The user's development system has approximately:

- Intel Core i5-12450H
- 16 GB RAM
- Integrated Intel graphics
- CachyOS Linux

This is sufficient for:

- AST analysis
- Airflow repository parsing
- CLI execution
- Static HTML report generation
- Benchmark orchestration
- Small quantised model experiments

It is not suitable for relying on large local models as the primary semantic engine.

## Recommended model strategy

The product should be:

- Provider-neutral
- BYOK
- Compatible with OpenAI-style APIs
- Able to run deterministic-only
- Able to use local or remote model endpoints

Example configuration:

```yaml
semantic_engine:
  provider: openai_compatible
  base_url: ${CONFORMDAG_MODEL_BASE_URL}
  api_key: ${CONFORMDAG_MODEL_API_KEY}
  model: ${CONFORMDAG_MODEL_NAME}
  temperature: 0
```

This abstraction can support:

- Hosted model APIs
- OpenRouter
- Ollama
- LM Studio
- vLLM
- Organisation-hosted gateways

## Accurate privacy claim

Do not claim that all analysis is local when a hosted model is configured.

Use this wording:

> The policy engine and deterministic analysis run locally. Semantic checks use a user-selected local or remote model endpoint.

## Privacy and governance controls

Version one should include:

- Deterministic-only mode
- Explicit context preview
- File-exclusion rules
- Secret redaction
- Maximum context limits
- No telemetry by default
- Optional semantic checks
- User-controlled request and response logging
- Input-content hashes in audit records
- Clear warnings when source code leaves the machine

Example commands:

```bash
conformdag scan dags/ --deterministic-only
conformdag scan dags/ --preview-model-context
conformdag scan dags/ --provider openrouter
```

---

# 17. Findings and remediation

Version one should produce findings and textual remediation only.

It should not automatically modify code or generate patches.

Example finding:

```yaml
finding:
  policy_id: AIR-SEM-002
  policy_version: 1.0.0
  status: NEEDS_REVIEW
  severity: medium
  file: dags/customer_sync.py
  lines: 73-91

  evidence: >
    The task performs substantial record-normalisation logic directly inside
    the DAG file.

  explanation: >
    The active standard requires DAG files to define orchestration while
    transformation logic is implemented in a separately testable module.

  remediation: >
    Move normalize_customer_records into a project module and invoke it from
    the task. Add unit tests for the module independently of Airflow.

  confidence: 0.86
  enforcement: semantic
```

Patch generation may be considered only after finding quality is proven.

---

# 18. Auditability requirements

Local execution does not automatically make a tool auditable.

Every run should record:

- Repository commit hash
- Policy-pack version
- Policy source and approval status
- Tool version
- Model provider
- Model name and exact version where available
- Prompt-template version
- Sampling configuration
- Retrieved context
- Deterministic rule results
- Model responses where logging is enabled
- Final decisions
- Suppressions and exceptions
- Relevant input hashes
- Timestamp
- Runtime environment

This allows findings to be reproduced and independently inspected.

The product should describe itself as a conformance checker, not as a regulatory-compliance platform.

---

# 19. Reporting formats

Version one should support:

## Terminal report

Optimised for local developer use and CI logs.

## JSON report

Stable machine-readable schema for integrations and benchmarks.

## SARIF report

Useful for code-scanning interfaces and CI platforms.

## Static HTML report

Useful for demonstrations, Product Hunt, architecture review, and sharing without running a hosted server.

Every report should include:

- Summary by severity
- Summary by policy
- Deterministic versus semantic breakdown
- Files scanned
- Policies evaluated
- Policies skipped
- Findings
- Needs-review cases
- Exceptions
- Run provenance

---

# 20. CLI design

Suggested commands:

```bash
conformdag init
conformdag validate-policies policies/
conformdag scan dags/
conformdag scan dags/ --format json
conformdag scan dags/ --format sarif
conformdag scan dags/ --html report.html
conformdag scan dags/ --deterministic-only
conformdag explain AIR-SEM-001
conformdag benchmark benchmarks/
conformdag list-policies
```

Suggested exit behaviour:

- `0`: no blocking violations
- `1`: deterministic blocking violations
- `2`: invalid configuration or policy pack
- `3`: scanner execution failure
- Semantic findings are advisory by default and configurable later

---

# 21. Proposed architecture

```text
Standards documents
Approved examples
Manual policy definitions
        │
        ▼
Policy validation and lifecycle
        │
        ▼
Intermediate policy representation
        │
        ├── Deterministic engine
        │      ├── Python AST
        │      ├── Airflow DagBag
        │      ├── Runtime object checks
        │      └── Pattern rules
        │
        └── Semantic engine
               ├── Context selection
               ├── Provider abstraction
               ├── Structured model output
               └── Abstention handling
        │
        ▼
Finding normalisation
        │
        ▼
Terminal / JSON / SARIF / HTML reports
```

Suggested package structure:

```text
src/conformdag/
├── policy/
│   ├── schema.py
│   ├── loader.py
│   ├── validator.py
│   ├── lifecycle.py
│   ├── provenance.py
│   └── contradictions.py
├── engines/
│   ├── deterministic.py
│   └── semantic.py
├── adapters/
│   └── airflow/
│       ├── ast_checks.py
│       ├── dagbag_checks.py
│       ├── object_checks.py
│       └── context.py
├── providers/
│   ├── base.py
│   └── openai_compatible.py
├── findings/
│   ├── schema.py
│   ├── severity.py
│   └── suppression.py
├── reporting/
│   ├── terminal.py
│   ├── json_report.py
│   ├── sarif.py
│   └── html.py
├── benchmark/
│   ├── runner.py
│   ├── metrics.py
│   └── datasets.py
├── cli/
│   └── main.py
└── config.py
```

The internal policy model should remain domain-neutral where practical, while the released implementation remains Airflow-only.

---

# 22. Evaluation and white-paper plan

The project should be evaluated before its public product launch.

## Research question 1: Policy representation

How accurately and completely can Airflow engineering standards be represented as atomic, structured policies?

## Research question 2: Violation detection

How accurately does each enforcement strategy detect known violations?

Compare:

1. LLM-only
2. Deterministic-only
3. Hybrid
4. Generic AI reviewer baseline

## Research question 3: False positives

How often does the system incorrectly flag:

- Valid implementations
- Explicit exceptions
- Irrelevant files
- Safe counterexamples
- Equivalent approved patterns

## Research question 4: Auditability

Can a reviewer trace every finding to:

- The exact policy
- The correct source passage
- The correct code evidence
- The enforcement method
- The policy version

## Research question 5: Cost and performance

How do model size and enforcement strategy affect:

- Runtime
- Peak memory
- Token usage
- Monetary API cost
- Detection quality
- Repeatability

## Research question 6: Small-model viability

For which semantic policies are small quantised local models sufficient, and where do hosted models provide materially better precision?

---

# 23. Benchmark dataset

Use only public or synthetic code and standards.

Do not use HSBC source code, standards, review comments, internal architecture documents, incidents, prompts, or templates.

The benchmark should include:

1. Public Airflow best-practice policies
2. Valid DAG examples
3. Hand-authored violations
4. Automatically mutated violations
5. Safe counterexamples
6. Ambiguous examples requiring abstention
7. Explicit exception cases
8. Unrelated Python changes
9. Multiple implementations of the same valid pattern
10. Adversarial examples that resemble violations but are safe

Each benchmark case should define:

- Expected policy applicability
- Expected status
- Expected code location
- Expected evidence
- Expected severity
- Whether deterministic evaluation is possible
- Whether semantic evaluation is required

---

# 24. Technical metrics

## Detection quality

- Precision
- Recall
- F1 score
- False-positive rate
- False-negative rate

## Evidence quality

- Policy-citation accuracy
- Code-location accuracy
- Evidence relevance
- Explanation correctness

## Semantic behaviour

- Correct abstention rate
- Invalid structured-output rate
- Repeatability across repeated runs
- Inter-model agreement

## Performance

- Runtime
- Peak memory
- Tokens per finding
- Cost per repository scan
- Cost per correctly detected violation

## Remediation

- Reviewer-rated usefulness
- Correctness
- Specificity
- Actionability

---

# 25. Product and business metrics

The project should measure business impact through controlled user studies rather than making unsupported ROI claims.

Potential metrics:

- Review time saved
- Repeated review comments avoided
- Percentage of findings accepted
- Time required to author and approve a policy
- Time required to remediate a violation
- Number of escaped violations
- Percentage of checks handled deterministically
- Reviewer trust rating
- Suppression rate
- Exception rate
- Semantic-check opt-in rate
- Scan completion rate

---

# 26. Product Hunt readiness

The project should not be considered Product Hunt-ready merely because it has a web page.

Minimum readiness criteria:

- Clear one-sentence value proposition
- Installable package or binary
- Working CLI
- Ten documented policies
- Example repository
- Deterministic-only mode
- Optional BYOK semantic checks
- Static HTML report
- Reproducible benchmark
- Transparent limitations
- Strong README
- Architecture diagram
- Demo video or animated terminal recording
- Public roadmap
- Contribution guide
- Issue templates
- Security and privacy documentation

Recommended tagline:

> Turn Airflow standards into enforceable, explainable checks.

Recommended short description:

> ConformDAG scans Apache Airflow repositories against versioned engineering policies using deterministic analysis and optional BYOK semantic review. Every finding includes code evidence, policy provenance, and textual remediation.

---

# 27. Explicit v1 exclusions

Version one will not include:

- dbt support
- Generic multi-language review
- Automatic code generation
- Patch generation
- Automatic code modification
- IDE extensions
- Desktop application
- Mobile application
- GitHub App
- GitLab App
- Hosted SaaS
- Team dashboard
- Authentication
- Role-based access control
- Cloud synchronisation
- Multi-agent architecture
- Fine-tuning
- Autonomous remediation
- Continuous learning from reviewers
- Slack ingestion
- Confluence ingestion
- Email ingestion
- Automatic policy activation
- Regulatory certification
- Generic policy plugin marketplace
- Multiple vector databases

---

# 28. Risks and mitigations

## Risk: The idea becomes a generic AI reviewer

**Mitigation:** Restrict v1 to Airflow and ten explicit policies.

## Risk: The tool duplicates existing linters

**Mitigation:** Use deterministic linters as enforcement primitives and focus the product on policy provenance, hybrid checks, and organisational conformance.

## Risk: LLM findings are noisy

**Mitigation:** Use structured output, abstention, fixed policy-specific prompts, benchmarks, and advisory semantic enforcement.

## Risk: Existing code is mistaken for policy

**Mitigation:** Treat repository patterns as evidence only. Require policy-owner approval.

## Risk: BYOK undermines privacy claims

**Mitigation:** Clearly distinguish local deterministic analysis from remote semantic evaluation and provide context preview and deterministic-only mode.

## Risk: The architecture becomes over-generalised

**Mitigation:** Keep the internal policy model reasonably neutral, but implement and document only Airflow.

## Risk: Product Hunt pressure distorts the project

**Mitigation:** Prioritise benchmark quality, reproducibility, and user usefulness before visual polish.

## Risk: Audit or compliance claims create legal exposure

**Mitigation:** Use the language of engineering-policy conformance and auditability, not regulatory certification.

---

# 29. Implementation milestones

## Milestone 0: Repository and design setup

- Create repository
- Add licence
- Add contribution guide
- Add architecture decision records
- Define policy and finding schemas
- Create sample Airflow repository

## Milestone 1: Deterministic engine

- Implement CLI skeleton
- Load and validate policy packs
- Implement first six deterministic policies
- Produce terminal and JSON reports
- Add tests and fixtures

## Milestone 2: Semantic engine

- Add provider abstraction
- Add BYOK configuration
- Add structured semantic responses
- Implement four semantic policies
- Add context preview and redaction
- Add abstention handling

## Milestone 3: Reporting and reproducibility

- Add SARIF output
- Add static HTML report
- Add run provenance
- Add suppressions and exceptions
- Add deterministic-only mode

## Milestone 4: Benchmark

- Build labelled dataset
- Add mutation generation
- Compare deterministic, semantic, and hybrid methods
- Measure precision, recall, cost, latency, and repeatability

## Milestone 5: Public release

- Complete README
- Publish technical report or white paper
- Record demo
- Package release
- Collect external user feedback
- Launch publicly

## Milestone 6: Policy compiler

- Parse standards documents
- Extract candidate policies
- Detect contradictions
- Show supporting and contradicting evidence
- Require owner approval
- Activate approved policies only

---

# 30. Codex handoff prompt

The following prompt can be supplied to Codex when beginning implementation:

```text
Create the initial repository for an open-source Python project named ConformDAG.

ConformDAG is a local CLI that scans Apache Airflow DAG repositories against versioned organisational engineering policies. It combines deterministic static analysis with optional BYOK semantic evaluation through an OpenAI-compatible endpoint. It produces terminal, JSON, SARIF, and static HTML reports. Every finding must include policy provenance, code evidence, severity, enforcement type, and textual remediation.

Scope for the first implementation:

1. Python 3.12 project using a modern pyproject.toml-based build.
2. CLI commands:
   - conformdag init
   - conformdag validate-policies
   - conformdag scan
   - conformdag list-policies
   - conformdag explain
3. Define typed schemas for:
   - policy packs
   - policy lifecycle
   - policy provenance
   - findings
   - scan metadata
4. Implement policy loading and validation from YAML.
5. Implement the first deterministic policy only:
   - AIR-DET-001: every DAG must declare an owner.
6. Parse Airflow DAG Python files without requiring a running Airflow scheduler.
7. Produce terminal and JSON output.
8. Use explicit exit codes.
9. Add unit tests and example fixtures.
10. Add a sample repository and sample policy pack.
11. Do not implement semantic evaluation, dbt support, a web server, a plugin framework, patch generation, or CI integrations yet.

Architecture constraints:

- Keep the core policy schema reasonably domain-neutral.
- Keep Airflow-specific analysis inside src/conformdag/adapters/airflow.
- Separate policy loading, scanning, findings, reporting, and CLI layers.
- Use type annotations throughout.
- Use clear error messages.
- Prefer small modules and explicit interfaces.
- Add README sections for installation, quick start, policy format, architecture, limitations, and roadmap.

Before generating code, create:

1. A concise architecture plan.
2. The proposed repository tree.
3. The policy and finding schema design.
4. The testing strategy.

Then implement milestone 1 incrementally.
```

---

# 31. Immediate next actions

1. Create the `conformdag` GitHub repository.
2. Add this document as `docs/project-brief.md`.
3. Add an MIT or Apache-2.0 licence after reviewing dependency and contribution goals.
4. Use the Codex handoff prompt to create the initial repository structure.
5. Implement only `AIR-DET-001` first.
6. Establish the policy schema and finding schema before adding more rules.
7. Add one valid and one invalid Airflow DAG fixture.
8. Make the first end-to-end CLI scan work.
9. Add the remaining deterministic rules one at a time.
10. Defer semantic evaluation until the deterministic engine and reporting contract are stable.

---

# 32. Final locked project definition

| Dimension | Decision |
|---|---|
| Project name | ConformDAG |
| Domain | Apache Airflow |
| User | Airflow platform or architecture engineer |
| Primary function | DAG conformance checking |
| Second capability | Policy compilation |
| Policy owner | Architecture or platform team |
| Contradictions | Report and require approval |
| Policies | 10 manually authored policies |
| Enforcement | Fail and report |
| Semantic inference | Optional BYOK |
| Local models | Experimental benchmark only |
| Remediation | Textual guidance only |
| Interface | CLI and static HTML report |
| dbt | Deferred adapter |
| Hosted service | Excluded from v1 |
| Regulatory claims | Excluded |
| Professional signal | AI engineering, backend/system design, open-source maintenance, product thinking, evaluation, and observability |

---

# 33. One-sentence definition

> ConformDAG is an open-source CLI that checks Apache Airflow repositories against versioned organisational engineering policies using deterministic analysis and optional BYOK semantic evaluation, producing reproducible, cited conformance reports.
