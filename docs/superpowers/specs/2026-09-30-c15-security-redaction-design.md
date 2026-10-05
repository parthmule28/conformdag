# C15 Centralized Security Redaction Design

**Status:** Design specification
**Baseline:** `main@e27ac4b232d2df802846b67668fbcf73a9b6eb0e`
**Predecessor:** C14 — Complete Platform Contract Typing
**Next boundary:** C16 — Decompose the Policy Package

## Objective

Create one canonical credential-name and credential-value redaction
implementation and migrate all current credential-sensitive evidence,
semantic, verifier, logging, privacy-check, and report-projection paths to it.

After C15:

- `src/conformdag/security/redaction.py` owns generic credential recognition and
  redaction;
- analysis no longer owns its own credential-name vocabulary;
- deterministic evidence no longer owns its own credential regex;
- semantic context and cache no longer own a second generic credential regex;
- agent verification no longer owns a third generic credential regex;
- provider-produced semantic text is sanitized before entering canonical
  findings or persistent caches;
- verifier verdict text cannot persist a credential echoed by the verifier;
- structured ConformDAG logs redact credential-bearing strings and
  credential-named structured values;
- SARIF and HTML projection do not reproduce raw credential material;
- the artifact privacy check uses the canonical implementation rather than a
  separate secret regex vocabulary;
- policy-configured sensitive-logging patterns remain separate policy
  configuration.

C15 centralizes credential redaction. It does not create a general data-loss
prevention framework.

---

## Current state

Generic credential logic is currently duplicated.

### Analysis

`src/conformdag/analysis/models.py` defines:

```python
def secret_like(name: str) -> bool:
    ...
```

with its own marker tuple.

The source analyzer uses this to identify module-scope credential-like
assignments.

### Deterministic evidence

`src/conformdag/checks/common.py` defines its own regex inside:

```python
redact_evidence(...)
```

The evaluator compatibility facade then re-exports that function.

The helper currently truncates before applying redaction.

### Semantic context and cache

`src/conformdag/semantic.py` owns:

```text
DEFAULT_SECRET_PATTERNS
redact_text()
```

and uses them for context construction and normalized cache persistence.

Custom semantic patterns can currently act as the supplied pattern set rather
than an explicitly additive extension of mandatory generic protection.

### Semantic finding normalization

`src/conformdag/semantic_evaluator.py` redacts bounded evidence and audit
excerpts, but provider-produced explanation and remediation text can reach the
canonical `Finding` without equivalent credential-value sanitization.

### Agent verifier

`src/conformdag/agent/verifier.py` owns:

```text
CREDENTIAL_PATTERN
redact_text()
```

The outgoing diff is redacted, but a verifier response could echo credential
material into `reasons` or `concerns`, which can then be persisted in the
verdict cache.

### Artifact privacy script

`scripts/verify_artifact_privacy.py` owns another independent pair of secret
regexes.

### Structured logging

`platform/logging.py` serializes message text, extras, and exception text
without canonical credential redaction.

Several platform errors can contain arbitrary exception or runner stderr text.

### Report projections

SARIF and HTML render finding explanation/remediation/evidence text directly.

C15 removes these duplicate generic implementations and applies one primitive
at the trust boundaries.

---

## Canonical owner

Create:

```text
src/conformdag/security/
├── __init__.py
└── redaction.py
```

`redaction.py` is a pure utility module.

It must not import:

```text
platform
FastAPI
Typer
SQLAlchemy
semantic providers
policy configuration
agent infrastructure
```

This keeps security redaction usable by analysis, checks, semantic, agent,
reporting, platform logging, and scripts without dependency cycles.

---

## Public interface

`security/redaction.py` owns:

```python
CREDENTIAL_NAME_MARKERS: tuple[str, ...]
CREDENTIAL_PATTERNS: tuple[str, ...]

def credential_name_like(name: str) -> bool: ...

def redact_credentials(text: str) -> str: ...

def redact_evidence(text: str, max_chars: int = 240) -> str: ...
```

