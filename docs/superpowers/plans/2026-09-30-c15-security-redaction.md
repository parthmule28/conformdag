# C15 Centralized Security Redaction Implementation Plan

> **Execution contract:** Use `superpowers:executing-plans` in one Native /
> single-session execution context. Do not use subagent-driven implementation.
> Follow RED → GREEN sequentially, retain useful task commits, then obtain an
> independent whole-branch privacy review.

**Goal:** Establish one canonical generic credential-redaction owner and migrate
all approved C15 trust-boundary consumers to it without changing scan,
fingerprint, schema, provider-authorization, or policy-specific pattern
semantics.

**Baseline:** `main@e27ac4b232d2df802846b67668fbcf73a9b6eb0e`

**Approved specification:**
`docs/superpowers/specs/2026-09-30-c15-security-redaction-design.md`
at `the exact approved C15 docs PR head`.

---

## Global constraints

- One generic credential vocabulary.
- Pure `security/redaction.py`.
- Redact before truncation.
- Preserve policy-configured secret-pattern ownership.
- Preserve analysis compatibility imports.
- Preserve evaluator compatibility imports.
- Preserve semantic provider boundary and authorization.
- Preserve verifier request schema and trust delimiters.
- Preserve finding fingerprint inputs.
- Preserve report/policy schema.
- Preserve worker/runner lifecycle behavior.
- No migration.
- No frontend changes.
- No C16 policy decomposition.
- No C22 semantic decomposition.
- No C30 compatibility cleanup.

---

# Task 1 — Add canonical RED tests

**Create**

```text
tests/security/test_redaction.py
```

Add RED tests for:

```text
credential_name_like()
redact_credentials()
redact_evidence()
```

Required cases:

```text
password
passwd
token
secret
api_key
api-key
apikey
credential

snake case
kebab case
camel case

benign secretary/tokenizer/passwordless names

colon
equals
quoted
unquoted
JSON-like
YAML-like
bearer
URL/DSN authority password
multiple credentials
already redacted
idempotence
redact-before-bound
```

Use synthetic credential values only.

Run:

```bash
mise exec -- uv run pytest tests/security/test_redaction.py -x --tb=short
```

Record expected RED due to missing package.

Commit:

```text
test: characterize credential redaction
```

---

# Task 2 — Implement the canonical security primitive

**Create**

```text
src/conformdag/security/__init__.py
src/conformdag/security/redaction.py
```

Implement:

```python
CREDENTIAL_NAME_MARKERS
CREDENTIAL_PATTERNS
credential_name_like()
redact_credentials()
redact_evidence()
```

Implementation requirements:

- standard library only;
- no package-layer dependency;
- name matching understands identifier components;
- generic text patterns support name/value assignments, bearer credentials, and
  URI authority passwords;
- generic substitution uses `[REDACTED]`;
- already-redacted values remain stable;
- every pattern is idempotent;
- `redact_evidence` redacts before truncating.

Run the canonical suite until GREEN.

Commit:

```text
feat: add canonical credential redaction
```

---

# Task 3 — Migrate analysis and deterministic checks

**Modify**

```text
src/conformdag/analysis/models.py
src/conformdag/checks/common.py
src/conformdag/checks/airflow/safety.py
src/conformdag/evaluator.py                 # only if necessary
tests/test_analysis.py
tests/test_evaluator.py
```

### Analysis

Replace the implementation of:

```text
secret_like()
```

with a thin canonical delegation.

Keep `conformdag.analysis.secret_like` functional.

Add the C15/C30 compatibility comment.

Do not alter parse-cache classes or pickle compatibility.

### Checks

Remove the local generic credential regex from `checks.common`.

Make its `redact_evidence` compatibility surface derive from the canonical
security function.

For generic finding text:

```text
evidence → redact_evidence
explanation → redact_credentials
```

Keep fingerprint construction unchanged.

### Sensitive logging

Use canonical `credential_name_like()` for generic credential names.

Continue separately checking:

```text
SensitiveLoggingConfig.secret_patterns
```

Do not merge the two sources.

Run:

