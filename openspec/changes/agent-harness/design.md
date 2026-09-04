## Context

See `proposal.md` for why. ADR 0003 decides the agentic platform: the agent is a tool user
of ConformDAG — it reads the canonical report JSON, triages findings, applies deterministic
codemods, proves the fix by deterministic re-scan, then an LLM-verifier (OpenAI-compatible
endpoint, model-agnostic) reviews the diff and re-scan report for semantic sanity before
the agent pushes a branch and opens a PR via a GitHub App. The agent never merges — humans
merge. ADR 0002 listed auto-PRs as a non-goal; ADR 0003 supersedes that in part. This
change specifies the harness. It depends on `fix-engine-and-codemods` (codemod registry,
verify-by-rescan, agent-readable findings) and is strengthened by, but not blocked on,
`platform-server` (governance aggregates for the policy-review mode).

## Goals / Non-Goals

**Goals:**

- Specify the agent harness as a tool user of the existing engine (single-engine principle).
- Make PR creation safe and auditable: deterministic codemods, deterministic re-scan gate,
  LLM-verifier semantic gate, evidence-rich PR bodies, GitHub App identity.
- Amend the `org-governance-1-0` non-goals requirement per ADR 0003 (auto-PR in scope;
  humans merge).
- Add the policy-review agent mode over governance aggregates.

**Non-Goals:**

- Autonomous merging, approving, or force-pushing.
- Autonomous DAG creation or Airflow runtime orchestration.
- Non-OpenAI-compatible provider integrations.
- An MCP server in this change (v1.x follow-up).

## Decisions

1. **The agent consumes the core tool as a library/CLI, never a second evaluation path**
   (single-engine principle). The harness invokes the same scan orchestration and codemod
   registry as `conformdag scan` / `conformdag fix`. Alternative: an agent-native
   evaluation pipeline. Rejected — two evaluation paths would fork the verifier.

2. **Fix generation is always deterministic codemods.** The LLM never authors mechanical
   patches; it triages findings and verifies results. Alternative: LLM-generated diffs.
   Rejected — non-reproducible, unreviewable fixes.

3. **The LLM-verifier reviews the diff plus before/after re-scan reports against a strict
   verdict schema** (approve/reject with reasons); a reject verdict blocks PR creation. The
   verifier reuses the existing semantic-boundary patterns: redaction, strict response
   validation, bounded concurrency, normalized caching.

4. **The provider surface is OpenAI-compatible endpoints only** — model-agnostic by
   construction. No provider-specific code paths.

5. **GitHub identity is a GitHub App** (fine-grained permissions, short-lived installation
   tokens) — no PATs. The agent opens PRs and NEVER merges or force-pushes.

6. **The PR body is an interpretability artifact:** findings fixed with file/line, policy
   contracts, report fingerprints before/after, deterministic verification result,
   LLM-verifier verdict, and a rollback note.

7. **Policy-review agent mode consumes platform aggregates** (fail rates by policy,
   suppression rates, stale suppressions, never-firing policies) — or a locally computed
   summary when the platform is absent — and drafts policy-pack PRs for human review.

8. **MCP server is deferred to a follow-up change**, but the report-consumption layer is
   designed as a tool surface so an MCP adapter can expose the same tools later.

9. **Verdict schema includes `escalate`.** Verdicts are `approve | reject | escalate` with
   a `reason_code` enum (`behavior-change-suspected`, `incomplete-fix`, `scope-creep`,
   `no-semantic-change`, `other`), a `confidence` level, and bounded `reasons`/`concerns`
   lists. `escalate` blocks the PR and asks a human. No partial approvals — the verdict
   applies to the whole diff. Verdicts are cached by (diff hash, report fingerprints,
   model).

10. **PR batching defaults to one PR per repo per run.** The diff and PR body are grouped
    by policy; a PR of many mechanical, re-scan-verified kwarg additions reviews faster
    than many PRs. A `--batch per-policy` flag supports staged rollouts of a single
    policy. Per-finding PRs are never generated.

11. **Policy-review ships local aggregation first.** `conformdag agent policy-review
    --reports ...` computes fail/suppression/staleness aggregates from report JSONs on
    disk, keeping this change unblocked by `platform-server`; the platform's `/api/v1`
    aggregates slot in behind the same interface later.

12. **No agent framework — stdlib + httpx + pydantic, mirroring `semantic.py`.** The
    pipeline is deliberately mostly deterministic: scan → triage (pure rules, no LLM) →
    codemod → re-scan → one structured LLM verifier call → git push → PR via REST.
    LangChain/LangGraph-style frameworks add dependency churn and obscure exactly the
    control flow that must stay explicit and auditable. Model-agnostic by construction:
    OpenAI-compatible chat completions with JSON-schema structured output. Push
    mechanics: local `git` subprocess for branch/commit/push (auth via existing
    remotes); the GitHub App installation token is used only to open the PR, so the PR
    is App-authored.

## Risks / Trade-offs

- [LLM-verifier false approvals] → Deterministic re-scan is the compliance gate; the
  verifier gates only semantic sanity and cannot clear a deterministic FAIL.
- [GitHub App scope creep] → Least-privilege manifest: contents write for branch push and
  pull requests write only; no merge, approve, or workflow permissions.
- [Prompt injection via DAG source content] → Findings, diffs, and reports are treated as
  untrusted evidence with delimitation inherited from the existing semantic boundary;
  verdicts are schema-validated.

## Migration Plan

Apply after `fix-engine-and-codemods` (hard dependency: codemods and agent-readable
findings). Amend the `org-governance-1-0` non-goals requirement in the same change so the
spec never contradicts the shipped capability. `platform-server` integration for
policy-review aggregates is additive; the local summary mode can ship first if the platform
is not yet available.

## Open Questions

None — resolved at planning (2026-09-02); see decisions 9–12.