`security/__init__.py` re-exports these names.

No second authoritative generic marker or regex collection may remain.

---

## Credential-name semantics

`credential_name_like()` recognizes credential-holder names rather than doing
arbitrary substring matching.

Required positive forms include at minimum:

```text
password
passwd
token
secret
api_key
api-key
apikey
credential
PASSWORD
db_password
db-password
auth_token
clientSecret
apiKey
githubCredential
```

Identifier parsing should account for:

- case differences;
- snake case;
- kebab case;
- dotted names where relevant;
- common camel-case boundaries.

Required benign examples must remain false, such as:

```text
secretary
tokenizer
passwordless
credentials_counted
```

The goal is to identify credential-holder names without treating every word
containing `secret` or `token` as a credential.

The analysis check remains conservative when the name actually contains a
credential marker as an identifier component.

---

## Credential-value redaction

`redact_credentials()` must handle at least:

```text
password=hunter2
password = hunter2
password: hunter2
password='hunter2'
password = "hunter2"

"password": "hunter2"
'token': 'abc123'

api_key=abc
api-key: abc
apikey = abc
credential=abc
clientSecret=abc
auth_token=abc

Authorization: Bearer abc.def.ghi
Bearer abc.def.ghi

postgresql://user:hunter2@database/db
https://user:secret@example.test/path
```

The output must preserve useful surrounding structure while replacing
credential values with:

```text
[REDACTED]
```

Exact quote preservation is not a contract, but the result must remain useful
for evidence and diagnostics.

Already-redacted content must remain stable.

---

## Idempotence

For every string:

```python
redact_credentials(redact_credentials(text)) == redact_credentials(text)
```

`[REDACTED]` must never itself be progressively modified.

---

## Redact before bounding

`redact_evidence()` must perform:

```text
redact → truncate
```

not:

```text
truncate → redact
```

Conceptually:

```python
def redact_evidence(text: str, max_chars: int = 240) -> str:
    return redact_credentials(text)[:max_chars]
```

The implementation may validate `max_chars`, but valid existing calls retain
their current bounded-string behavior.

This ordering prevents a truncation boundary from exposing a partial
credential value.

---

## Policy-specific secret patterns remain separate

`SensitiveLoggingConfig.secret_patterns` remains policy configuration.

It is not added to:

```text
CREDENTIAL_NAME_MARKERS
CREDENTIAL_PATTERNS
```

The sensitive-logging evaluator uses:

```text
canonical credential-name detection
OR
policy-specific configured name patterns
```

The two concepts must remain visibly distinct.

---

## Analysis compatibility

`analysis.models.secret_like` is an existing compatibility surface through:

```text
conformdag.analysis.secret_like
```

C15 must not create a second implementation there.

It may remain as a thin wrapper:

```python
def secret_like(name: str) -> bool:
    return credential_name_like(name)
```

Document:

- canonical owner: `conformdag.security.redaction`;
- reason: preserve pre-C15 analysis import compatibility;
- introduced compatibility seam: C15;
- removal decision: C30.

`analysis.airflow` may continue using `secret_like` so C15 does not create
unnecessary analysis churn.

Do not alter parse-cache format or C04 pickle compatibility.

C15 does not redact the local analysis parse cache itself.

---

## Deterministic evidence

`checks.common.redact_evidence` must stop owning regex behavior.

Preserve the import surface because:

```text
conformdag.evaluator.redact_evidence
```

is part of the evaluator compatibility facade.

The checks layer may re-export or thinly wrap:

```text
security.redaction.redact_evidence
```

The generic deterministic finding helper must ensure that credential-bearing
text cannot escape through the human-readable finding explanation while only
the evidence field is safe.

For generic textual evaluator output:

```text
evidence     → bounded canonical redaction
explanation  → canonical credential redaction
```