```bash
mise exec -- uv run pytest \
  tests/security/test_redaction.py \
  tests/test_analysis.py \
  tests/test_evaluator.py \
  -x --tb=short
```

Commit:

```text
refactor: migrate analysis and check redaction
```

---

# Task 4 — Migrate semantic context, cache, and finding normalization

**Modify**

```text
src/conformdag/semantic.py
src/conformdag/semantic_evaluator.py
tests/test_semantic.py
```

### semantic.py

Remove ownership of the generic credential regex.

Retain compatibility names where required:

```text
DEFAULT_SECRET_PATTERNS
redact_text
```

but make them derive from the canonical security implementation.

Caller-supplied patterns become additive.

They must not disable generic canonical protection.

### build_context

Apply canonical redaction to:

```text
policy text
source slices
runtime observation strings
```

before context assembly/hash.

Then apply optional extra caller patterns.

### Semantic cache

Canonical-redact before persistence:

```text
evidence
explanation
remediation
audit_evidence excerpt
```

Do not persist prompt/provider payloads.

### semantic_evaluator

Before creating the canonical finding, sanitize provider-controlled:

```text
evidence
explanation
remediation
audit excerpts
```

Do not modify semantic fingerprint identity.

Add regressions for provider echo of synthetic credentials.

Run:

```bash
mise exec -- uv run pytest \
  tests/security/test_redaction.py \
  tests/test_semantic.py \
  -x --tb=short
```

Commit:

```text
fix: centralize semantic credential redaction
```

---

# Task 5 — Migrate agent verifier

**Modify**

```text
src/conformdag/agent/verifier.py
tests/test_agent.py
```

Remove:

```text
CREDENTIAL_PATTERN
local generic redaction implementation
```

Use canonical redaction for verifier evidence.

Order:

```text
diff redaction
→ evidence construction
→ max_input_chars bound
```

After schema-valid provider response:

- sanitize `reasons`;
- sanitize `concerns`;
- return sanitized verdict;
- cache sanitized verdict.

Keep cache identity based on the existing hash inputs.

Do not persist the diff.

Add tests proving a provider that echoes the synthetic credential into its
verdict cannot cause the credential to be returned or cached.

Run:

```bash
mise exec -- uv run pytest \
  tests/security/test_redaction.py \
  tests/test_agent.py \
  -x --tb=short
```

Commit:

```text
fix: use canonical redaction in verifier
```

---

# Task 6 — Secure current log and runner/worker text egress

**Modify as required**

```text
src/conformdag/platform/logging.py
src/conformdag/platform/runner.py
src/conformdag/platform/worker.py
tests/test_platform.py
```

### JSON formatter

Add a small private structured-value sanitizer.

Rules:

```text
str → redact_credentials
mapping credential-like key → value becomes [REDACTED]
mapping other key → recursively sanitize value
sequence → recursively sanitize members
other scalar → unchanged
```

Apply it to:

```text
message
extra fields
formatted exception text
```

Do not create new regexes.

### Runner/worker

Where arbitrary exception/stderr text becomes persistent or relayed error text,
canonical-redact it before:

```text
DB transition error field
structured log extra
stderr relay-derived outcome
```

Preserve lifecycle semantics exactly.

Add focused logging/error regression tests.

Commit:

```text
fix: redact platform diagnostic text
```

---

# Task 7 — Migrate report projection and privacy verification

**Modify**

```text
src/conformdag/reporting.py
scripts/verify_artifact_privacy.py
tests/test_reporting.py or current reporting test location
privacy-script tests if present
```

### SARIF/HTML

Canonical-redact free-text finding material emitted by the projection:

```text
explanation
remediation/help
evidence when emitted
```

Do not change structural output.

### Privacy script

Remove independent generic credential regex ownership.

Detect unredacted canonical credentials through the canonical redaction
primitive.

Retain the independent raw semantic field rule:

```text
system_prompt
raw_prompt
raw_response
```

Add regressions for:

```text
canonical forms detected
already-redacted values accepted
raw semantic fields still rejected
```

Run:

```bash
mise run privacy
```

Commit:

```text
fix: reuse canonical redaction at privacy boundaries
```

---

# Task 8 — Duplicate-owner audit

Search the product tree for remaining generic credential implementations.

Review occurrences of:

```text
password
passwd
token
secret
api_key
api-key
apikey
credential
CREDENTIAL_PATTERN
SECRET_PATTERN
DEFAULT_SECRET_PATTERNS
redact_text
redact_evidence
secret_like
```

Expected exceptions:

- canonical declarations in `security/redaction.py`;
- policy-specific `SensitiveLoggingConfig.secret_patterns`;
- compatibility aliases/wrappers;
- test fixtures;
- user-facing prose;
- semantic raw-field privacy checks.

There must be no second generic marker or regex owner.

Record the audit in PR evidence.

---

# Task 9 — Full verification

Run:

```bash
mise exec -- uv run pytest \
  tests/security/test_redaction.py \
  tests/test_analysis.py \
  tests/test_evaluator.py \
  tests/test_semantic.py \
  tests/test_agent.py \
  tests/test_reporting.py \
  tests/test_platform.py \
  -x --tb=short
```

If `tests/test_reporting.py` is not the current location, use the existing
reporting test module.

Then:

```bash
mise run privacy
mise run check
mise run test:coverage
mise run schema --check
mise run build
git diff --check
```

Expected:

```text
no schema drift
no migration
no frontend change
coverage >= repository gate
privacy passed
```

Record exact counts and coverage.

---

# Task 10 — Implementation PR and independent privacy review

Before publication verify:

```text
implementation base is accepted C14 main
approved spec/plan carried exactly
security/redaction.py is sole generic owner
C15 scope only
no C16/C22/C30 implementation
no migration
no generated schema drift
.serena untouched
```

Push:

```text
feat/c15-security-redaction
```

Open implementation PR against `main`.

Wait for exact implementation-head CI.

Run independent whole-branch privacy/security review against the implementation
base.

Review must explicitly inspect:

```text
canonical pattern coverage
benign-name behavior
idempotence
redact-before-bound
deterministic findings
semantic context
semantic cache
semantic findings
verifier evidence
verifier cache
structured logs
runner/worker diagnostic persistence
SARIF/HTML
artifact privacy
compatibility wrappers
policy-pattern separation
fingerprints/schema
```

Fix all Critical/Important findings.

Re-run required gates after fixes.

---

# Task 11 — Review ledger

Only after:

```text
product implementation complete
exact product-head CI green
independent review complete
no unresolved Critical/Important findings
```

update only the C15 row:

```text
planned → review
```

Record:

```text
PR
implementation base
product head
review/fix head if any
approved docs head
focused security/privacy tests
mise run privacy
mise run check
coverage
schema/build
exact-head CI
independent-review result
deferred Minors
```

Commit separately:

```text
docs: record C15 implementation review evidence
```

Push and wait for final PR-head CI.

Verify product-head → final-head delta is ledger-only.

Stop with implementation PR open and unmerged.

---

# Post-merge acceptance

After explicit user merge authorization:

1. verify implementation merge commit;
2. verify post-merge `main` CI;
3. create docs-only acceptance update;
4. change C15 `review → accepted`;
5. record final PR head, merge commit, post-merge CI, privacy evidence, and
   review result;
6. open acceptance PR;
7. stop unmerged unless separately authorized.

---

# Completion definition

C15 is complete when:

- `security/redaction.py` is the sole generic redaction owner;
- all required credential forms are protected;
- benign forms are characterized;
- redaction is idempotent;
- redaction precedes bounds;
- analysis/check/semantic/verifier consumers derive from it;
- provider text cannot leak through canonical semantic findings/cache;
- verifier text cannot leak through verdict cache;
- structured log output derives from it;
- current report projections derive from it;
- privacy verification derives from it;
- policy-specific secret patterns remain independent;
- fingerprints/schema/provider authorization remain unchanged;
- all gates pass;
- independent review has no unresolved Critical/Important findings;
- implementation remains unmerged pending explicit authorization.