Do not modify structural fingerprints merely because display text is
redacted.

Policy IDs, paths, anchors, status, and structural fingerprint inputs stay
unchanged.

---

## Semantic compatibility

`semantic.py` currently exposes:

```text
DEFAULT_SECRET_PATTERNS
redact_text()
```

Preserve these names where compatibility requires them, but they must no longer
own generic credential logic.

Recommended compatibility structure:

```text
DEFAULT_SECRET_PATTERNS
    compatibility alias/view of canonical generic patterns

redact_text(...)
    thin compatibility wrapper around redact_credentials()
    plus optional caller-supplied additional patterns
```

Any caller-supplied semantic patterns are **additive**.

They must never disable the mandatory canonical redaction set.

This is an intentional security hardening.

For example, supplying:

```python
[r"tenant_secret=\w+"]
```

must redact both:

```text
tenant_secret=...
password=...
```

rather than replacing mandatory password protection.

Do not change provider authorization or endpoint behavior.

---

## Semantic context

`build_context()` must apply canonical redaction to:

```text
policy text
source slices
runtime observation strings
```

before constructing the semantic context.

Optional additional caller patterns may then further redact content.

The context hash remains the SHA-256 of the actual redacted context text.

No raw source credential value may be sent to the provider through this path.

---

## Semantic request construction

`build_semantic_request()` may defensively re-apply canonical redaction to the
already-redacted context.

This must be idempotent.

The untrusted-evidence boundary and prompt structure remain unchanged.

Do not broaden semantic context.

---

## Semantic cache

`SemanticCache.put()` must sanitize every provider-controlled persisted text
field:

```text
evidence
explanation
remediation
audit_evidence[*].excerpt
```

using the canonical primitive.

Raw prompts and raw provider payloads remain unpersisted.

Cache keys remain hashes of normalized identity inputs.

Do not add prompt or response bodies to cache-key material.

---

## Semantic finding normalization

Provider output is untrusted.

Before provider response text becomes part of a canonical `Finding`, sanitize:

```text
evidence
explanation
remediation
audit_evidence[*].excerpt
```

Use bounded canonical redaction for evidence excerpts.

Use unbounded canonical credential redaction for explanation/remediation unless
an existing field bound requires otherwise.

The status, confidence, citation location, unresolved flag, blocking behavior,
and semantic fingerprint identity remain unchanged.

In particular, semantic finding fingerprints continue to derive from the
existing structural/citation identity rather than redacted display text.

---

## Agent verifier evidence

`build_verifier_evidence()` must:

```text
redact the diff
then bound the full evidence block
```

The untrusted delimiters, before/after fingerprints, and blocking-count
behavior stay unchanged.

No raw credential value may be sent to the verifier provider.

---

## Agent verifier verdict cache

Verifier output is also untrusted.

A model could echo a credential from evidence into:

```text
reasons
concerns
```

Before returning or caching a `Verdict`, sanitize all free-text verdict fields.

The verifier cache continues to store:

```text
cache key → schema-valid normalized Verdict
```

It must not store:

```text
raw diff
raw messages
raw provider response
raw credential values
```

Existing corrupt-cache behavior remains unchanged.

---

## Structured logging

The platform JSON formatter is a text egress boundary.

`JsonFormatter` must apply canonical redaction to:

```text
record.getMessage()
string extra values
string values nested in mappings/sequences
formatted exception text
```

When a structured mapping key itself is credential-name-like, its associated
value must be replaced with `[REDACTED]` even when the value alone does not look
secret-like.

Example:

```python
extra={"api_key": "hunter2"}
```

must not emit `hunter2`.

Do not create a separate credential regex in the logging module.

Non-string scalar values retain their existing JSON representation.

This is sink sanitization, not a new logging-policy framework.

---

## Runner/worker error text

Runner exceptions and worker stderr can become:

```text
persistent scan errors
structured log extras
API-visible scan error text
```

Apply canonical redaction before arbitrary exception/stderr text is stored or
relayed through these paths.

Do not alter:

```text
retry classification
status transitions
claim fencing
timeout behavior
cancellation behavior
exit codes
```

Only textual sanitization is in scope.

---

## Report projections

Canonical findings should already contain sanitized generic credential text.

SARIF and HTML nevertheless act as external projection boundaries and should
defensively call the same canonical redaction primitive on free-text content
that they render:

```text
finding explanation
finding remediation/help
finding evidence where emitted
```

Do not change:

```text
SARIF structure
HTML structure
finding status
severity
fingerprint
location
suppression semantics
```

The canonical `ScanReport` schema and result-fingerprint algorithm are not
redesigned in C15.

JSON remains the canonical report serialization.

---

## Artifact privacy checker

`scripts/verify_artifact_privacy.py` must stop owning a second generic
credential regex vocabulary.

Use the canonical redaction implementation to determine whether a line/file
contains unredacted credential material.

For example, line-oriented detection may treat:

```python
redact_credentials(line) != line
```

as evidence of unredacted credential material.

Already-redacted values must not be reported.

The separate check for persisted raw semantic fields remains independently
owned by the privacy script:

```text
system_prompt
raw_prompt
raw_response
```

Those are semantic-persistence rules, not credential-pattern rules.

---

## Generic redaction pattern ownership

After C15, generic credential patterns must not independently remain in:

```text
analysis
checks
semantic
agent/verifier
artifact privacy script
platform logging
reporting
```

Compatibility aliases or thin wrappers are allowed.

They may not define divergent generic marker or regex lists.

---

## Expected files

Create:

```text
src/conformdag/security/__init__.py
src/conformdag/security/redaction.py
tests/security/test_redaction.py
```

Expected modifications:

```text
src/conformdag/analysis/models.py
src/conformdag/checks/common.py
src/conformdag/checks/airflow/safety.py
src/conformdag/evaluator.py                     # only if compatibility import needs adjustment
src/conformdag/semantic.py
src/conformdag/semantic_evaluator.py
src/conformdag/agent/verifier.py
src/conformdag/platform/logging.py
src/conformdag/platform/worker.py               # narrow error sanitization only
src/conformdag/platform/runner.py               # narrow error sanitization only
src/conformdag/reporting.py
scripts/verify_artifact_privacy.py

tests/test_analysis.py
tests/test_evaluator.py
tests/test_semantic.py
tests/test_agent.py
tests/test_platform.py
tests/test_reporting.py                         # if existing projection tests live here
```

Modify only the files actually required.

No frontend change is expected.

No migration is expected.

No generated schema change is expected.

---

## Explicit non-goals

C15 does not:

- move semantic modules into a package;
- implement C22;
- split `policy.py`;
- implement C16;
- redesign policy editing;
- implement C17;
- merge `SensitiveLoggingConfig.secret_patterns` into generic credential
  patterns;
- introduce enterprise DLP classification;
- scan binary files for secrets;
- encrypt caches;
- redesign semantic provider validation;
- change semantic provider authorization;
- persist raw prompts or responses;
- redesign logging configuration;
- redesign platform error taxonomy;
- alter scan lifecycle;
- change finding fingerprint inputs;
- change report schema;
- change policy schema;
- regenerate TypeScript;
- implement C30 compatibility cleanup.

---

## Test requirements

### Canonical redaction tests

Create `tests/security/test_redaction.py`.

Cover at minimum:

1. every canonical credential-name marker;
2. snake/kebab/camel credential names;
3. benign identifier words;
4. `=` separators;
5. `:` separators;
6. quoted values;
7. unquoted values;
8. JSON-like assignments;
9. YAML-like assignments;
10. bearer values;
11. URL/DSN authority credentials;
12. multiple credentials in one string;
13. existing `[REDACTED]`;
14. idempotence;
15. redaction before truncation;
16. no raw value remains after redaction.

Never use real credentials in tests.

Use unmistakably synthetic strings such as:

```text
c15-test-password-value
c15-test-token-value
```

---

## Migration regressions

### Analysis/checks

Prove:

- `analysis.secret_like` delegates to canonical name detection;
- sensitive-logging custom policy patterns still work independently;
- deterministic finding evidence is bounded and redacted;
- deterministic explanation text cannot retain a credential value;
- evaluator compatibility import remains usable.

### Semantic

Prove:

- source/policy/runtime context uses canonical redaction;
- caller extra patterns are additive;
- caller extra patterns cannot disable canonical protection;
- semantic request evidence contains no raw credential;
- cache evidence/explanation/remediation/audit excerpts contain no raw
  credential;
- provider-echoed credential material does not enter canonical semantic
  findings;
- context and cache behavior remain deterministic;
- no raw prompt/provider payload is persisted.

### Agent

Prove:

- outgoing verifier evidence redacts all supported forms;
- redaction occurs before bounds;
- verifier delimiters remain unchanged;
- verifier verdict `reasons`/`concerns` are sanitized;
- verifier cache contains no raw credential;
- cache key still does not persist the diff.

### Logging

Prove:

- message strings are redacted;
- normal string extras are redacted;
- credential-named extra keys redact their values;
- nested structured extras are redacted;
- exception text is redacted;
- ordinary log fields are unchanged.

### Reporting/privacy

Prove:

- SARIF contains no raw credential from explanation/remediation;
- HTML contains no raw credential from explanation/evidence;
- artifact privacy detects all canonical forms;
- artifact privacy accepts already-redacted values;
- raw semantic field detection remains active.

---

## Verification

Run at minimum:

```bash
mise run setup

mise exec -- uv run pytest \
  tests/security/test_redaction.py \
  tests/test_analysis.py \
  tests/test_evaluator.py \
  tests/test_semantic.py \
  tests/test_agent.py \
  tests/test_reporting.py \
  tests/test_platform.py \
  -x --tb=short

mise run privacy
mise run check
mise run test:coverage
mise run schema --check
mise run build
git diff --check
```

If a named test file does not exist, use the repository's current test location
for that concern rather than creating an unrelated split.

Also perform an ownership audit proving no independent generic credential
marker/regex implementation remains outside `security/redaction.py`.

---

## Review focus

Independent whole-branch review must inspect:

- false negatives in required credential forms;
- false positives on benign names;
- redaction idempotence;
- redact-before-bound ordering;
- semantic context/provider boundary;
- semantic cache persistence;
- semantic finding normalization;
- verifier request and verifier cache;
- deterministic finding explanation/evidence;
- log message/extras/exception handling;
- runner/worker error persistence;
- SARIF/HTML projection;
- artifact privacy;
- compatibility wrappers;
- policy-specific pattern separation;
- fingerprint/schema stability;
- C16/C22/C30 scope containment.

No unresolved Critical or Important finding may remain before merge readiness.

---

## Completion criteria

C15 is complete when:

- one canonical generic redaction implementation exists;
- all required credential-name/value forms are covered;
- benign-word regressions are covered;
- redaction is idempotent;
- redaction precedes truncation;
- analysis credential-name detection derives from the canonical owner;
- deterministic evidence derives from the canonical owner;
- semantic context/cache/finding text derives from the canonical owner;
- agent verifier evidence and verdict cache derive from the canonical owner;
- logging uses the canonical primitive;
- current external report projections use the canonical primitive;
- artifact privacy uses the canonical primitive;
- policy-specific secret patterns remain separate;
- no report/policy/schema/fingerprint redesign occurs;
- no C16/C22/C30 work is pulled forward;
- focused tests pass;
- `mise run privacy` passes;
- default checks and coverage pass;
- exact-head CI passes;
- independent privacy review has no unresolved Critical or Important findings;
- implementation remains unmerged until explicitly authorized.
